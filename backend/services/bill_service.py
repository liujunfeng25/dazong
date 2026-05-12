from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Bill, Order, OrderItemAllocation


async def create_receive_bills(db: AsyncSession, order: Order):
    order_snapshot = {
        "order_id": order.id,
        "order_no": order.order_no,
        "client_id": order.client_id,
        "supplier_id": int(order.supplier_id) if order.supplier_id is not None else None,
        "delivery_id": order.delivery_id,
        "order_status": order.status,
        "items_snapshot_json": order.items_snapshot_json,
        "total_amount": float(order.total_amount),
        "total_volume_m3": float(order.total_volume_m3) if order.total_volume_m3 is not None else None,
        "total_weight_kg": float(order.total_weight_kg) if order.total_weight_kg is not None else None,
    }
    db.add(
        Bill(
            order_id=order.id,
            role="client",
            amount=order.total_amount,
            order_snapshot_json=order_snapshot,
            bill_type="应付",
            status="待结算",
        )
    )
    db.add(
        Bill(
            order_id=order.id,
            role="delivery",
            amount=order.total_amount,
            order_snapshot_json=order_snapshot,
            bill_type="应收",
            status="待结算",
        )
    )
    allocation_rows = (
        await db.execute(
            select(
                OrderItemAllocation.supplier_id,
                OrderItemAllocation.quantity,
                OrderItemAllocation.unit_price,
            ).where(
                OrderItemAllocation.order_id == order.id,
                OrderItemAllocation.delivery_id == order.delivery_id,
            )
        )
    ).all()
    payable_by_supplier: dict[int, Decimal] = {}
    for supplier_id, quantity, unit_price in allocation_rows:
        sid = int(supplier_id)
        payable_by_supplier.setdefault(sid, Decimal("0.00"))
        payable_by_supplier[sid] += (Decimal(str(quantity or 0)) * Decimal(str(unit_price or 0))).quantize(Decimal("0.01"))
    for supplier_id, amount in payable_by_supplier.items():
        supplier_snapshot = {**order_snapshot, "supplier_id": supplier_id}
        db.add(
            Bill(
                order_id=order.id,
                role="delivery",
                amount=amount.quantize(Decimal("0.01")),
                order_snapshot_json=supplier_snapshot,
                bill_type="应付",
                status="待结算",
            )
        )
        db.add(
            Bill(
                order_id=order.id,
                role="supplier",
                amount=amount.quantize(Decimal("0.01")),
                order_snapshot_json=supplier_snapshot,
                bill_type="应收",
                status="待结算",
            )
        )
