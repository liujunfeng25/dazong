from fastapi import APIRouter, Depends, Request
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, parse_client_canteen_id_from_authorization
from models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class MarkReadIn(BaseModel):
    ids: list[int] = []


def _client_notification_scope(request: Request, user):
    """采购端：仅本校 JWT 当前食堂 + 学校级（canteen_id IS NULL）。"""
    if str(user.role) != "client":
        return true()
    cid = parse_client_canteen_id_from_authorization(request.headers.get("authorization"))
    if cid is None:
        return Notification.canteen_id.is_(None)
    return or_(Notification.canteen_id.is_(None), Notification.canteen_id == int(cid))


@router.get("")
async def list_notifications(
    request: Request,
    unread_only: bool = False,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = _client_notification_scope(request, user)
    stmt = (
        select(Notification)
        .where(Notification.target_user_id == user.id, scope)
        .order_by(Notification.id.desc())
        .limit(100)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return (await db.scalars(stmt)).all()


@router.post("/read")
async def mark_read(
    request: Request,
    payload: MarkReadIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = _client_notification_scope(request, user)
    if payload.ids:
        rows = (
            await db.scalars(
                select(Notification).where(
                    Notification.target_user_id == user.id,
                    Notification.id.in_(payload.ids),
                    scope,
                )
            )
        ).all()
    else:
        rows = (
            await db.scalars(
                select(Notification).where(Notification.target_user_id == user.id, scope)
            )
        ).all()
    for row in rows:
        row.is_read = True
        row.read_at = row.read_at or datetime.utcnow()
    await db.commit()
    return {"updated": len(rows)}


@router.post("/read/{notification_id}")
async def mark_read_one(
    notification_id: int,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = _client_notification_scope(request, user)
    row = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.target_user_id == user.id,
            scope,
        )
    )
    if row:
        row.is_read = True
        row.read_at = row.read_at or datetime.utcnow()
        await db.commit()
    return {"ok": True}
