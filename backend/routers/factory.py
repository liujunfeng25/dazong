from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models import BillingStatement, Order, OrderItemAllocation, Product, QualityReport
from services.periodic_quality_reports import (
    approved_periodic_report_map,
    periodic_report_payload,
    quality_cover_date_for_order,
)

router = APIRouter(prefix="/factory", tags=["factory"])


@router.get("/home")
async def factory_home(
    user=Depends(require_role("factory")),
    db: AsyncSession = Depends(get_db),
):
    """厂家落地页「今日待办」汇总:全部真实查询,无 mock。
    厂家以「指定厂家」身份承接分单(allocation.supplier_id == 本厂家),口径与供货商一致。
    - pending_ship_orders:今日配送、有未出库分单、且订单仍在「下单/配货」的订单数
      （业务规则:当日分的单当日发货,故只看「今日配送」的待发货单）
    - in_progress_orders:分给本厂家、未结算未取消的订单数(全量)
    - receivable_unsettled:本厂家「应收」方向、未结清账单未结金额(对配送商应收,全量)
    """
    fid = int(user.id)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    base = (
        select(func.count(func.distinct(OrderItemAllocation.order_id)))
        .select_from(OrderItemAllocation)
        .join(Order, Order.id == OrderItemAllocation.order_id)
        .where(OrderItemAllocation.supplier_id == fid)
    )
    pending_ship = await db.scalar(
        base.where(
            OrderItemAllocation.status != "已出库",
            Order.status.in_(["下单", "配货"]),
            Order.expected_delivery_date == today,
        )
    )
    in_progress = await db.scalar(base.where(Order.status.notin_(["已结算", "取消"])))
    receivable = await db.scalar(
        select(func.coalesce(func.sum(BillingStatement.amount - BillingStatement.settled_amount), 0)).where(
            BillingStatement.owner_user_id == fid,
            BillingStatement.direction == "应收",
            BillingStatement.status != "已结清",
        )
    )
    return {
        "message": "ok",
        "module": "factory",
        "todo": {
            "pending_ship_orders": int(pending_ship or 0),
            "in_progress_orders": int(in_progress or 0),
            "receivable_unsettled": float(receivable or 0),
        },
    }


@router.get("/orders")
async def factory_orders(
    status: str = "",
    order_no: str = "",
    created_date_start: str = "",
    created_date_end: str = "",
    expected_delivery_date_start: str = "",
    expected_delivery_date_end: str = "",
    user=Depends(require_role("factory")),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date, datetime, time, timedelta

    today = datetime.utcnow().date()
    use_delivery_filter = bool(expected_delivery_date_start or expected_delivery_date_end)
    try:
        if use_delivery_filter:
            ed_start = date.fromisoformat(expected_delivery_date_start) if expected_delivery_date_start else today
            ed_end = date.fromisoformat(expected_delivery_date_end) if expected_delivery_date_end else ed_start
        else:
            start_date = date.fromisoformat(created_date_start) if created_date_start else today
            end_date = date.fromisoformat(created_date_end) if created_date_end else today
    except ValueError:
        raise HTTPException(400, "时间筛选格式错误，需为 YYYY-MM-DD")
    if use_delivery_filter:
        if ed_end < ed_start:
            raise HTTPException(400, "结束日期不能早于开始日期")
    else:
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date + timedelta(days=1), time.min)

    order_ids = (
        await db.scalars(
            select(OrderItemAllocation.order_id)
            .join(Product, Product.id == OrderItemAllocation.product_id)
            .where(
                OrderItemAllocation.supplier_id == user.id,
                Product.is_designated_factory.is_(True),
                Product.designated_factory_id == user.id,
            )
            .distinct()
        )
    ).all()
    if not order_ids:
        return []
    stmt = select(Order).where(Order.id.in_(order_ids)).order_by(Order.id.desc())
    if use_delivery_filter:
        stmt = stmt.where(
            Order.expected_delivery_date >= ed_start,
            Order.expected_delivery_date <= ed_end,
        )
    else:
        stmt = stmt.where(Order.created_at >= start_dt, Order.created_at < end_dt)
    if status:
        stmt = stmt.where(Order.status == status)
    if order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))
    return (await db.scalars(stmt)).all()


@router.get("/orders/{order_id}")
async def factory_order_detail(
    order_id: int,
    user=Depends(require_role("factory")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    rows = (
        await db.execute(
            select(
                OrderItemAllocation.id,
                OrderItemAllocation.line_no,
                OrderItemAllocation.product_id,
                OrderItemAllocation.quantity,
                OrderItemAllocation.unit_price,
                OrderItemAllocation.status,
                Product.name,
                Product.spec,
                Product.unit,
                Product.quality_report_mode,
            )
            .join(Product, Product.id == OrderItemAllocation.product_id)
            .where(
                OrderItemAllocation.order_id == order_id,
                OrderItemAllocation.supplier_id == user.id,
                Product.is_designated_factory.is_(True),
                Product.designated_factory_id == user.id,
            )
            .order_by(OrderItemAllocation.line_no.asc(), OrderItemAllocation.id.asc())
        )
    ).all()
    if not rows:
        raise HTTPException(403, "无权限查看该订单")
    allocation_ids = [int(r[0]) for r in rows]
    alloc_rows = (
        await db.scalars(
            select(OrderItemAllocation).where(OrderItemAllocation.id.in_(allocation_ids))
        )
    ).all()
    periodic_by_key = await approved_periodic_report_map(
        db,
        alloc_rows,
        cover_date=quality_cover_date_for_order(order),
    )
    report_rows = (
        await db.execute(
            select(QualityReport.id, QualityReport.product_id, QualityReport.order_id, QualityReport.report_no)
            .where(QualityReport.order_id == order_id, QualityReport.supplier_id == user.id)
            .order_by(QualityReport.id.desc())
        )
    ).all()
    return {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "created_at": order.created_at,
        "items": [
            {
                "allocation_id": int(aid),
                "line_no": int(line_no),
                "product_id": int(pid),
                "product_name": pname,
                "spec": spec,
                "unit": unit,
                "quantity": float(qty or 0),
                "unit_price": float(unit_price or 0),
                "status": alloc_status,
                "quality_report_mode": str(qmode or "batch"),
                "periodic_quality_report": periodic_report_payload(
                    periodic_by_key.get((int(pid), int(user.id)))
                )
                if str(qmode or "batch") == "periodic"
                else None,
            }
            for aid, line_no, pid, qty, unit_price, alloc_status, pname, spec, unit, qmode in rows
        ],
        "allocation_ids": allocation_ids,
        "latest_reports": [
            {
                "id": int(rid),
                "product_id": int(pid),
                "order_id": int(oid),
                "report_no": report_no,
            }
            for rid, pid, oid, report_no in report_rows
        ],
    }
