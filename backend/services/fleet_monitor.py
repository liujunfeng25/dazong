import asyncio
import math
import random
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import (
    DeliveryDevice,
    DeliveryVehicle,
    DeliveryVehicleDeviceBinding,
    DeliveryWarehouse,
    DeliveryWarehouseDeviceBinding,
    DeliveryWarehouseElitechBinding,
    User,
)
from services.delivery_warehouse_elitech import (
    elitech_realtime_fields_empty,
    elitech_realtime_map_for_sns,
)
from services.beidou_client import (
    BeidouClient,
    beidou_location_for_amap,
    beidou_online_status_from_raw,
    beidou_reported_at_display,
    beidou_row_user_id,
    enrich_beidou_devices_live,
    lng_lat_to_amap_gcj02,
    normalize_beidou_macid_input,
)


BEIJING_FLEET_BOUNDS = {
    "min_lng": 115.35,
    "max_lng": 117.65,
    "min_lat": 39.35,
    "max_lat": 41.10,
}
from services.ys7_client import YS7Client
from services.ys7_meta import is_ys7_battery_device, ys7_battery_fields_from_raw

_HISTORY_JITTER_SEC = 3


def _to_float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def device_location(raw_payload: dict[str, Any], vendor: str) -> tuple[Optional[float], Optional[float]]:
    raw = _as_dict(raw_payload)
    if vendor == "beidou":
        lng, lat, _stale = beidou_location_for_amap(raw)
        return lng, lat

    camera = _as_dict(raw.get("camera"))
    device = _as_dict(raw.get("device"))
    lng = (
        _to_float_or_none(camera.get("longitude"))
        or _to_float_or_none(device.get("longitude"))
        or _to_float_or_none(camera.get("lng"))
        or _to_float_or_none(device.get("lng"))
    )
    lat = (
        _to_float_or_none(camera.get("latitude"))
        or _to_float_or_none(device.get("latitude"))
        or _to_float_or_none(camera.get("lat"))
        or _to_float_or_none(device.get("lat"))
    )
    return lng, lat


def device_online_status(raw_payload: dict[str, Any], vendor: str) -> str:
    raw = _as_dict(raw_payload)
    explicit_keys = ("online", "is_online", "isOnline", "onlineStatus", "status")
    if vendor == "ys7":
        c = _as_dict(raw.get("camera"))
        d = _as_dict(raw.get("device"))
        for src in (c, d, raw):
            for k in explicit_keys:
                val = src.get(k)
                if val is None:
                    continue
                text = str(val).strip().lower()
                if text in {"1", "true", "online", "on"}:
                    return "online"
                if text in {"0", "false", "offline", "off"}:
                    return "offline"
        return "offline"

    return beidou_online_status_from_raw(raw)


def is_beijing_fleet_coordinate(lng: Optional[float], lat: Optional[float]) -> bool:
    if lng is None or lat is None:
        return False
    try:
        lng_f = float(lng)
        lat_f = float(lat)
    except (TypeError, ValueError):
        return False
    return (
        BEIJING_FLEET_BOUNDS["min_lng"] <= lng_f <= BEIJING_FLEET_BOUNDS["max_lng"]
        and BEIJING_FLEET_BOUNDS["min_lat"] <= lat_f <= BEIJING_FLEET_BOUNDS["max_lat"]
    )


def _device_payload(device: DeliveryDevice) -> dict[str, Any]:
    raw = device.raw_payload_json or {}
    lng, lat = device_location(raw, str(device.vendor or ""))
    payload: dict[str, Any] = {
        "id": int(device.id),
        "device_type": device.device_type,
        "vendor": device.vendor,
        "device_code": device.device_code,
        "device_name": device.device_name,
        "channel_no": int(device.channel_no or 0),
        "online_status": device_online_status(raw, str(device.vendor or "")),
        "lng": lng,
        "lat": lat,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
    }
    if str(device.vendor or "").lower() == "ys7":
        payload.update(_ys7_meta_fields(device))
    return payload


