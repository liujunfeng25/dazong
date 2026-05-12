from fastapi import HTTPException

ALLOWED_TICKET_TRANSITIONS = {
    "待处理": {"处理中", "已关闭"},
    "处理中": {"已关闭"},
    "已关闭": set(),
}


def ensure_ticket_transition(old_status: str, new_status: str):
    if old_status == new_status:
        return
    allowed = ALLOWED_TICKET_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise HTTPException(400, f"非法工单状态流转: {old_status} -> {new_status}")
