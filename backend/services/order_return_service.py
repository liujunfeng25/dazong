"""收货少收：整单确认收货后生成退货单头 + 明细（幂等）。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Order, OrderReceivingLine, OrderReturn, OrderReturnLine


def _new_return_no() -> str:
    return "RT" + datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[-14:]


async def create_returns_after_receive(
    db: AsyncSession,
    order: Order,
    client_user_id: int,
    receive_idempotency_key: Optional[str],
) -> Optional[int]:
    """若存在少收原因草稿，则生成一条 order_returns 及若干 order_return_lines。已存在同单退货头则跳过。"""
    existing_id = await db.scalar(
        select(OrderReturn.id).where(
            OrderReturn.order_id == order.id,
            OrderReturn.source == "receive_shortage",
        )
    )
    if existing_id:
        return int(existing_id)

    recv_rows = (
        await db.scalars(
            select(OrderReceivingLine)
            .where(OrderReceivingLine.order_id == order.id)
            .order_by(OrderReceivingLine.line_index.asc())
        )
    ).all()
    shortage_rows = [r for r in recv_rows if r.shortage_reason_code and str(r.shortage_reason_code).strip()]
    if not shortage_rows:
        return None

    items = order.items_json or []
    snaps = order.items_snapshot_json or []

    ret = OrderReturn(
        order_id=order.id,
        return_no=_new_return_no(),
        source="receive_shortage",
        client_id=client_user_id,
        receive_idempotency_key=(receive_idempotency_key or None)[:128] if receive_idempotency_key else None,
        status="confirmed",
    )
    db.add(ret)
    await db.flush()

    for r in shortage_rows:
        idx = int(r.line_index)
        item = items[idx - 1] if 0 < idx <= len(items) else {}
        snap = snaps[idx - 1] if 0 < idx <= len(snaps) else {}
        pid = int(item.get("product_id") or snap.get("product_id") or 0)
        pname = str(snap.get("product_name") or item.get("product_name") or f"商品#{pid}")
        ok = float(r.shortage_ordered_kg or 0)
        rk = float(r.confirmed_kg or 0)
        dk = float(r.shortage_delta_kg or max(0.0, ok - rk))
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
            )
        )
    return int(ret.id)