async def build_fleet_monitor_vehicles(db: AsyncSession, *, delivery_id: Optional[int] = None) -> dict[str, Any]:
    stmt = select(DeliveryVehicle).where(DeliveryVehicle.status == "active").order_by(DeliveryVehicle.id.desc())
    if delivery_id is not None:
        stmt = stmt.where(DeliveryVehicle.delivery_id == int(delivery_id))
    vehicles = (await db.scalars(stmt)).all()
    if not vehicles:
        return {"vehicles": [], "summary": {"total": 0, "online": 0, "offline": 0, "unlocated": 0, "cameras": 0}}

    vehicle_ids = [int(v.id) for v in vehicles]
    delivery_ids = sorted({int(v.delivery_id) for v in vehicles})
    users = (await db.scalars(select(User).where(User.id.in_(delivery_ids)))).all() if delivery_ids else []
    user_map = {int(u.id): u for u in users}

    rows = (
        await db.execute(
            select(DeliveryVehicleDeviceBinding.vehicle_id, DeliveryDevice)
            .join(DeliveryDevice, DeliveryDevice.id == DeliveryVehicleDeviceBinding.device_id)
            .where(DeliveryVehicleDeviceBinding.vehicle_id.in_(vehicle_ids))
            .order_by(DeliveryVehicleDeviceBinding.id.asc())
        )
    ).all()
    devices_by_vehicle: dict[int, list[DeliveryDevice]] = {}
    for vehicle_id, device in rows:
        devices_by_vehicle.setdefault(int(vehicle_id), []).append(device)

    all_beidou = [
        d
        for devs in devices_by_vehicle.values()
        for d in devs
        if str(d.vendor or "").lower() == "beidou"
    ]
    if all_beidou:
        await enrich_beidou_devices_live(all_beidou, db=db, persist=False)

    out: list[dict[str, Any]] = []
    online = offline = unlocated = camera_total = 0
    for vehicle in vehicles:
        devices = devices_by_vehicle.get(int(vehicle.id), [])
        beidou_devices = [d for d in devices if str(d.vendor) == "beidou"]
        cameras = sorted(
            [d for d in devices if str(d.vendor) == "ys7" and str(d.device_type) == "camera"],
            key=lambda d: (int(d.channel_no or 0), int(d.id)),
        )
        beidou = beidou_devices[0] if beidou_devices else None
        raw = beidou.raw_payload_json if beidou and isinstance(beidou.raw_payload_json, dict) else {}
        raw_lng, raw_lat = device_location(raw, "beidou") if beidou else (None, None)
        coord_valid = bool(beidou and is_beijing_fleet_coordinate(raw_lng, raw_lat))
        lng, lat = (raw_lng, raw_lat) if coord_valid else (None, None)
        status = device_online_status(raw, "beidou") if beidou else "unbound"
        if lng is None or lat is None:
            unlocated += 1
        elif status == "online":
            online += 1
        elif status == "offline":
            offline += 1
        camera_total += len(cameras)
        delivery_user = user_map.get(int(vehicle.delivery_id))
        out.append(
            {
                "id": int(vehicle.id),
                "vehicle_no": vehicle.vehicle_no,
                "vehicle_model": vehicle.vehicle_model or "",
                "driver_name": vehicle.driver_name or "",
                "delivery_id": int(vehicle.delivery_id),
                "delivery_name": (delivery_user.company_name or delivery_user.username if delivery_user else "") or "",
                "lng": float(lng) if lng is not None else None,
                "lat": float(lat) if lat is not None else None,
                "raw_lng": float(raw_lng) if raw_lng is not None else None,
                "raw_lat": float(raw_lat) if raw_lat is not None else None,
                "coordinate_valid": bool(coord_valid),
                "coordinate_status": "ok"
                if coord_valid
                else ("unbound" if not beidou else ("out_of_beijing" if raw_lng is not None and raw_lat is not None else "missing")),
                "coordinate_hint": ""
                if coord_valid
                else (
                    "未绑定北斗设备"
                    if not beidou
                    else ("北斗坐标不在北京业务范围内，已暂不在地图展示" if raw_lng is not None and raw_lat is not None else "暂无北斗坐标")
                ),
                "online_status": status,
                "source": "beidou" if beidou else "",
                "beidou_device": _device_payload(beidou) if beidou else None,
                "device_id": int(beidou.id) if beidou else None,
                "device_code": beidou.device_code if beidou else "",
                "device_label": (beidou.device_name or beidou.device_code if beidou else "") or "",
                "speed": raw.get("speed"),
                "course": raw.get("course") or raw.get("direction") or "",
                "reported_at": beidou_reported_at_display(raw),
                "updated_at": beidou.updated_at.isoformat() if beidou and beidou.updated_at else None,
                "cameras": [_device_payload(d) for d in cameras[:3]],
            }
        )

    return {
        "vehicles": out,
        "summary": {
            "total": len(out),
            "online": online,
            "offline": offline,
            "unlocated": unlocated,
            "cameras": camera_total,
        },
        "refreshed_at": datetime.utcnow().isoformat(),
    }


