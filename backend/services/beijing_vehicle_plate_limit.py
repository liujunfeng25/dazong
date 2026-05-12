"""北京尾号限行判定（与前端车辆管理页规则对齐，供路线规划等后端接口复用）。"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any

# 工作日机动车尾号限行常见表述：7:00–20:00（北京时间）
BEIJING_TAIL_NUMBER_WINDOW_END = time(20, 0)

# 智能排线中不参与分配的车辆状态（在限行时段可能重叠时启用剔除）
ROUTE_PLAN_BLOCKED_LIMIT_STATUSES = frozenset({"限行", "外地限行"})


def parse_plate_tail_digit(plate_no: str) -> int | None:
    text = str(plate_no or "").strip().upper()
    if not text:
        return None
    last = text[-1]
    if last.isdigit():
        return int(last)
    if "A" <= last <= "Z":
        return 0
    return None


def is_beijing_plate(plate_no: str) -> bool:
    return str(plate_no or "").strip().upper().startswith("京")


def is_beijing_pure_electric_plate(plate_no: str) -> bool:
    p = str(plate_no or "").strip().upper()
    return p.startswith("京AA") or p.startswith("京AB") or p.startswith("京AC") or p.startswith("京AD")


def classify_vehicle_limit(
    vehicle_no: str,
    *,
    restriction: dict[str, Any],
) -> dict[str, str]:
    """
    restriction: fetch_beijing_driving_restriction() 的返回，含 available, digits, raw_text 等。
    返回 { "status": "限行"|"不限行"|"纯电不限"|"外地限行"|"待识别", "reason": str }
    """
    plate = str(vehicle_no or "").strip()
    digits: list[int] = []
    raw_digits = restriction.get("digits") or []
    if isinstance(raw_digits, list):
        for x in raw_digits:
            try:
                digits.append(int(x))
            except (TypeError, ValueError):
                continue
    available = bool(restriction.get("available"))

    if not is_beijing_plate(plate):
        return {
            "status": "外地限行",
            "reason": f"非京牌（{plate or '-'}）默认按未办进京证处理为限行；若已办证仍须遵守尾号限行",
        }
    if is_beijing_pure_electric_plate(plate):
        return {
            "status": "纯电不限",
            "reason": f"车牌前缀 {plate[:4]} 视为纯电，不受尾号限行",
        }
    lim_day = str(restriction.get("date") or "").strip() or "所选日"
    if not available:
        return {
            "status": "待识别",
            "reason": restriction.get("message") or "限行接口不可用，尾号命中情况未知",
        }
    if not digits:
        return {
            "status": "不限行",
            "reason": restriction.get("raw_text") or f"{lim_day} 接口返回不限行",
        }
    tail = parse_plate_tail_digit(plate)
    if tail is None:
        return {"status": "待识别", "reason": "车牌尾号无法识别，请检查录入"}
    if tail in digits:
        return {
            "status": "限行",
            "reason": f"尾号 {tail} 命中限行日 {lim_day} 的限行尾号 {digits}",
        }
    return {
        "status": "不限行",
        "reason": f"尾号 {tail} 未命中限行日 {lim_day} 的限行尾号 {digits}",
    }


def departure_may_overlap_beijing_tail_restriction(departure_shanghai: datetime) -> bool:
    """
    判断本次计划发车是否可能需要遵守「当日 7:00–20:00」尾号限行时段。
    若发车时间已 **晚于** 当日北京时间 20:00，假定主要行程落在限行窗口之外，可不按尾号/外地默认限行剔除车辆。
    20:00 及以前发车（含凌晨），保守认为可能与限行时段重叠。
    """
    if departure_shanghai.tzinfo is None:
        raise ValueError("departure_shanghai 须为带时区的 datetime（建议 Asia/Shanghai）")
    return departure_shanghai.time() <= BEIJING_TAIL_NUMBER_WINDOW_END


def build_vehicle_limit_today(
    vehicle_nos: list[str],
    restriction: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for vn in vehicle_nos:
        c = classify_vehicle_limit(vn, restriction=restriction)
        rows.append(
            {
                "vehicle_no": vn,
                "limit_status": c["status"],
                "reason": c["reason"],
            }
        )
    return {
        "available": bool(restriction.get("available")),
        "city": restriction.get("city") or "北京",
        "date": restriction.get("date") or "",
        "digits": restriction.get("digits") or [],
        "raw_text": restriction.get("raw_text") or "",
        "message": restriction.get("message") or "",
        "vehicles": rows,
    }
