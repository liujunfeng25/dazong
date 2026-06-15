"""商品单位枚举（仅清单与成员判定，不含任何换算逻辑）。

- 非标品（按重量收货/过磅）：计量单位
- 标品（按件清点）：计数单位

注意：非标品计量单位用 "kg" / "斤"（**不用「公斤」**）——历史收货换算用 `"斤" in unit`
子串判断，「公斤」含「斤」会被误判为斤 ×0.5。用 "kg" 可避开该坑、无需改收货代码。
"""

# 非标品计量单位
WEIGHT_UNITS = ["kg", "斤"]

# 标品计数单位（覆盖现网已有 + 常见）
COUNT_UNITS = [
    "件", "袋", "箱", "盒", "包", "桶", "瓶", "杯", "提", "排",
    "卷", "只", "块", "托", "组", "把", "份", "条", "罐", "听",
]


def is_weight_unit(unit: str | None) -> bool:
    return (unit or "").strip() in WEIGHT_UNITS


def is_count_unit(unit: str | None) -> bool:
    return (unit or "").strip() in COUNT_UNITS


def allowed_units_for(standard_type: str | None) -> list[str]:
    return WEIGHT_UNITS if str(standard_type) == "non_standard" else COUNT_UNITS
