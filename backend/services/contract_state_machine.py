from fastapi import HTTPException

ALLOWED_CONTRACT_TRANSITIONS = {
    "招标中": {"已中标", "已流标"},
    "已中标": {"执行中", "已过期"},
    "执行中": {"已完成", "已过期"},
    "已完成": set(),
    "已流标": set(),
    "已过期": set(),
}


def ensure_contract_transition(old_status: str, new_status: str):
    if old_status == new_status:
        return
    allowed = ALLOWED_CONTRACT_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise HTTPException(400, f"非法合约状态流转: {old_status} -> {new_status}")
