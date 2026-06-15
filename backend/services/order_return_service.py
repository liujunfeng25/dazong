"""收货少收：整单确认收货后生成退货单头 + 明细（幂等）。"""

from decimal import Decimal
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Order, OrderReceivingLine, OrderReturn, OrderReturnLine, User
from services.receiving_billing import build_receiving_billing_snapshot


def _new_return_no() -> str:
    return "RT" + datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[-14:]


async def create_returns_after_receive(
    db: AsyncSession,
    order: Order,
    client_user_id: int,
    receive_idempotency_key: Optional[str],
) -> Optional[int]:
    """整单收货时按当前称重行生成/更新退货单。"""
    return await upsert_returns_for_order(db, order, client_user_id, receive_idempotency_key)


async def upsert_returns_for_order(
    db: AsyncSession,
    order: Order,
    client_user_id: int,
    receive_idempotency_key: Optional[str] = None,
) -> Optional[int]:
    """按当前收货行即时生成/更新退货单；无少收行时删除旧明细和旧单头。"""
    existing = await db.scalar(
        select(OrderReturn).where(OrderReturn.order_id == order.id, OrderReturn.source == "receive_shortage")
    )

    recv_rows = (
        await db.scalars(
            select(OrderReceivingLine)
            .where(OrderReceivingLine.order_id == order.id)
            .order_by(OrderReceivingLine.line_index.asc())
        )
    ).all()
    shortage_rows = [r for r in recv_rows if r.shortage_reason_code and str(r.shortage_reason_code).strip()]
    if not shortage_rows:
        if existing:
            if str(existing.status) == "confirmed":
                return int(existing.id)
            await db.execute(delete(OrderReturnLine).where(OrderReturnLine.order_return_id == int(existing.id)))
            await db.delete(existing)
        return None

    items = order.items_json or []
    snaps = order.items_snapshot_json or []

    delivery = await db.scalar(select(User).where(User.id == int(order.delivery_id)))
    target_status = "pending_delivery_review" if bool(getattr(delivery, "return_review_required", False)) else "confirmed"

    if existing:
        ret = existing
        if str(ret.status) == "confirmed":
            return int(ret.id)
        ret.status = target_status
        ret.receive_idempotency_key = (receive_idempotency_key or ret.receive_idempotency_key or None)
        ret.reviewed_by_user_id = None
        ret.reviewed_at = None
        ret.review_note = None
        await db.execute(delete(OrderReturnLine).where(OrderReturnLine.order_return_id == int(ret.id)))
    else:
        ret = OrderReturn(
            order_id=order.id,
            return_no=_new_return_no(),
            source="receive_shortage",
            client_id=client_user_id,
            receive_idempotency_key=(receive_idempotency_key or None)[:128] if receive_idempotency_key else None,
            status=target_status,
        )
        db.add(ret)
        await db.flush()

    billing = await build_receiving_billing_snapshot(db, order, enforce_return_status=False)
    billing_lines = {int(x.get("line_index") or 0): x for x in billing.get("lines") or []}

    for r in shortage_rows:
        idx = int(r.line_index)
        item = items[idx - 1] if 0 < idx <= len(items) else {}
        snap = snaps[idx - 1] if 0 < idx <= len(snaps) else {}
        pid = int(item.get("product_id") or snap.get("product_id") or 0)
        pname = str(snap.get("product_name") or item.get("product_name") or f"商品#{pid}")
        ok = float(r.shortage_ordered_kg or 0)
        rk = float(r.confirmed_quantity if r.confirmed_quantity is not None else r.confirmed_kg or 0)
        dk = float(r.shortage_delta_kg or max(0.0, ok - rk))
        deduction_amount = Decimal(str((billing_lines.get(idx) or {}).get("deduction_amount") or 0)).quantize(Decimal("0.01"))
        db.add(
            OrderReturnLine(
                order_return_id=int(ret.id),
                line_index=idx,
                product_id=pid if pid > 0 else None,
                product_name=pname[:255],
                ordered_kg=ok,
                received_kg=rk,
                delta_kg=dk,
                reason_code=str(r.shortage_reason_code),
                reason_detail=r.shortage_reason_detail,
                photo_urls_json=r.return_photo_urls_json or [],
                deduction_amount=deduction_amount,
            )
        )
    return int(ret.id)
