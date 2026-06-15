from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from config import settings

_TIMEOUT = 45.0


def _json_decode_loose_embedded(text: str) -> Any:
    """
    部分 18gps 返回形如：时间戳数字 / 标量 + 紧跟 JSON 对象（无逗号分隔）。
    raw_decode 会先吃掉标量，再把剩余当作真正业务 JSON。
    """
    s = (text or "").strip()
    if not s:
        raise ValueError("empty json segment")
    dec = json.JSONDecoder()
    val, idx = dec.raw_decode(s)
    tail = s[idx:].strip()
    if tail and tail[0] in "{[":
        try:
            val2, _ = dec.raw_decode(tail)
            if isinstance(val2, dict):
                return val2
            if isinstance(val2, list):
                return val2
        except json.JSONDecodeError:
            pass
    return val


def _plain_track_http_body(text: str) -> dict[str, Any] | None:
    """
    GetDate 偶发直接返回轨迹明文（lng,lat,毫秒,...;...），非 JSON。
    extract_history_data_string 支持 data 为 str，故封装为 {success,data}。
    """
    t = (text or "").strip()
    if not t or t.lstrip().startswith(("{", "[", '"')):
        return None
    parts = [p for p in re.split(r";+", t) if p.strip()]
    if not parts:
        return None
    head = re.split(r"bool#", parts[0], maxsplit=1)[0].strip().rstrip(",")
    if re.match(r"^-?\d+\.?\d*,-?\d+\.?\d*,\d+", head):
        return {"success": True, "data": t}
    return None


def _parse_beidou_http_json_body(text: str) -> dict[str, Any]:
    """
    18gps / ASMX 偶发返回：顶层 JSON 数组、JSON 字符串再包一层、裸轨迹串、或网关 HTML。
    部分环境把两段 JSON 拼在同一字符串里二次编码，json.loads 会报 Extra data；用 raw_decode 只取首段。
    """
    t = (text or "").strip()
    if t.startswith("\ufeff"):
        t = t.lstrip("\ufeff")
    if not t:
        raise ValueError("北斗接口返回空内容")
    head = t[:900].lower()
    if t.lstrip().startswith("<") or "<html" in head or "<!doctype" in head:
        raise ValueError(
            "北斗接口返回了 HTML/XML 而非 JSON，请核对 GPS18_BASE_URL 是否指向 openapi 主机、以及本机出网是否被劫持"
        )

    plain = _plain_track_http_body(t)
    if plain is not None:
        return plain

    try:
        parsed: Any = json.loads(t)
    except json.JSONDecodeError:
        try:
            parsed = _json_decode_loose_embedded(t)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"北斗接口 JSON 解析失败：{e}；正文前 240 字符：{t[:240]!r}") from e

    if isinstance(parsed, str):
        inner = parsed.strip()
        pt = _plain_track_http_body(inner)
        if pt is not None:
            return pt
        try:
            parsed2: Any = json.loads(inner)
        except json.JSONDecodeError:
            try:
                parsed2 = _json_decode_loose_embedded(inner)
            except json.JSONDecodeError as e2:
                raise ValueError(
                    f"北斗接口返回了字符串但二次 JSON 解析失败：{e2}；字符串前 200 字符：{inner[:200]!r}"
                ) from e2
        parsed = parsed2

    if isinstance(parsed, list):
        return {"success": True, "data": parsed}
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, (int, float)) or parsed is None:
        return {
            "success": False,
            "msg": f"北斗接口返回标量根节点（{type(parsed).__name__}：{parsed!r}）",
            "data": {},
        }
    if isinstance(parsed, bool):
        return {"success": parsed, "data": {}}
    raise ValueError(f"北斗接口响应根类型不支持：{type(parsed).__name__}")


@dataclass
class BeidouDevice:
    device_code: str
    device_name: str
    raw: dict[str, Any]


def beidou_row_user_id(row: dict[str, Any]) -> str:
    """Gps18Api::beidouRowUserId"""
    for rk, v in row.items():
        if isinstance(v, (dict, list)) or v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        norm_k = str(rk).lower().replace("_", "").replace("-", "")
        if norm_k == "userid":
            return s
    return ""


def normalize_beidou_macid_input(s: Any) -> str:
    """Gps18Api::normalizeBeidouMacidInput（空白、全角数字）。"""
    t = str(s or "").strip()
    if not t:
        return ""
    t = re.sub(r"\s+", "", t)
    fw = str.maketrans("０１２３４５６７８９", "0123456789")
    return t.translate(fw)