async def load_fleet_vehicle_or_404(
    db: AsyncSession, vehicle_id: int, *, delivery_id: Optional[int] = None
) -> DeliveryVehicle:
    stmt = select(DeliveryVehicle).where(DeliveryVehicle.id == int(vehicle_id), DeliveryVehicle.status == "active")
    if delivery_id is not None:
        stmt = stmt.where(DeliveryVehicle.delivery_id == int(delivery_id))
    vehicle = await db.scalar(stmt)
    if not vehicle:
        raise HTTPException(404, "车辆不存在或无权限查看")
    return vehicle


async def load_vehicle_beidou_device_or_404(
    db: AsyncSession, vehicle_id: int, *, delivery_id: Optional[int] = None
) -> DeliveryDevice:
    await load_fleet_vehicle_or_404(db, vehicle_id, delivery_id=delivery_id)
    stmt = (
        select(DeliveryDevice)
        .join(DeliveryVehicleDeviceBinding, DeliveryVehicleDeviceBinding.device_id == DeliveryDevice.id)
        .where(
            DeliveryVehicleDeviceBinding.vehicle_id == int(vehicle_id),
            DeliveryDevice.vendor == "beidou",
        )
        .order_by(DeliveryVehicleDeviceBinding.id.asc())
    )
    if delivery_id is not None:
        stmt = stmt.where(DeliveryVehicleDeviceBinding.delivery_id == int(delivery_id))
    device = await db.scalar(stmt)
    if not device:
        raise HTTPException(400, "该车辆未绑定北斗设备，无法查询历史轨迹")
    return device


async def load_camera_device_or_404(
    db: AsyncSession, device_id: int, *, delivery_id: Optional[int] = None
) -> DeliveryDevice:
    stmt = select(DeliveryDevice).where(
        DeliveryDevice.id == int(device_id),
        DeliveryDevice.vendor == "ys7",
        DeliveryDevice.device_type == "camera",
    )
    if delivery_id is not None:
        stmt = stmt.where(DeliveryDevice.delivery_id == int(delivery_id))
    device = await db.scalar(stmt)
    if not device:
        raise HTTPException(404, "摄像头不存在或无权限查看")
    return device


