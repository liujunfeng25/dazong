"""分单质检缺失检测：仅「已出库」视为已从供货商发出，缺报告则参与异常判定。"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Order, OrderAbnormal, OrderItemAllocation, QualityReport, Ticket
from services.ticket_service import QUALITY_MISSING_PREFIX, close_quality_missing_ticket_if_clear


async def missing_quality_allocations(
    db: AsyncSession, order_id: int, *, shipped_only: bool
) -> list[OrderItemAllocation]:
    """返回缺质检的分单行。shipped_only=True 时仅检查状态为「已出库」的分单（已从供货商发出）。"""
    alloc_rows = (
        await db.scalars(
            select(OrderItemAllocation).where(OrderItemAllocation.order_id == order_id)
        )
    ).all()
    if not alloc_rows:
        return []
    if shipped_only:
        alloc_rows = [a for a in alloc_rows if str(a.status) == "已出库"]
    if not alloc_rows:
        return []
    qr_rows = (
        await db.scalars(
            select(QualityReport).where(QualityReport.order_id == order_id)
        )
    ).all()
    covered_alloc_ids = {int(q.allocation_id) for q in qr_rows if q.allocation_id is not None}
    legacy_keys = {
        (int(q.product_id), int(q.supplier_id))
        for q in qr_rows
        if q.allocation_id is None
    }
    missing: list[OrderItemAllocation] = []
    for a in alloc_rows:
        if int(a.id) in covered_alloc_ids:
            continue
        if (int(a.product_id), int(a.supplier_id)) in legacy_keys:
            continue
        missing.append(a)
    return missing


async def assert_quality_missing_ticket_can_close(
    db: AsyncSession, ticket: Ticket, new_status: str
) -> None:
    """运营端将工单置为「已关闭」前：「异常订单·【质检缺失】」须已补齐全部分单质检（与自动关单口径一致）。"""
    if new_status != "已关闭":
        return
    if str(ticket.type) != "异常订单":
        return
    if not (ticket.description or "").strip().startswith(QUALITY_MISSING_PREFIX):
        return
    miss = await missing_quality_allocations(db, int(ticket.order_id), shipped_only=False)
    if miss:
        raise HTTPException(
            400,
            f"仍有 {len(miss)} 条分单未上传质检报告，须全部补全并消除缺质检异常后方可关闭该工单。",
        )


async def refresh_order_has_abnormal_for_quality(db: AsyncSession, order: Order) -> None:
    """上传质检后重算 has_abnormal：按「全部分单」是否齐全 + 既有 OrderAbnormal 记录。

    口径：消除条件比触发条件更严——必须所有分单（无论状态）都有质检报告，
    且没有任何 OrderAbnormal 记录，才能把 has_abnormal 落回 false。
    任何一条分单仍缺报告，has_abnormal 保持 true。
    """
    miss_all = await missing_quality_allocations(db, int(order.id), shipped_only=False)
    has_abn_rows = (
        await db.scalar(
            select(OrderAbnormal.id).where(OrderAbnormal.order_id == order.id).limit(1)
        )
        is not None
    )
    order.has_abnormal = bool(miss_all) or has_abn_rows
    if not miss_all:
        # 全部分单都已上传质检：关闭对应的「质检缺失」工单（合约异常/超时单不受影响）
        await close_quality_missing_ticket_if_clear(db, order)