def _beidou_device_ids_equal(a: str, b: str) -> bool:
    a, b = normalize_beidou_macid_input(a), normalize_beidou_macid_input(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if a.isdigit() and b.isdigit():
        return int(a) == int(b)
    return False


def _row_beidou_id_candidates(row: dict[str, Any]) -> list[str]:
    keys = {"sim_id", "sim", "macid", "device_id", "imei"}
    out: list[str] = []
    for rk, v in row.items():
        if not isinstance(v, (str, int, float)) or isinstance(v, bool):
            continue
        vs = str(v).strip()
        if not vs:
            continue
        if str(rk).lower() in keys:
            out.append(vs)
    un = str(row.get("user_name") or "").strip()
    if un.isdigit() and len(un) >= 8:
        out.append(un)
    return list(dict.fromkeys(out))


def find_device_by_macid_in_list(macid: str, devices: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Gps18Api::findDeviceByMacidInList"""
    m = normalize_beidou_macid_input(macid)
    if not m:
        return None
    for row in devices:
        if not isinstance(row, dict):
            continue
        for cand in _row_beidou_id_candidates(row):
            if _beidou_device_ids_equal(m, cand):
                return row
    return None


# 设备真实上报（定位/心跳）；不含 server_time（仅为平台列表刷新时间）
_BEIDOU_DEVICE_ACTIVITY_KEYS = ("heart_time", "datetime", "sys_time")
_BEIDOU_ALL_ACTIVITY_KEYS = _BEIDOU_DEVICE_ACTIVITY_KEYS + ("server_time",)
_BEIDOU_ONLINE_WINDOW_MS = 10 * 60 * 1000
_BEIDOU_POSITION_STALE_MS = 30 * 60 * 1000


def _timestamp_ms(value: Any) -> int:
    """18gps 多为毫秒；秒级时间戳（<1e11）自动乘 1000。"""
    try:
        if value is None or value == "":
            return 0
        v = int(float(value))
        if v <= 0:
            return 0
        if v < 100_000_000_000:
            return v * 1000
        return v
    except (TypeError, ValueError, OverflowError):
        return 0


def beidou_device_activity_ms(raw: dict[str, Any]) -> int:
    """设备侧最近上报时间（毫秒），用于在线/定位时效判定。"""
    data = raw if isinstance(raw, dict) else {}
    best = 0
    for key in _BEIDOU_DEVICE_ACTIVITY_KEYS:
        best = max(best, _timestamp_ms(data.get(key)))
    return best


def beidou_latest_activity_ms(raw: dict[str, Any]) -> int:
    """含 server_time 的最近活动时间（审计/调试）。"""
    data = raw if isinstance(raw, dict) else {}
    best = 0
    for key in _BEIDOU_ALL_ACTIVITY_KEYS:
        best = max(best, _timestamp_ms(data.get(key)))
    return best


def beidou_fetch_map_type() -> str:
    """18gps 设备列表 mapType；高德展示默认 GAODE（GCJ-02）。"""
    mt = (settings.gps18_map_type or "GAODE").strip().upper()
    return mt or "GAODE"


def beidou_online_status_from_raw(
    raw: dict[str, Any], *, window_ms: int = _BEIDOU_ONLINE_WINDOW_MS
) -> str:
    """按设备最近上报时间判断在线（不含 server_time，避免“平台在线但 GPS 已停更”）。"""
    data = raw if isinstance(raw, dict) else {}
    latest = beidou_device_activity_ms(data)
    if latest > 0:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return "online" if now_ms - latest <= int(window_ms) else "offline"
    status_text = str(data.get("status") or "").strip().lower()
    if status_text in {"1", "online", "true"}:
        return "online"
    return "offline"


def beidou_reported_at_display(raw: dict[str, Any]) -> str:
    data = raw if isinstance(raw, dict) else {}
    latest = beidou_device_activity_ms(data)
    if latest > 0:
        return datetime.fromtimestamp(latest / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for key in ("reported_at", "updatetime", "update_time"):
        val = data.get(key)
        if val not in (None, ""):
            return str(val)
    return ""


def merge_beidou_raw(db_raw: Any, api_raw: Any) -> dict[str, Any]:
    base = dict(db_raw) if isinstance(db_raw, dict) else {}
    if isinstance(api_raw, dict) and api_raw:
        base.update(api_raw)
    return base


async def fetch_beidou_live_raw_by_code() -> dict[str, dict[str, Any]]:
    """一次 list_devices，返回 normalize 后 device_code -> 平台最新 raw。"""
    try:
        client = BeidouClient()
        devices = await client.list_devices()
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in devices:
        key = normalize_beidou_macid_input(item.device_code)
        if key and isinstance(item.raw, dict):
            tagged = dict(item.raw)
            tagged.setdefault("_gps18_map_type", beidou_fetch_map_type())
            out[key] = tagged
    return out


def resolve_beidou_raw(
    device: Any,
    live_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """单设备：DB raw 与平台 live raw 合并（内存）。"""
    db_raw = device.raw_payload_json if isinstance(getattr(device, "raw_payload_json", None), dict) else {}
    if str(getattr(device, "vendor", "") or "").lower() != "beidou":
        return db_raw
    api_raw = live_map.get(normalize_beidou_macid_input(getattr(device, "device_code", "")))
    if not api_raw:
        return db_raw
    return merge_beidou_raw(db_raw, api_raw)


async def enrich_beidou_devices_live(
    devices: list[Any],
    *,
    db: Any = None,
    persist: bool = False,
    live_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """将所有北斗设备的 raw_payload_json 与 18gps 实时数据合并（展示/定位统一走实时）。"""
    beidou = [d for d in devices if str(getattr(d, "vendor", "") or "").lower() == "beidou"]
    if not beidou:
        return live_map or {}
    if live_map is None:
        live_map = await fetch_beidou_live_raw_by_code()
    changed = False
    for device in beidou:
        db_raw = device.raw_payload_json if isinstance(device.raw_payload_json, dict) else {}
        merged = resolve_beidou_raw(device, live_map)
        if merged != db_raw:
            device.raw_payload_json = merged
            if persist:
                device.updated_at = datetime.utcnow()
            changed = True
    if persist and changed and db is not None:
        await db.commit()
        for device in beidou:
            await db.refresh(device)
    return live_map


def _coord_out_of_china(lat: float, lng: float) -> bool:
    return lng < 72.004 or lng > 137.8347 or lat < 0.8293 or lat > 55.8271


def bd09_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """百度 BD-09 → 高德 GCJ-02。"""
    lng_f, lat_f = float(lng), float(lat)
    x = lng_f - 0.0065
    y = lat_f - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)
    return z * math.cos(theta), z * math.sin(theta)


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """Gps18Api::wgs84ToGcj02"""
    lng_f, lat_f = float(lng), float(lat)
    if _coord_out_of_china(lat_f, lng_f):
        return lng_f, lat_f
    a = 6378245.0
    ee = 0.00669342162296594323
    d_lat = _transform_lat(lng_f - 105.0, lat_f - 35.0)
    d_lng = _transform_lng(lng_f - 105.0, lat_f - 35.0)
    rad_lat = lat_f / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - ee * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * math.pi)
    d_lng = (d_lng * 180.0) / (a / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lng_f + d_lng, lat_f + d_lat


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def lng_lat_to_amap_gcj02(lng: float, lat: float, map_type_used: str | None) -> tuple[float, float]:
    """将 18gps 坐标转为高德地图 GCJ-02。"""
    mode = ""
    if map_type_used and str(map_type_used).strip():
        mode = str(map_type_used).strip().lower()
    else:
        mode = (settings.gps18_coord_for_amap or "auto").strip().lower()
    if mode in {"", "auto"}:
        mt = beidou_fetch_map_type().lower()
        if mt == "baidu":
            mode = "bd09"
        elif mt in {"gaode", "amap", "google"}:
            mode = "gcj02"
        else:
            mode = "wgs84"
    if mode in {"gcj02", "gcj", "mars", "gaode", "amap", "google"}:
        return float(lng), float(lat)
    if mode in {"bd09", "baidu"}:
        return bd09_to_gcj02(lng, lat)
    return wgs84_to_gcj02(lng, lat)


def beidou_raw_coordinates(raw: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    data = raw if isinstance(raw, dict) else {}
    lng = _to_float_or_none_beidou(data.get("jingdu")) or _to_float_or_none_beidou(data.get("ljingdu"))
    lat = _to_float_or_none_beidou(data.get("weidu")) or _to_float_or_none_beidou(data.get("lweidu"))
    return lng, lat


def _to_float_or_none_beidou(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def beidou_location_for_amap(
    raw: dict[str, Any],
    *,
    stale_after_ms: int = _BEIDOU_POSITION_STALE_MS,
) -> tuple[Optional[float], Optional[float], bool]:
    """返回 (lng, lat, location_stale)；坐标已转为 GCJ-02 供高德使用。"""
    data = raw if isinstance(raw, dict) else {}
    lng, lat = beidou_raw_coordinates(data)
    if lng is None or lat is None:
        return None, None, True
    pos_ms = beidou_device_activity_ms(data)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    stale = pos_ms <= 0 or (now_ms - pos_ms > int(stale_after_ms))
    map_type = str(data.get("_gps18_map_type") or beidou_fetch_map_type() or "GAODE")
    glng, glat = lng_lat_to_amap_gcj02(lng, lat, map_type)
    return glng, glat, stale


def parse_history_point_string(s: str) -> list[dict[str, Any]]:
    """Gps18Api::parseHistoryPointString"""
    s = (s or "").strip()
    if not s:
        return []
    parts = re.split(r";+", s)
    out: list[dict[str, Any]] = []
    for seg in parts:
        seg = seg.strip()
        if not seg:
            continue
        head = re.split(r"bool#", seg, maxsplit=1)[0].strip().rstrip(",")
        comma = head.split(",")
        if len(comma) < 3:
            continue
        lng_s, lat_s, tms_s = comma[0].strip(), comma[1].strip(), comma[2].strip()
        spd = comma[3].strip() if len(comma) > 3 else ""
        crs = comma[4].strip() if len(comma) > 4 else ""
        try:
            lng_v = float(lng_s) if re.match(r"^-?\d", lng_s) else lng_s
            lat_v = float(lat_s) if re.match(r"^-?\d", lat_s) else lat_s
            tms_v = int(tms_s) if tms_s.isdigit() else tms_s
        except ValueError:
            continue
        out.append(
            {
                "lng": lng_v,
                "lat": lat_v,
                "time_ms": tms_v,
                "speed": spd,
                "course": crs,
                "raw": seg,
            }
        )
    return out


def extract_history_data_string(resp: dict[str, Any], depth: int = 0) -> str | None:
    """Gps18Api::extractHistoryDataString（核心分支）。"""
    if depth > 14:
        return None
    if not isinstance(resp, dict) or "data" not in resp:
        return None
    d = resp.get("data")
    if isinstance(d, str):
        t = d.strip()
        return t or None
    if not isinstance(d, dict):
        return None
    pt = d.get("point")
    if isinstance(pt, str) and pt.strip():
        return pt.strip()
    for k in ("Point", "points", "data", "track", "result", "rows", "list"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    z = d.get(0)
    if isinstance(z, str) and z.strip():
        t = z.strip()
        if (t[0] in "{[" and len(t) > 4) or ";" in t or re.match(r"^-?\d+\.?\d*,-?\d+\.?\d*,\d+", t):
            if t[0] in "{[":
                try:
                    j = json.loads(t)
                except json.JSONDecodeError:
                    j = None
                if isinstance(j, (dict, list)):
                    nested = extract_history_data_string({"data": j}, depth + 1)
                    if nested:
                        return nested
            if ";" in t or re.match(r"^-?\d+\.?\d*,-?\d+\.?\d*,\d+", t):
                return t
    for v in d.values():
        if isinstance(v, str) and len(v) >= 8:
            if ";" in v or re.match(r"^-?\d+\.?\d*,-?\d+\.?\d*,\d+", v):
                return v
    for v in d.values():
        if isinstance(v, (dict, list)):
            nested = extract_history_data_string({"data": v}, depth + 1)
            if nested:
                return nested
    return None


def _is_success(data: dict[str, Any]) -> bool:
    return data.get("success") in (True, "true")


def _token_expired_business(data: dict[str, Any]) -> bool:
    code = str(data.get("errorCode") or "")
    return code in ("403", "401")


def _norm_empty(norm: dict[str, Any] | None) -> bool:
    if norm is None or norm.get("error"):
        return True
    pts = norm.get("points")
    return not isinstance(pts, list) or len(pts) == 0


class BeidouClient:
    def __init__(self) -> None:
        self.base_url = (settings.gps18_base_url or "").rstrip("/")
        self.username = (settings.gps18_username or "").strip()
        self.password = (settings.gps18_password or "").strip()

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, text/javascript, */*;q=0.1",
            "User-Agent": "Mozilla/5.0 (compatible; DazongDelivery/1.0)",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{self.base_url}{path}", params=params, headers=headers)
            resp.raise_for_status()
            return _parse_beidou_http_json_body(resp.text)

    async def login(self) -> dict[str, str]:
        if not self.base_url or not self.username or not self.password:
            raise ValueError("北斗配置未完成")
        data = await self._request(
            "/GetDateServices.asmx/loginSystem",
            {
                "LoginName": self.username,
                "LoginPassword": self.password,
                "LoginType": "ENTERPRISE",
                "language": "cn",
                "ISMD5": "0",
                "timeZone": "8",
                "apply": "APP",
            },
        )
        if data.get("success") not in (True, "true"):
            data = await self._request(
                "/GetDateServices.asmx/loginSystem",
                {"name": self.username, "pwd": self.password},
            )
        if data.get("success") not in (True, "true"):
            raise ValueError(str(data.get("msg") or "北斗登录失败"))
        payload = data.get("data") or {}
        unit_id = str(data.get("id") or payload.get("id") or "").strip()
        if not unit_id:
            raise ValueError("北斗登录返回缺少单位ID")
        mds = str(data.get("mds") or payload.get("mds") or "").strip()
        return {"unit_id": unit_id, "mds": mds}

    async def _get_date_with_mds(self, session: dict[str, str], params: dict[str, Any]) -> dict[str, Any]:
        q = {**params, "mds": session["mds"]}
        data = await self._request("/GetDateServices.asmx/GetDate", q)
        if _token_expired_business(data) and self.username:
            session2 = await self.login()
            session.clear()
            session.update(session2)
            q["mds"] = session["mds"]
            data = await self._request("/GetDateServices.asmx/GetDate", q)
        return data

    def _map_type_for_history(self) -> str:
        h = (settings.gps18_history_map_type or "").strip()
        if h:
            return h
        return (settings.gps18_map_type or "").strip()

    def _alternate_history_map_type(self, used: str) -> str | None:
        if not settings.gps18_history_maptype_fallback:
            return None
        u = str(used or "")
        if u == "":
            return "BAIDU"
        if u.upper() == "BAIDU":
            return ""
        return None

    async def _history_normalized_internal_async(
        self, session: dict[str, str], params: dict[str, Any]
    ) -> dict[str, Any]:
        resp = await self._get_date_with_mds(session, params)
        if not _is_success(resp):
            return {"error": str(resp.get("msg") or resp.get("message") or "北斗历史接口失败"), "raw": resp}
        map_used = str(params.get("mapType") or "")
        raw = extract_history_data_string(resp)
        if raw:
            pts = parse_history_point_string(raw)
            return {"points": pts, "may_have_more": len(pts) >= 1000, "mapType_used": map_used}
        alt = self._alternate_history_map_type(map_used)
        if alt is not None:
            p2 = {**params, "mapType": alt}
            resp2 = await self._get_date_with_mds(session, p2)
            if _is_success(resp2):
                raw2 = extract_history_data_string(resp2)
                if raw2:
                    pts = parse_history_point_string(raw2)
                    return {"points": pts, "may_have_more": len(pts) >= 1000, "mapType_used": alt}
        return {"points": [], "may_have_more": False, "mapType_used": map_used}

    async def get_history_m_by_m_utc_new_normalized(
        self, session: dict[str, str], macid: str, from_ms: int, to_ms: int
    ) -> dict[str, Any]:
        """Gps18Api::getHistoryMByMUtcNewNormalized"""
        macid = normalize_beidou_macid_input(macid)
        if not macid:
            return {"error": "macid 为空"}
        fm, tm = int(from_ms), int(to_ms)
        if fm > 0 and tm > 0 and max(fm, tm) < 20_000_000_000:
            fm = int(round(fm * 1000))
            tm = int(round(tm * 1000))
        if tm <= fm:
            return {"error": "结束时间须大于开始时间"}
        play_lbs = "true" if settings.gps18_history_play_lbs else "false"
        method = (settings.gps18_history_method or "").strip() or "getHistoryMByMUtcNew"
        params: dict[str, Any] = {
            "method": method,
            "macid": macid,
            "mapType": self._map_type_for_history(),
            "from": str(fm),
            "to": str(tm),
            "playLBS": play_lbs,
        }
        return await self._history_normalized_internal_async(session, params)

    async def get_history_m_by_m_utc_normalized(
        self, session: dict[str, str], user_id: str, from_ms: int, to_ms: int
    ) -> dict[str, Any]:
        """Gps18Api::getHistoryMByMUtcNormalized"""
        user_id = str(user_id or "").strip()
        if not user_id:
            return {"error": "user_id 为空"}
        fm, tm = int(from_ms), int(to_ms)
        if fm > 0 and tm > 0 and max(fm, tm) < 20_000_000_000:
            fm = int(round(fm * 1000))
            tm = int(round(tm * 1000))
        if tm <= fm:
            return {"error": "结束时间须大于开始时间"}
        play_lbs = "true" if settings.gps18_history_play_lbs else "false"
        method = (settings.gps18_history_method_user or "").strip() or "getHistoryMByMUtc"
        params: dict[str, Any] = {
            "method": method,
            "userID": user_id,
            "mapType": self._map_type_for_history(),
            "from": str(fm),
            "to": str(tm),
            "playLBS": play_lbs,
        }
        return await self._history_normalized_internal_async(session, params)

    async def list_devices(self) -> list[BeidouDevice]:
        session = await self.login()
        map_type = beidou_fetch_map_type()
        data = await self._get_date_with_mds(
            session,
            {
                "method": "getDeviceListByCustomId",
                "id": session["unit_id"],
                "mapType": map_type,
            },
        )
        if data.get("success") not in (True, "true"):
            raise ValueError(str(data.get("msg") or "北斗设备拉取失败"))
        rows = data.get("data") or []
        if rows and isinstance(rows, list) and isinstance(rows[0], dict) and "records" in rows[0]:
            block = rows[0]
            key_map = block.get("key") or {}
            records = block.get("records") or []
            converted = []
            if isinstance(key_map, dict) and isinstance(records, list):
                for rec in records:
                    if not isinstance(rec, list):
                        continue
                    item: dict[str, Any] = {}
                    for name, idx in key_map.items():
                        try:
                            item[str(name)] = rec[int(idx)]
                        except Exception:  # noqa: BLE001
                            continue
                    converted.append(item)
            rows = converted
        devices: list[BeidouDevice] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = self._pick_code(row)
            if not code:
                continue
            name = str(
                row.get("car_no")
                or row.get("device_name")
                or row.get("sim")
                or row.get("macid")
                or code
            ).strip()
            tagged = dict(row)
            tagged["_gps18_map_type"] = map_type
            devices.append(BeidouDevice(device_code=code, device_name=name, raw=tagged))
        return devices

    @staticmethod
    def _pick_code(row: dict[str, Any]) -> str:
        for key in ("macid", "sim_id", "sim", "device_id", "imei", "user_name"):
            val = str(row.get(key) or "").strip()
            if val:
                return val
        return ""

    async def fetch_history_track_resolved(
        self, macid: str, user_id_bound: str, start_unix: int, end_unix: int
    ) -> dict[str, Any]:
        """
        对齐 sxw smart_logistics_bind.get_history_track 的北斗请求链。
        返回 {"points": [...内部 time_ms/lng/lat/speed...], "mapType_used": str} 或 {"error": str}。
        """
        session = await self.login()
        mac_api = normalize_beidou_macid_input(macid)
        uid_bound = (user_id_bound or "").strip()

        norm: dict[str, Any] | None = None
        if mac_api:
            norm = await self.get_history_m_by_m_utc_new_normalized(session, mac_api, start_unix, end_unix)
        if _norm_empty(norm) and uid_bound:
            norm = await self.get_history_m_by_m_utc_normalized(session, uid_bound, start_unix, end_unix)

        if _norm_empty(norm) and mac_api:
            try:
                devs = await self.list_devices()
            except ValueError:
                devs = []
            raw_rows = [d.raw for d in devs if isinstance(d.raw, dict)]
            dev = find_device_by_macid_in_list(mac_api, raw_rows)
            if dev is not None:
                uid_list = beidou_row_user_id(dev)
                if uid_list and (not uid_bound or uid_list != uid_bound):
                    norm = await self.get_history_m_by_m_utc_normalized(session, uid_list, start_unix, end_unix)

        if _norm_empty(norm):
            return {"error": str((norm or {}).get("error") or "轨迹查询失败")}
        return norm or {"error": "轨迹查询失败"}