async def build_camera_live_url_payload(device: DeliveryDevice) -> dict[str, str]:
    """直播统一走 EZOPEN + EZUIKit（与 sxw 一致）；电池机先唤醒再取 ezopen 地址。"""
    client = YS7Client()
    serial = str(device.device_code or "").strip()
    ch = int(device.channel_no or 1)
    is_battery = is_ys7_battery_device(device)
    supports_ptz = ys7_device_supports_ptz(device)

    if settings.ys7_live_use_ezopen:
        try:
            await client.try_live_video_open(serial, ch)
            if is_battery:
                delay = float(settings.ys7_battery_wake_seconds or 0)
                if delay > 0:
                    await asyncio.sleep(delay)
            token = await client.get_access_token()
            ez_url = YS7Client.build_ezopen_live_url(serial, ch, 2)
            if not ez_url:
                raise HTTPException(400, "无法拼装萤石 EZOPEN 地址")
            return {
                "hls": ez_url,
                "ys7_play_mode": "ezuikit",
                "ys7_access_token": token,
                "ys7_battery_camera": is_battery,
                "ys7_supports_ptz": supports_ptz,
            }
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                502, "萤石直播准备失败：当前网络无法连接萤石开放平台，请稍后重试或检查服务器出网策略"
            ) from e

    try:
        hls_url = await client.get_live_address_hls(
            serial, ch, 2, wake_first=is_battery
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            502, "萤石直播地址获取失败：当前网络无法连接萤石开放平台，请稍后重试或检查服务器出网策略"
        ) from e
    return {
        "hls": hls_url,
        "ys7_play_mode": "hls",
        "ys7_access_token": "",
        "ys7_battery_camera": is_battery,
        "ys7_supports_ptz": supports_ptz,
    }


def _ys7_meta_fields(device: DeliveryDevice) -> dict[str, Any]:
    raw_payload = device.raw_payload_json if isinstance(device.raw_payload_json, dict) else {}
    dev = raw_payload.get("device") if isinstance(raw_payload.get("device"), dict) else raw_payload
    parent = str((dev or {}).get("parentCategory") or "").strip()
    model = str((dev or {}).get("model") or (dev or {}).get("deviceType") or "").strip()
    if parent == "BatteryCamera":
        power_kind, power_label = "battery", "电池机"
    elif parent in {"IPC", "NVR", "DVR", "HCVR", "SD"}:
        power_kind, power_label = "wired", "有线机"
    elif parent:
        power_kind, power_label = "other", parent
    else:
        power_kind, power_label = "unknown", "未知"
    meta = {
        "ys7_power_kind": power_kind,
        "ys7_power_label": power_label,
        "ys7_model": model or None,
        "ys7_supports_ptz": power_kind == "wired",
    }
    meta.update(ys7_battery_fields_from_raw(raw_payload, power_kind=power_kind))
    return meta


def ys7_device_supports_ptz(device: DeliveryDevice) -> bool:
    """仅有线萤石 IPC 等支持云台；电池机不支持。"""
    if str(device.vendor or "").lower() != "ys7" or str(device.device_type) != "camera":
        return False
    return _ys7_meta_fields(device).get("ys7_supports_ptz") is True


async def control_ys7_camera_ptz(
    device: DeliveryDevice,
    *,
    action: str,
    direction: int,
    speed: int = 1,
) -> dict[str, str]:
    if not ys7_device_supports_ptz(device):
        raise HTTPException(400, "该设备不支持云台控制（仅有线萤石摄像头支持）")
    act = str(action or "").strip().lower()
    if act not in {"start", "stop"}:
        raise HTTPException(400, "action 须为 start 或 stop")
    client = YS7Client()
    serial = str(device.device_code or "").strip()
    ch = int(device.channel_no or 1)
    spd = int(speed)
    try:
        if act == "start":
            await client.ptz_start(serial, ch, int(direction), spd)
        else:
            await client.ptz_stop(serial, ch, int(direction), spd)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            502, "萤石云台控制失败：当前网络无法连接萤石开放平台，请稍后重试"
        ) from e
    return {"message": "ok"}


