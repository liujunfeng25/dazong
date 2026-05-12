from typing import Iterable, Optional

from services.ws_manager import ws_manager


async def publish_monitor_event(event_type: str, data: dict):
    await ws_manager.broadcast_monitor({"type": event_type, "data": data})


async def publish_role_order_update(
    role: str,
    target_user_ids: Iterable[int],
    order_id: int,
    order_no: str,
    new_status: str,
    message: str,
    *,
    canteen_id: Optional[int] = None,
):
    user_ids = [int(i) for i in target_user_ids if i]
    if not user_ids:
        return
    payload = {
        "type": "order_update",
        "order_id": order_id,
        "order_no": order_no,
        "new_status": new_status,
        "message": message,
        "target_user_ids": user_ids,
    }
    if canteen_id is not None:
        payload["canteen_id"] = int(canteen_id)
    await ws_manager.broadcast_users(role, user_ids, payload)
