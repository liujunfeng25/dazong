from fastapi import HTTPException

ALLOWED_ALERT_TRANSITIONS = {
    "open": {"closed"},
    "closed": set(),
}


def ensure_alert_transition(old_status: str, new_status: str):
    if old_status == new_status:
        return
    allowed = ALLOWED_ALERT_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise HTTPException(400, f"非法预警状态流转: {old_status} -> {new_status}")
