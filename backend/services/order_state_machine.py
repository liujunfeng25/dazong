"""主订单粗粒度状态机；对外展示名见前端 `orderStatusLabel`（存库值不变）。"""
from fastapi import HTTPException

ALLOWED_TRANSITIONS = {
    "下单": {"取消", "配货"},
    "配货": {"发货"},
    "发货": {"收货"},
    "收货": {"收货确认"},
    "收货确认": {"已结算"},
    "取消": set(),
    "已结算": set(),
}


def ensure_order_transition(old_status: str, new_status: str):
    if old_status == new_status:
        return
    allowed = ALLOWED_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise HTTPException(400, f"非法状态流转: {old_status} -> {new_status}")