def _history_time_to_unix_seconds(tms: Any) -> int:
    try:
        if isinstance(tms, str) and tms.strip().isdigit():
            v = int(tms.strip())
        elif isinstance(tms, (int, float)):
            v = int(tms)
        else:
            return 0
    except (ValueError, TypeError, OverflowError):
        return 0
    if v > 20_000_000_000:
        v //= 1000
    return v


def _history_haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _history_build_output_points(raw_points: list[dict[str, Any]], map_type_used: Optional[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in raw_points:
        if not isinstance(p, dict):
            continue
        try:
            lng = float(p.get("lng"))
            lat = float(p.get("lat"))
        except (TypeError, ValueError):
            continue
        glng, glat = lng_lat_to_amap_gcj02(lng, lat, map_type_used)
        mt = _history_time_to_unix_seconds(p.get("time_ms"))
        if mt <= 0:
            continue
        try:
            spd = float(p.get("speed")) if p.get("speed") not in (None, "") else 0.0
        except (TypeError, ValueError):
            spd = 0.0
        out.append({"lng": glng, "lat": glat, "monitorTime": mt, "speed": spd, "course": str(p.get("course") or "").strip()})
    out.sort(key=lambda x: int(x.get("monitorTime") or 0))
    return out


def _history_dedupe(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not points:
        return []
    pts = sorted(points, key=lambda x: int(x.get("monitorTime") or 0))
    out: list[dict[str, Any]] = []
    for p in pts:
        if not out:
            out.append(p)
            continue
        q = out[-1]
        if (
            round(float(q["lng"]), 6) == round(float(p["lng"]), 6)
            and round(float(q["lat"]), 6) == round(float(p["lat"]), 6)
            and abs(int(p["monitorTime"]) - int(q["monitorTime"])) <= _HISTORY_JITTER_SEC
        ):
            continue
        out.append(p)
    return out


def _history_merge_stationary(points: list[dict[str, Any]], merge_m: float) -> list[dict[str, Any]]:
    if merge_m <= 0 or len(points) < 2:
        return points
    pts = sorted(points, key=lambda x: int(x.get("monitorTime") or 0))
    out: list[dict[str, Any]] = [pts[0]]
    for p in pts[1:]:
        prev = out[-1]
        d = _history_haversine_m(float(prev["lng"]), float(prev["lat"]), float(p["lng"]), float(p["lat"]))
        if d < merge_m:
            out[-1] = p
            continue
        out.append(p)
    return out


def _history_truncate_latest(points: list[dict[str, Any]], max_n: int) -> list[dict[str, Any]]:
    if max_n <= 0 or len(points) <= max_n:
        return points
    pts = sorted(points, key=lambda x: int(x.get("monitorTime") or 0))
    return pts[-max_n:]


def _history_demo_points(start_unix: int, end_unix: int) -> list[dict[str, Any]]:
    s = min(int(start_unix), int(end_unix))
    e = max(int(start_unix), int(end_unix))
    if e <= s:
        e = s + 3600
    span = max(e - s, 3600)
    n = min(80, max(10, span // 180))
    base_lng, base_lat = 116.397428, 39.90923
    out: list[dict[str, Any]] = []
    for i in range(n):
        t = s + int(span * i / max(1, n - 1))
        dlng = (i / max(1, n - 1)) * 0.018 + random.uniform(-0.0004, 0.0004)
        dlat = math.sin(i / 3.0) * 0.003 + (i / max(1, n - 1)) * 0.008
        out.append({"lng": base_lng + dlng, "lat": base_lat + dlat, "monitorTime": t, "speed": round(random.uniform(0, 45), 1), "course": ""})
    return out


async def build_beidou_history_track_payload(
    dev: DeliveryDevice, *, start_time: int, end_time: int, force_demo: bool = False
) -> dict[str, Any]:
    st = int(start_time)
    et = int(end_time)
    if st > 20_000_000_000:
        st //= 1000
    if et > 20_000_000_000:
        et //= 1000
    if et <= st:
        raise HTTPException(400, "结束时间须大于开始时间")

    max_span = int(settings.beidou_history_max_span_seconds)
    if et - st > max_span:
        detail = f"查询跨度不能超过 {max_span // 86400} 天" if max_span >= 86400 else f"查询跨度不能超过 {max(1, max_span // 3600)} 小时"
        raise HTTPException(400, detail)

    if force_demo:
        return {"points": _history_demo_points(st, et), "demo": True, "may_have_more": False, "mapType_used": None}

    raw = dev.raw_payload_json or {}
    mac = (dev.device_code or "").strip()
    uid = beidou_row_user_id(raw)
    try:
        client = BeidouClient()
        norm = await client.fetch_history_track_resolved(mac, uid, st, et)
    except ValueError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"北斗历史接口失败：{e}") from e

    if isinstance(norm, dict) and norm.get("error"):
        raise HTTPException(502, str(norm["error"]))
    raw_pts = norm.get("points") if isinstance(norm, dict) else None
    if not isinstance(raw_pts, list):
        raw_pts = []
    map_used = norm.get("mapType_used") if isinstance(norm, dict) else None
    built = _history_build_output_points(raw_pts, map_used)
    built = _history_dedupe(built)
    merge_m = float(settings.beidou_history_merge_meters or 0.0)
    if merge_m > 0:
        built = _history_merge_stationary(built, merge_m)
    built = _history_truncate_latest(built, int(settings.beidou_history_max_points))
    return {"points": built, "demo": False, "may_have_more": bool(norm.get("may_have_more")) if isinstance(norm, dict) else False, "mapType_used": map_used}


# ===== Warehouse =====

async def build_fleet_monitor_warehouses(
    db: AsyncSession, *, delivery_id: Optional[int] = None
) -> dict[str, Any]:
    stmt = (
        select(DeliveryWarehouse)
        .where(DeliveryWarehouse.status == "active")
        .order_by(DeliveryWarehouse.id.desc())
    )
    if delivery_id is not None:
        stmt = stmt.where(DeliveryWarehouse.delivery_id == int(delivery_id))
    warehouses = (await db.scalars(stmt)).all()
    if not warehouses:
        return {"warehouses": [], "summary": {"total": 0, "cameras": 0}, "refreshed_at": datetime.utcnow().isoformat()}

    warehouse_ids = [int(w.id) for w in warehouses]
    delivery_ids = sorted({int(w.delivery_id) for w in warehouses})
    users = (await db.scalars(select(User).where(User.id.in_(delivery_ids)))).all() if delivery_ids else []
    user_map = {int(u.id): u for u in users}

    rows = (
        await db.execute(
            select(DeliveryWarehouseDeviceBinding.warehouse_id, DeliveryDevice)
            .join(DeliveryDevice, DeliveryDevice.id == DeliveryWarehouseDeviceBinding.device_id)
            .where(DeliveryWarehouseDeviceBinding.warehouse_id.in_(warehouse_ids))
            .order_by(DeliveryWarehouseDeviceBinding.id.asc())
        )
    ).all()
    cameras_by_warehouse: dict[int, list[DeliveryDevice]] = {}
    for wid, device in rows:
        if str(device.vendor) == "ys7" and str(device.device_type) == "camera":
            cameras_by_warehouse.setdefault(int(wid), []).append(device)

    elitech_rows = (
        await db.scalars(
            select(DeliveryWarehouseElitechBinding).where(
                DeliveryWarehouseElitechBinding.warehouse_id.in_(warehouse_ids)
            )
        )
    ).all()
    elitech_map = {int(b.warehouse_id): b for b in elitech_rows}
    rt_map = await elitech_realtime_map_for_sns(
        [str(b.elitech_sn) for b in elitech_rows if b.elitech_sn]
    )

    out: list[dict[str, Any]] = []
    camera_total = 0
    for w in warehouses:
        cameras = sorted(
            cameras_by_warehouse.get(int(w.id), []),
            key=lambda d: (int(d.channel_no or 0), int(d.id)),
        )
        camera_total += len(cameras)
        delivery_user = user_map.get(int(w.delivery_id))
        binding = elitech_map.get(int(w.id))
        sn = str(binding.elitech_sn) if binding and binding.elitech_sn else ""
        if binding and sn:
            rt = rt_map.get(sn, elitech_realtime_fields_empty())
            elitech = {
                "elitech_bound": True,
                "elitech_sn": sn,
                "elitech_device_name": str(binding.device_name or ""),
                "elitech_temperature": str(rt.get("elitech_temperature") or ""),
                "elitech_humidity": str(rt.get("elitech_humidity") or ""),
                "elitech_online": rt.get("elitech_online"),
            }
        else:
            elitech = {
                "elitech_bound": False,
                "elitech_sn": "",
                "elitech_device_name": "",
                **elitech_realtime_fields_empty(),
            }
        out.append(
            {
                "id": int(w.id),
                "name": w.name,
                "address": w.address or "",
                "lng": float(w.lng) if w.lng is not None else None,
                "lat": float(w.lat) if w.lat is not None else None,
                "status": w.status,
                "delivery_id": int(w.delivery_id),
                "delivery_name": (
                    (delivery_user.company_name or delivery_user.username) if delivery_user else ""
                ) or "",
                "cameras": [_device_payload(d) for d in cameras],
                **elitech,
            }
        )

    return {
        "warehouses": out,
        "summary": {"total": len(out), "cameras": camera_total},
        "refreshed_at": datetime.utcnow().isoformat(),
    }


async def load_warehouse_or_404(
    db: AsyncSession, warehouse_id: int, *, delivery_id: Optional[int] = None
) -> DeliveryWarehouse:
    stmt = select(DeliveryWarehouse).where(DeliveryWarehouse.id == int(warehouse_id))
    if delivery_id is not None:
        stmt = stmt.where(DeliveryWarehouse.delivery_id == int(delivery_id))
    row = await db.scalar(stmt)
    if not row:
        raise HTTPException(404, "仓库不存在")
    return row


async def assert_device_not_bound_elsewhere_for_warehouse(
    db: AsyncSession, device_id: int
) -> None:
    """绑定到仓库前：确保该设备未绑车辆、未绑其他仓库。"""
    vbind = await db.scalar(
        select(DeliveryVehicleDeviceBinding).where(DeliveryVehicleDeviceBinding.device_id == int(device_id))
    )
    if vbind is not None:
        raise HTTPException(400, "该摄像头已绑定车辆，请先在车辆管理中解绑")
    wbind = await db.scalar(
        select(DeliveryWarehouseDeviceBinding).where(DeliveryWarehouseDeviceBinding.device_id == int(device_id))
    )
    if wbind is not None:
        wname_row = await db.scalar(
            select(DeliveryWarehouse).where(DeliveryWarehouse.id == int(wbind.warehouse_id))
        )
        wname = wname_row.name if wname_row else "其他仓库"
        raise HTTPException(400, f"该摄像头已绑定仓库《{wname}》，请先解绑")


async def assert_device_not_bound_to_warehouse_for_vehicle(
    db: AsyncSession, device_id: int
) -> None:
    """绑定到车辆前：确保该设备未绑任一仓库。"""
    wbind = await db.scalar(
        select(DeliveryWarehouseDeviceBinding).where(DeliveryWarehouseDeviceBinding.device_id == int(device_id))
    )
    if wbind is not None:
        wname_row = await db.scalar(
            select(DeliveryWarehouse).where(DeliveryWarehouse.id == int(wbind.warehouse_id))
        )
        wname = wname_row.name if wname_row else "仓库"
        raise HTTPException(400, f"该摄像头已绑定仓库《{wname}》，请先在仓库管理中解绑")
