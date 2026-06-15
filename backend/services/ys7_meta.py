from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import DeliveryDevice


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_battery_percent_from_status(status_data: dict[str, Any]) -> Optional[int]:
    """萤石 device/status/get 返回 battryStatus（官方拼写），一般为 0–100。"""
    if not status_data:
        return None
    val = status_data.get("battryStatus")
    if val is None:
        val = status_data.get("batteryStatus")
    if val is None:
        return None
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    if 0 <= n <= 100:
        return n
    return None


def ys7_status_snapshot(status_data: dict[str, Any]) -> dict[str, Any]:
    """从 status/get 响应 data 提取可缓存字段。"""
    pct = parse_battery_percent_from_status(status_data)
    out: dict[str, Any] = {}
    if pct is not None:
        out["battery_percent"] = pct
    sig = status_data.get("signal")
    if sig is not None:
        try:
            out["signal"] = int(sig)
        except (TypeError, ValueError):
            pass
    return out


def ys7_battery_fields_from_raw(raw_payload: dict[str, Any], *, power_kind: str) -> dict[str, Any]:
    if power_kind != "battery":
        return {}
    st = _as_dict(_as_dict(raw_payload).get("ys7_status"))
    pct = st.get("battery_percent")
    if pct is None:
        return {"ys7_battery_percent": None}
    try:
        p = int(pct)
        if 0 <= p <= 100:
            fields: dict[str, Any] = {"ys7_battery_percent": p}
            if st.get("signal") is not None:
                fields["ys7_signal"] = st.get("signal")
            return fields
    except (TypeError, ValueError):
        pass
    return {"ys7_battery_percent": None}


def ys7_power_kind_from_raw(raw_payload: dict[str, Any]) -> str:
    raw = _as_dict(raw_payload)
    device = _as_dict(raw.get("device"))
    if not device.get("parentCategory") and raw.get("parentCategory"):
        device = raw
    parent = str(device.get("parentCategory") or "").strip()
    if parent == "BatteryCamera":
        return "battery"
    if parent in {"IPC", "NVR", "DVR", "HCVR", "SD"}:
        return "wired"
    return "other"


def is_ys7_battery_device(device: "DeliveryDevice") -> bool:
    if str(device.vendor or "").lower() != "ys7" or str(device.device_type) != "camera":
        return False
    raw = device.raw_payload_json if isinstance(device.raw_payload_json, dict) else {}
    return ys7_power_kind_from_raw(raw) == "battery"
