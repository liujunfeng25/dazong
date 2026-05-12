from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models import Order, OrderItemAllocation, Product, QualityReport

router = APIRouter(prefix="/factory", tags=["factory"])


@router.get("/home")
async def factory_home(_=Depends(require_role("factory"))):
    return {"message": "ok", "module": "factory"}


@router.get("/orders")
async def factory_orders(
    status: str = "",
    order_no: str = "",
    created_date_start: str = "",
    created_date_end: str = "",
    user=Depends(require_role("factory")),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date, datetime, time, timedelta

    today = datetime.utcnow().date()
    try:
        start_date = date.fromisoformat(created_date_start) if created_date_start else today
        end_date = date.fromisoformat(created_date_end) if created_date_end else today
    except ValueError:
        raise HTTPException(400, "时间筛选格式错误，需为 YYYY-MM-DD")
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
    stmt = (
        select(Order)
        .where(Order.id.in_(order_ids), Order.created_at >= start_dt, Order.created_at < end_dt)
        .order_by(Order.id.desc())
    )
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
    report_rows = (
        await db.execute(
            select(QualityReport.id, QualityReport.product_id, QualityReport.order_id, QualityReport.report_no)
            .where(QualityReport.order_id == order_id, QualityReport.supplier_id == user.id)
            .order_by(QualityReport.id.desc())
        )
    ).all()
    report_map = {int(r[0]): r for r in report_rows}
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
            }
            for aid, line_no, pid, qty, unit_price, alloc_status, pname, spec, unit in rows
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
