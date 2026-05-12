"""客户端售后投诉接口：图片上传 + 创建工单。"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role, resolve_client_canteen_id_from_request
from models import Order
from schemas.complaints import ComplaintIn
from services.audit_service import write_audit_log
from services.storage.minio_client import upload_complaint_image
from services.notification_service import push_notification
from services.ticket_service import (
    create_customer_complaint_ticket,
    find_open_complaint_ticket,
)

router = APIRouter(prefix="/complaints", tags=["complaints"])

ALLOWED_STATUSES = {"收货确认", "已结算"}


def _audit_meta(request: Request) -> dict:
    return {
        "trace_id": getattr(request.state, "trace_id", ""),
        "source_ip": request.client.host if request.client else "",
    }


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    _user=Depends(require_role("client")),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "仅允许上传图片")
    url = await upload_complaint_image(file)
    return {"url": url}


@router.post("")
async def create_complaint(
    payload: ComplaintIn,
    request: Request,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    cid = await resolve_client_canteen_id_from_request(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == payload.order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在或不属于当前账号")
    if str(order.status) not in ALLOWED_STATUSES:
        raise HTTPException(400, "仅在「已确认收货 / 已结算」的订单可发起售后投诉")
    existing = await find_open_complaint_ticket(db, int(order.id))
    if existing:
        raise HTTPException(400, "该订单已有未关闭的售后投诉工单，请等待配送商与运营处理")

    ticket = await create_customer_complaint_ticket(
        db,
        order=order,
        client_user=user,
        reason=payload.reason,
        image_urls=payload.image_urls,
    )
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="complaint_create",
        category="ticket",
        object_type="ticket",
        object_id=int(ticket.id),
        detail=f"客户端发起售后投诉：订单 {order.order_no}",
        after_json={
            "order_id": int(order.id),
            "order_no": order.order_no,
            "image_count": len(payload.image_urls or []),
        },
        **_audit_meta(request),
    )
    await push_notification(
        db=db,
        role="delivery",
        event_type="ticket_complaint",
        title=f"售后投诉待处理：{order.order_no}",
        content=(ticket.description or "")[:300],
        route=f"/delivery/complaints",
        object_type="ticket",
        object_id=int(ticket.id),
        target_user_ids=[int(order.delivery_id)],
    )
    await db.commit()
    return {
        "id": int(ticket.id),
        "order_id": int(ticket.order_id),
        "type": ticket.type,
        "status": ticket.status,
        "description": ticket.description,
        "attachments_json": ticket.attachments_json or [],
    }


@router.get("/order/{order_id}/open")
async def get_open_complaint(
    order_id: int,
    request: Request,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    """供客户端订单详情判断按钮置灰：返回是否已存在未关闭的投诉工单。"""
    cid = await resolve_client_canteen_id_from_request(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在或不属于当前账号")
    existing = await find_open_complaint_ticket(db, int(order.id))
    if not existing:
        return {"exists": False}
    return {
        "exists": True,
        "id": int(existing.id),
        "status": existing.status,
        "description": existing.description,
        "attachments_json": existing.attachments_json or [],
    }
