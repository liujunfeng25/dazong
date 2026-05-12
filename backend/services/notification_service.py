from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Notification, User
from services.ws_manager import ws_manager


def _prefix_for_event_type(event_type: str) -> str:
    et = str(event_type or "").strip().lower()
    if et in {"order_status_change"}:
        return "[履约]"
    if et in {"order_split_confirmed"}:
        return "[分单]"
    if et in {"bill_created"}:
        return "[账单生成]"
    if et in {"bill_settled", "bill_update"}:
        return "[账单结算]"
    if et in {"ticket_complaint"}:
        return "[工单]"
    if et in {
        "tender_shortlisted",
        "tender_bid_created",
        "tender_bid_updated",
        "tender_award_win",
        "tender_award_lose",
        "tender_awarded_done",
        "supplier_quote_updated",
    }:
        return "[招采]"
    return "[系统]"


def _with_prefix(event_type: str, title: str) -> str:
    raw = str(title or "").strip()
    if not raw:
        raw = "系统通知"
    if raw.startswith("["):
        return raw
    return f"{_prefix_for_event_type(event_type)} {raw}"


async def push_notification(
    db: AsyncSession,
    *,
    role: str,
    event_type: str,
    title: str,
    content: str,
    route: str,
    target_user_ids: Iterable[int],
    object_type: str = "",
    object_id: int = 0,
    canteen_id: Optional[int] = None,
) -> None:
    user_ids = [int(i) for i in target_user_ids if i]
    if not user_ids:
        return
    normalized_title = _with_prefix(event_type, title)
    cid = int(canteen_id) if canteen_id is not None else None
    for user_id in user_ids:
        db.add(
            Notification(
                event_type=event_type,
                title=normalized_title,
                content=content,
                role=role,
                target_user_id=user_id,
                canteen_id=cid,
                object_type=object_type,
                object_id=object_id,
                route=route,
                is_read=False,
            )
        )
    await db.flush()
    await ws_manager.broadcast_users(
        role,
        user_ids,
        {
            "type": "notification",
            "event_type": event_type,
            "title": normalized_title,
            "content": content,
            "route": route,
            "object_type": object_type,
            "object_id": object_id,
            "target_user_ids": user_ids,
            "canteen_id": cid,
        },
    )


async def list_operation_user_ids(db: AsyncSession) -> list[int]:
    rows = (await db.scalars(select(User.id).where(User.role == "operation"))).all()
    return [int(r) for r in rows]


async def push_single_notification(
    db: AsyncSession,
    *,
    role: str,
    target_user_id: int,
    event_type: str,
    title: str,
    content: str,
    route: str,
    object_type: str = "",
    object_id: int = 0,
    canteen_id: Optional[int] = None,
) -> None:
    await push_notification(
        db,
        role=role,
        event_type=event_type,
        title=title,
        content=content,
        route=route,
        object_type=object_type,
        object_id=object_id,
        target_user_ids=[target_user_id],
        canteen_id=canteen_id,
    )
