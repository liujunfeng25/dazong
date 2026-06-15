from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import (
    create_access_token,
    require_client_with_canteen,
    require_role,
    resolve_client_canteen_id_from_request,
)
from models import Bill, BillingStatement, ClientCanteen, Contract, Order

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


CLIENT_ACTIVE_STATUSES = ["下单", "配货", "发货", "收货", "收货确认"]


@router.get("/dashboard")
async def client_dashboard(
    request: Request,
    scope: str = "canteen",
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    """客户采购看板：KPI + 近7日采购趋势 + 近30日品类分布 + 近90日常购商品 TOP。
    scope=canteen 仅当前所选食堂；scope=all 汇总本校全部食堂。"""
    scope = "all" if str(scope) == "all" else "canteen"
    today = datetime.utcnow().date()
    month_start = today.replace(day=1)
    d7_start = today - timedelta(days=6)
    d30_start = today - timedelta(days=29)
    d90_start = today - timedelta(days=89)

    order_filter = [Order.client_id == user.id]
    canteen_name = "全部食堂"
    canteen_id = None
    if scope == "canteen":
        canteen_id = await resolve_client_canteen_id_from_request(db, user, request)
        order_filter.append(Order.canteen_id == canteen_id)
        crow = await db.scalar(select(ClientCanteen).where(ClientCanteen.id == canteen_id))
        canteen_name = crow.name if crow else ""

    # 本月采购额 / 订单数（≠取消）
    month_filter = [*order_filter, func.date(Order.created_at) >= month_start, Order.status != "取消"]
    month_spend = float(
        await db.scalar(select(func.coalesce(func.sum(Order.total_amount), 0)).where(*month_filter)) or 0
    )
    month_orders = int(
        await db.scalar(select(func.count(Order.id)).where(*month_filter)) or 0
    )
    avg_order = round(month_spend / month_orders, 2) if month_orders else 0.0

    to_receive = int(
        await db.scalar(select(func.count(Order.id)).where(*order_filter, Order.status == "收货")) or 0
    )
    in_progress = int(
        await db.scalar(
            select(func.count(Order.id)).where(*order_filter, Order.status.in_(CLIENT_ACTIVE_STATUSES))
        )
        or 0
    )
    abnormal = int(
        await db.scalar(
            select(func.count(Order.id)).where(
                *order_filter, Order.has_abnormal.is_(True), Order.status.in_(CLIENT_ACTIVE_STATUSES)
            )
        )
        or 0
    )

    # 应付未结
    payable_filter = [
        BillingStatement.role == "client",
        BillingStatement.owner_user_id == user.id,
        BillingStatement.direction == "应付",
        BillingStatement.status != "已结清",
    ]
    if scope == "canteen":
        payable_filter.append(BillingStatement.canteen_id == canteen_id)
    payable_outstanding = float(
        await db.scalar(
            select(
                func.coalesce(func.sum(BillingStatement.amount - BillingStatement.settled_amount), 0)
            ).where(*payable_filter)
        )
        or 0
    )

    # 近 7 日采购额趋势
    trend_rows = (
        await db.execute(
            select(func.date(Order.created_at), func.coalesce(func.sum(Order.total_amount), 0))
            .where(*order_filter, func.date(Order.created_at) >= d7_start, Order.status != "取消")
            .group_by(func.date(Order.created_at))
        )
    ).all()
    trend_map = {str(r[0]): float(r[1] or 0) for r in trend_rows}
    trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        trend.append({"date": d.strftime("%m-%d"), "spend": round(trend_map.get(d.isoformat(), 0.0), 2)})

    # 近 30 日品类分布 / 近 90 日商品 TOP（解析下单快照）
    cat_orders = (
        await db.scalars(
            select(Order).where(*order_filter, func.date(Order.created_at) >= d90_start, Order.status != "取消")
        )
    ).all()
    cat_amount: dict[str, float] = {}
    prod_amount: dict[str, float] = {}
    prod_qty: dict[str, float] = {}
    for o in cat_orders:
        in_30 = o.created_at.date() >= d30_start
        for it in o.items_snapshot_json or []:
            if not isinstance(it, dict):
                continue
            qty = float(it.get("order_quantity") if it.get("order_quantity") is not None else it.get("quantity") or 0)
            price = float(it.get("order_unit_price") if it.get("order_unit_price") is not None else it.get("unit_price") or 0)
            amt = qty * price
            pname = it.get("product_name") or f"商品#{it.get('product_id')}"
            prod_amount[pname] = prod_amount.get(pname, 0.0) + amt
            prod_qty[pname] = prod_qty.get(pname, 0.0) + qty
            if in_30:
                cname = it.get("category1_name") or "未分类"
                cat_amount[cname] = cat_amount.get(cname, 0.0) + amt
    category_dist = sorted(
        ({"name": k, "value": round(v, 2)} for k, v in cat_amount.items()),
        key=lambda x: x["value"],
        reverse=True,
    )
    product_top = sorted(
        (
            {"name": k, "amount": round(prod_amount[k], 2), "qty": round(prod_qty.get(k, 0.0), 2)}
            for k in prod_amount
        ),
        key=lambda x: x["amount"],
        reverse=True,
    )[:8]

    return {
        "scope": scope,
        "canteen_name": canteen_name,
        "kpi": {
            "month_spend": round(month_spend, 2),
            "month_orders": month_orders,
            "avg_order": avg_order,
            "to_receive": to_receive,
            "in_progress": in_progress,
            "abnormal": abnormal,
            "payable_outstanding": round(payable_outstanding, 2),
        },
        "trend": trend,
        "category_dist": category_dist,
        "product_top": product_top,
    }


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
