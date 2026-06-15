from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import DeliverySortScanRecord, OrderItemAllocation


async def delivery_sort_summary_for_order(db: AsyncSession, order_id: int) -> dict:
    total = int(
        await db.scalar(
            select(func.count(OrderItemAllocation.id)).where(OrderItemAllocation.order_id == order_id)
        )
        or 0
    )
    if total <= 0:
        return {"total": 0, "sorted": 0, "all_sorted": True}
    sorted_count = int(
        await db.scalar(
            select(func.count(DeliverySortScanRecord.id))
            .join(OrderItemAllocation, OrderItemAllocation.id == DeliverySortScanRecord.allocation_id)
            .where(OrderItemAllocation.order_id == order_id)
        )
        or 0
    )
    return {
        "total": total,
        "sorted": sorted_count,
        "all_sorted": sorted_count == total,
    }
