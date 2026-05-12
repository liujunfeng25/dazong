from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import (
    create_access_token,
    require_client_with_canteen,
    require_role,
    resolve_client_canteen_id_from_request,
)
from models import Bill, ClientCanteen, Contract, Order

router = APIRouter(prefix="/client", tags=["client"])


class ClientCanteenSessionIn(BaseModel):
    canteen_id: int = Field(..., ge=1)


@router.get("/home")
async def client_home(_=Depends(require_role("client"))):
    return {"message": "ok", "module": "client"}


@router.get("/canteens")
async def list_client_canteens(
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    """列出本校（当前 client 用户）下已由运营端维护的食堂；客户端不能在此接口增删改。"""
    rows = (
        await db.scalars(
            select(ClientCanteen)
            .where(ClientCanteen.school_client_id == user.id)
            .order_by(ClientCanteen.sort_order.asc(), ClientCanteen.id.asc())
        )
    ).all()
    return rows


@router.post("/canteen-session")
async def set_client_canteen_session(
    payload: ClientCanteenSessionIn,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(ClientCanteen).where(
            ClientCanteen.id == payload.canteen_id,
            ClientCanteen.school_client_id == user.id,
            ClientCanteen.status == "active",
        )
    )
    if not row:
        raise HTTPException(404, "食堂不存在、已停用或不属于本校")
    token = create_access_token(user, canteen_id=int(row.id))
    return {"token": token, "canteen_id": int(row.id), "canteen_name": row.name}


@router.get("/contracts")
async def client_contracts(user=Depends(require_role("client")), db: AsyncSession = Depends(get_db)):
    return (
        await db.scalars(select(Contract).where(Contract.client_id == user.id).order_by(Contract.id.desc()))
    ).all()


@router.get("/orders")
async def client_orders(
    status: Optional[str] = None,
    order_no: Optional[str] = None,
    created_date_start: Optional[str] = None,
    created_date_end: Optional[str] = None,
    user_and_canteen=Depends(require_client_with_canteen),
    db: AsyncSession = Depends(get_db),
):
    user, canteen = user_and_canteen
    today = datetime.utcnow().date()
    try:
        start_date = date.fromisoformat(created_date_start) if created_date_start else today
        end_date = date.fromisoformat(created_date_end) if created_date_end else today
    except ValueError:
        raise HTTPException(400, "时间筛选格式错误，需为 YYYY-MM-DD")
    if end_date < start_date:
        raise HTTPException(400, "结束日期不能早于开始日期")
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min)
    stmt = (
        select(Order)
        .where(
            Order.client_id == user.id,
            Order.canteen_id == canteen.id,
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
        )
        .order_by(Order.id.desc())
    )
    if status:
        stmt = stmt.where(Order.status == status)
    if order_no and order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))
    return (await db.scalars(stmt)).all()


@router.get("/bills")
async def client_bills(
    request: Request,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    """与 `GET /bills` 一致：仅当前 JWT 所选食堂下、归属本校采购方的应付/应收账单。"""
    cid = await resolve_client_canteen_id_from_request(db, user, request)
    return (
        await db.scalars(
            select(Bill)
            .join(Order, Order.id == Bill.order_id)
            .where(Bill.role == "client", Order.client_id == user.id, Order.canteen_id == cid)
            .order_by(Bill.id.desc())
        )
    ).all()
