from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Bill, Order, OrderItemAllocation
from services.receiving_billing import build_receiving_billing_snapshot


async def create_receive_bills(db: AsyncSession, order: Order):
    billing = await build_receiving_billing_snapshot(db, order)
    received_total = Decimal(str(billing.get("received_amount") or order.total_amount or 0)).quantize(Decimal("0.01"))
    order_snapshot = {
        "order_id": order.id,
        "order_no": order.order_no,
        "client_id": order.client_id,
        "supplier_id": int(order.supplier_id) if order.supplier_id is not None else None,
        "delivery_id": order.delivery_id,
        "order_status": order.status,
        "items_snapshot_json": order.items_snapshot_json,
        "total_amount": float(order.total_amount),
        "receiving_billing": billing,
        "received_amount": float(received_total),
        "deduction_amount": float(Decimal(str(billing.get("deduction_amount") or 0)).quantize(Decimal("0.01"))),
        "total_volume_m3": float(order.total_volume_m3) if order.total_volume_m3 is not None else None,
        "total_weight_kg": float(order.total_weight_kg) if order.total_weight_kg is not None else None,
    }
    db.add(
        Bill(
            order_id=order.id,
            role="client",
            amount=received_total,
            order_snapshot_json=order_snapshot,
            bill_type="应付",
            status="待结算",
        )
    )
    db.add(
        Bill(
            order_id=order.id,
            role="delivery",
            amount=received_total,
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
                OrderItemAllocation.id,
            ).where(
                OrderItemAllocation.order_id == order.id,
                OrderItemAllocation.delivery_id == order.delivery_id,
            )
        )
    ).all()
    payable_by_supplier: dict[int, Decimal] = {}
    allocation_amounts = {
        int(k): Decimal(str(v)).quantize(Decimal("0.01"))
        for k, v in (billing.get("allocation_amounts") or {}).items()
    }
    for supplier_id, quantity, unit_price, allocation_id in allocation_rows:
        sid = int(supplier_id)
        payable_by_supplier.setdefault(sid, Decimal("0.00"))
        original_amount = (Decimal(str(quantity or 0)) * Decimal(str(unit_price or 0))).quantize(Decimal("0.01"))
        payable_by_supplier[sid] += allocation_amounts.get(int(allocation_id), original_amount)
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
