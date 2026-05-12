"""配送时段：整点起止（HH:00-HH:00），且须为恰好 1 小时（如 06:00-07:00；允许 23:00-24:00）。"""
from __future__ import annotations

import re

# 与历史下单校验一致：两端均为整点，结束可为 24:00
DELIVERY_SLOT_RE = re.compile(r"^([01]\d|2[0-3]):00-(?:([01]\d|2[0-3])|24):00$")


def parse_delivery_slot_hours(slot: str | None) -> tuple[int, int] | None:
    s = (slot or "").strip()
    m = DELIVERY_SLOT_RE.match(s)
    if not m:
        return None
    ha = int(m.group(1))
    hb = 24 if m.group(2) is None else int(m.group(2))
    return ha, hb


def is_one_hour_delivery_slot(slot: str | None) -> bool:
    """合法整点格式且结束时刻 = 开始时刻 +1 小时（23:00-24:00 视为 1 小时）。"""
    b = parse_delivery_slot_hours(slot)
    if not b:
        return False
    ha, hb = b
    if ha == 23 and hb == 24:
        return True
    return hb == ha + 1
