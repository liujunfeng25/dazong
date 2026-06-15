from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

# 精创 monitorTime 为 Unix 时间戳（UTC）；展示统一转北京时间
_CN_TZ = ZoneInfo("Asia/Shanghai")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("list", "records", "rows", "dataList", "items"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
    return []


def _first_str(*values: Any) -> str:
    for v in values:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _device_guid(device: dict[str, Any]) -> str:
    return _first_str(
        device.get("deviceGuid"),
        device.get("guid"),
        device.get("GUID"),
        device.get("sn"),
        device.get("deviceSn"),
    )


def normalize_device_row(raw: dict[str, Any]) -> dict[str, Any]:
    guid = _device_guid(raw)
    return {
        "sn": guid,
        "deviceGuid": guid,
        "device_name": _first_str(raw.get("deviceName"), raw.get("name")),
        "device_types": _first_str(raw.get("deviceType"), raw.get("deviceTypes"), raw.get("model")),
        "device_model": _first_str(raw.get("deviceModel"), raw.get("model")),
        "time_code": "",
        "last_comm_time": _first_str(raw.get("lastCommTime"), raw.get("lastCommunicationTime")),
    }


def normalize_device_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    rows = _as_list(data)
    if not rows and isinstance(data, dict):
        rows = _as_list(data)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = normalize_device_row(raw)
        if row["sn"] and row["sn"] not in seen:
            seen.add(row["sn"])
            out.append(row)
    return out


def _pick_number(row: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key not in row:
            continue
        val = row.get(key)
        if val is None or val == "":
            continue
        parsed = _parse_sensor_number(val)
        if parsed is not None:
            return parsed
    return None


def _format_elitech_timestamp(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        ts = int(value)
        if ts > 1_000_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return ""


def _parse_sensor_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    num = ""
    for ch in text:
        if ch.isdigit() or ch in ".-":
            num += ch
        elif num:
            break
    if not num or num in ("-", "."):
        return None
    try:
        return float(num)
    except ValueError:
        return None


def normalize_realtime_row(raw: dict[str, Any]) -> dict[str, Any]:
    row = _as_dict(raw)
    temp = _pick_number(
        row, "temperature", "temp", "probeTemperature", "t1", "value1", "tmp1", "tmp2"
    )
    hum = _pick_number(row, "humidity", "hum", "probeHumidity", "h1", "value2", "hum1", "hum2")
    online = row.get("onlineStatus", row.get("status", row.get("deviceStatus")))
    status = 1
    if online is not None:
        s = str(online).lower()
        if s in ("0", "online", "true", "on", "在线"):
            status = 0
        elif s in ("1", "offline", "false", "off", "离线"):
            status = 1
    last_ts = row.get("monitorTime", row.get("lastDataTime", row.get("lastSessionTime")))
    report_date = _format_elitech_timestamp(last_ts)
    if report_date and last_ts is not None:
        try:
            ts = int(last_ts)
            if ts > 1_000_000_000_000:
                ts //= 1000
            if time.time() - ts < 900:
                status = 0
        except (TypeError, ValueError):
            pass
    warning = _first_str(row.get("warning"), row.get("alarm"), row.get("alarmInfo"))
    return {
        "temperature": str(temp) if temp is not None else "",
        "humidity": str(hum) if hum is not None else "",
        "status": status,
        "electricity": row.get("electricity", row.get("battery", row.get("power"))),
        "warning": warning,
        "date": _first_str(
            row.get("date"),
            row.get("time"),
            row.get("recordTime"),
            row.get("dataTime"),
            report_date,
        ),
        "raw": row,
    }


def normalize_realtime_payload(payload: dict[str, Any], *, device_guid: str) -> dict[str, Any]:
    data = payload.get("data")
    rows: list[Any] = []
    if isinstance(data, dict):
        rows = _as_list(data)
        if not rows:
            rows = [data]
    elif isinstance(data, list):
        rows = data
    item = rows[0] if rows else {}
    if isinstance(item, dict) and not _device_guid(item):
        item = {**item, "deviceGuid": device_guid}
    return normalize_realtime_row(_as_dict(item))


def normalize_curve_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        curve = data
    elif isinstance(data, list) and data:
        curve = _as_dict(data[0])
    else:
        curve = {}
    dates = curve.get("dateList") or curve.get("timeList") or curve.get("dates") or []
    temps = curve.get("temperatureList") or curve.get("tempList") or []
    hums = curve.get("humidityList") or curve.get("humList") or []
    if not dates and isinstance(curve.get("records"), list):
        records = curve["records"]
        dates, temps, hums = [], [], []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            dates.append(_first_str(rec.get("date"), rec.get("time"), rec.get("recordTime")))
            t = _pick_number(rec, "temperature", "temp")
            h = _pick_number(rec, "humidity", "hum")
            temps.append(t if t is not None else None)
            hums.append(h if h is not None else None)
    return {
        "dateList": dates,
        "temperatureList": temps,
        "humidityList": hums,
    }


def curve_from_history_page(page: dict[str, Any]) -> dict[str, Any]:
    rows = [r for r in (page.get("dataList") or []) if isinstance(r, dict)]
    rows.sort(key=lambda r: str(r.get("date") or ""))
    dates: list[str] = []
    temps: list[Optional[float]] = []
    hums: list[Optional[float]] = []
    for row in rows:
        dates.append(_first_str(row.get("date")))
        t = _parse_sensor_number(row.get("temperature"))
        h = _parse_sensor_number(row.get("humidity"))
        temps.append(t)
        hums.append(h)
    return {"dateList": dates, "temperatureList": temps, "humidityList": hums}


def normalize_history_page(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    rows: list[Any] = []
    total = 0
    if isinstance(data, dict):
        rows = _as_list(data)
        total = int(data.get("total") or data.get("count") or len(rows) or 0)
    elif isinstance(data, list):
        rows = data
        total = len(rows)
    out_rows = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        rt = normalize_realtime_row(raw)
        out_rows.append(
            {
                "date": rt["date"],
                "temperature": rt["temperature"],
                "humidity": rt["humidity"],
            }
        )
    return {"dataList": out_rows, "count": total, "rows": len(out_rows), "page": 0}


def normalize_warning_row(raw: dict[str, Any]) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "id": row.get("id"),
        "wrId": row.get("wrId") or row.get("alarmId") or row.get("alarmType"),
        "content": _first_str(row.get("content"), row.get("alarmContent"), row.get("message")),
        "wrData": row.get("wrData") or row.get("alarmValue") or row.get("value"),
        "date": _first_str(row.get("date"), row.get("time"), row.get("alarmTime")),
    }


def normalize_warnings_page(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    rows: list[Any] = []
    total = 0
    if isinstance(data, dict):
        rows = _as_list(data)
        total = int(data.get("total") or data.get("count") or len(rows) or 0)
    elif isinstance(data, list):
        rows = data
        total = len(rows)
    return {
        "dataList": [normalize_warning_row(r) for r in rows if isinstance(r, dict)],
        "count": total,
    }


def history_stats_from_rows(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not rows:
        return None
    temps = []
    hums = []
    for r in rows:
        t = _pick_number(r, "temperature")
        h = _pick_number(r, "humidity")
        if t is not None:
            temps.append(t)
        if h is not None:
            hums.append(h)
    stats = []
    if temps:
        stats.append(
            {
                "text": "温度℃",
                "key": "temperature",
                "minValue": str(min(temps)),
                "maxValue": str(max(temps)),
                "averageValue": str(round(sum(temps) / len(temps), 1)),
            }
        )
    if hums:
        stats.append(
            {
                "text": "湿度%RH",
                "key": "humidity",
                "minValue": str(min(hums)),
                "maxValue": str(max(hums)),
                "averageValue": str(round(sum(hums) / len(hums), 1)),
            }
        )
    return {"count": len(rows), "printStsList": stats} if stats else None
