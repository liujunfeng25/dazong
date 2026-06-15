"""分单质检缺失检测：仅「已出库」视为已从供货商发出，缺报告则参与异常判定。"""

from collections import defaultdict
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Order,
    OrderAbnormal,
    OrderItemAllocation,
    PeriodicQualityReport,
    QualityReport,
    Ticket,
)
from services.periodic_quality_reports import (
    approved_periodic_report_map,
    product_quality_mode_map,
    quality_cover_date_for_order,
)
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
    order = await db.scalar(select(Order).where(Order.id == order_id))
    cover_date = quality_cover_date_for_order(order) if order else None
    mode_map = await product_quality_mode_map(db, [int(a.product_id) for a in alloc_rows])
    periodic_map = (
        await approved_periodic_report_map(db, alloc_rows, cover_date=cover_date)
        if cover_date is not None
        else {}
    )
    missing: list[OrderItemAllocation] = []
    for a in alloc_rows:
        if mode_map.get(int(a.product_id), "batch") == "periodic":
            if (int(a.product_id), int(a.supplier_id)) in periodic_map:
                continue
            missing.append(a)
            continue
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


async def period_quality_coverage(
    db: AsyncSession,
    allocations: list[OrderItemAllocation],
    quality_reports: list[QualityReport],
    orders: list[Order],
    *,
    shipped_only: bool = True,
) -> dict:
    """周期级质检覆盖率统计（批次为存证模型：上传即覆盖，无审核）。

    覆盖判定与 ``order_detail_aggregator`` 完全一致：
      - batch 模式：该分单存在批次报告（按 allocation_id；旧数据按 product+supplier 兜底）
      - periodic 模式：该订单 cover_date 落在某「已通过」周期报告有效期内

    ``shipped_only=True`` 时仅统计「已出库」分单（到此步才应当有报告，避免分母含未发货行
    使覆盖率永远到不了 100%）。复用已加载的 ``allocations`` / ``quality_reports`` / ``orders``，
    仅额外一次周期报告查询。返回 shipped/covered/missing/coverage_rate。
    """
    targets = [
        a for a in allocations
        if (not shipped_only or str(a.status) == "已出库")
    ]
    total = len(targets)
    if total == 0:
        return {
            "shipped": 0,
            "covered": 0,
            "missing": 0,
            "coverage_rate": 0.0,
            "missing_allocations": [],
        }

    covered_alloc_ids = {
        int(q.allocation_id) for q in quality_reports if q.allocation_id is not None
    }
    legacy_keys = {
        (int(q.product_id), int(q.supplier_id))
        for q in quality_reports
        if q.allocation_id is None
    }
    mode_map = await product_quality_mode_map(db, [int(a.product_id) for a in targets])
    order_cover: dict[int, date] = {
        int(o.id): quality_cover_date_for_order(o) for o in orders
    }

    # 周期模式分单：一次查回全部「已通过」候选报告，在内存内按各订单 cover_date 命中有效期，
    # 比 approved_periodic_report_map（单一 cover_date）更准——不同订单交期可能落在不同有效期。
    periodic_windows: dict[tuple[int, int], list[tuple[date, date]]] = defaultdict(list)
    periodic_pairs = {
        (int(a.product_id), int(a.supplier_id))
        for a in targets
        if mode_map.get(int(a.product_id), "batch") == "periodic"
    }
    if periodic_pairs:
        rows = (
            await db.scalars(
                select(PeriodicQualityReport).where(
                    PeriodicQualityReport.product_id.in_(
                        sorted({pid for pid, _ in periodic_pairs})
                    ),
                    PeriodicQualityReport.provider_id.in_(
                        sorted({sid for _, sid in periodic_pairs})
                    ),
                    PeriodicQualityReport.status == "已通过",
                )
            )
        ).all()
        for r in rows:
            key = (int(r.product_id), int(r.provider_id))
            if key in periodic_pairs:
                periodic_windows[key].append((r.valid_from, r.valid_to))

    missing_allocations: list[OrderItemAllocation] = []
    for a in targets:
        if mode_map.get(int(a.product_id), "batch") == "periodic":
            cover_date = order_cover.get(int(a.order_id))
            windows = periodic_windows.get((int(a.product_id), int(a.supplier_id)), [])
            if cover_date is not None and any(vf <= cover_date <= vt for vf, vt in windows):
                continue
            missing_allocations.append(a)
            continue
        if int(a.id) in covered_alloc_ids or (
            int(a.product_id), int(a.supplier_id)
        ) in legacy_keys:
            continue
        missing_allocations.append(a)

    covered = total - len(missing_allocations)
    return {
        "shipped": total,
        "covered": covered,
        "missing": len(missing_allocations),
        "coverage_rate": round(covered / total * 100, 2) if total else 0.0,
        "missing_allocations": missing_allocations,
    }
