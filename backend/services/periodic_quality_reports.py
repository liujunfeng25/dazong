from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Order,
    OrderItemAllocation,
    PeriodicQualityReport,
    Product,
    SupplierProductQuote,
)
from services.quality_report_attachments import file_urls_from_row

MAX_PERIOD_DAYS = 366
ACTIVE_REPORT_STATUSES = {"待审核", "已通过"}


def period_days(valid_from: date, valid_to: date) -> int:
    return (valid_to - valid_from).days + 1


def validate_period(valid_from: date, valid_to: date) -> None:
    if valid_to < valid_from:
        raise HTTPException(400, "有效期结束日期不能早于开始日期")
    days = period_days(valid_from, valid_to)
    if days > MAX_PERIOD_DAYS:
        raise HTTPException(400, f"周期报告有效期最长为 {MAX_PERIOD_DAYS} 天")


def periods_overlap(
    left_from: date,
    left_to: date,
    right_from: date,
    right_to: date,
) -> bool:
    return left_from <= right_to and left_to >= right_from


async def assert_provider_can_upload(
    db: AsyncSession,
    user,
    product_id: int,
) -> Product:
    if str(user.role) not in {"supplier", "factory"}:
        raise HTTPException(403, "仅供货商或厂家可上传周期质检报告")
    if str(getattr(user, "status", "")) != "active":
        raise HTTPException(403, "上传主体已停用")
    product = await db.scalar(
        select(Product).where(
            Product.id == int(product_id),
            Product.is_deleted.is_(False),
            Product.status == "active",
            Product.quality_report_mode == "periodic",
        )
    )
    if not product:
        raise HTTPException(404, "该商品不存在、已停用或未设置为周期报告模式")
    if str(user.role) == "supplier":
        if bool(product.is_designated_factory):
            raise HTTPException(403, "指定厂家商品仅允许对应厂家上传周期报告")
        quote_exists = await db.scalar(
            select(SupplierProductQuote.id)
            .where(
                SupplierProductQuote.supplier_id == int(user.id),
                SupplierProductQuote.product_id == int(product_id),
            )
            .limit(1)
        )
        if quote_exists is None:
            raise HTTPException(403, "仅可为当前账号已报价的商品上传周期报告")
    elif not (
        bool(product.is_designated_factory)
        and int(product.designated_factory_id or 0) == int(user.id)
    ):
        raise HTTPException(403, "厂家仅可上传指定给本厂的周期报告")
    return product


async def provider_product_options(db: AsyncSession, user) -> list[Product]:
    stmt = select(Product).where(
        Product.is_deleted.is_(False),
        Product.status == "active",
        Product.quality_report_mode == "periodic",
    )
    if str(user.role) == "supplier":
        stmt = stmt.join(
            SupplierProductQuote,
            SupplierProductQuote.product_id == Product.id,
        ).where(
            Product.is_designated_factory.is_(False),
            SupplierProductQuote.supplier_id == int(user.id),
        )
    elif str(user.role) == "factory":
        stmt = stmt.where(
            Product.is_designated_factory.is_(True),
            Product.designated_factory_id == int(user.id),
        )
    else:
        raise HTTPException(403, "仅供货商或厂家可查看可上传商品")
    return (await db.scalars(stmt.order_by(Product.id.desc()))).all()


async def overlapping_reports(
    db: AsyncSession,
    *,
    provider_id: int,
    product_id: int,
    valid_from: date,
    valid_to: date,
    exclude_ids: Optional[set[int]] = None,
    lock: bool = False,
) -> list[PeriodicQualityReport]:
    stmt = select(PeriodicQualityReport).where(
        PeriodicQualityReport.provider_id == int(provider_id),
        PeriodicQualityReport.product_id == int(product_id),
        PeriodicQualityReport.status.in_(ACTIVE_REPORT_STATUSES),
        PeriodicQualityReport.valid_from <= valid_to,
        PeriodicQualityReport.valid_to >= valid_from,
    )
    excluded = {int(i) for i in (exclude_ids or set())}
    if excluded:
        stmt = stmt.where(PeriodicQualityReport.id.not_in(excluded))
    if lock:
        stmt = stmt.with_for_update()
    return (await db.scalars(stmt.order_by(PeriodicQualityReport.id.desc()))).all()


async def assert_no_overlap(
    db: AsyncSession,
    *,
    provider_id: int,
    product_id: int,
    valid_from: date,
    valid_to: date,
    exclude_ids: Optional[set[int]] = None,
    lock: bool = False,
) -> None:
    conflicts = await overlapping_reports(
        db,
        provider_id=provider_id,
        product_id=product_id,
        valid_from=valid_from,
        valid_to=valid_to,
        exclude_ids=exclude_ids,
        lock=lock,
    )
    if conflicts:
        labels = "、".join(f"{r.report_no}(#{int(r.id)})" for r in conflicts[:3])
        raise HTTPException(409, f"有效期与现有待审核或已通过报告重叠：{labels}")


def quality_cover_date_for_order(order: Order) -> date:
    return order.expected_delivery_date or order.created_at.date()


async def approved_periodic_report_for(
    db: AsyncSession,
    *,
    provider_id: int,
    product_id: int,
    cover_date: date,
) -> Optional[PeriodicQualityReport]:
    return await db.scalar(
        select(PeriodicQualityReport)
        .where(
            PeriodicQualityReport.provider_id == int(provider_id),
            PeriodicQualityReport.product_id == int(product_id),
            PeriodicQualityReport.status == "已通过",
            PeriodicQualityReport.valid_from <= cover_date,
            PeriodicQualityReport.valid_to >= cover_date,
        )
        .order_by(PeriodicQualityReport.id.desc())
        .limit(1)
    )


async def approved_periodic_report_map(
    db: AsyncSession,
    allocations: Iterable[OrderItemAllocation],
    *,
    cover_date: date,
) -> dict[tuple[int, int], PeriodicQualityReport]:
    pairs = {
        (int(a.product_id), int(a.supplier_id))
        for a in allocations
        if a.product_id is not None and a.supplier_id is not None
    }
    if not pairs:
        return {}
    product_ids = sorted({pid for pid, _ in pairs})
    provider_ids = sorted({sid for _, sid in pairs})
    rows = (
        await db.scalars(
            select(PeriodicQualityReport)
            .where(
                PeriodicQualityReport.product_id.in_(product_ids),
                PeriodicQualityReport.provider_id.in_(provider_ids),
                PeriodicQualityReport.status == "已通过",
                PeriodicQualityReport.valid_from <= cover_date,
                PeriodicQualityReport.valid_to >= cover_date,
            )
            .order_by(PeriodicQualityReport.id.desc())
        )
    ).all()
    out: dict[tuple[int, int], PeriodicQualityReport] = {}
    for row in rows:
        key = (int(row.product_id), int(row.provider_id))
        if key in pairs and key not in out:
            out[key] = row
    return out


def periodic_report_payload(row: Optional[PeriodicQualityReport]) -> Optional[dict]:
    if not row:
        return None
    return {
        "id": int(row.id),
        "provider_id": int(row.provider_id),
        "product_id": int(row.product_id),
        "revision_of_id": (
            int(row.revision_of_id) if row.revision_of_id is not None else None
        ),
        "version": int(row.version or 1),
        "report_no": row.report_no,
        "status": row.status,
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        "file_url": row.file_url,
        "file_urls": file_urls_from_row(row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def active_orders_for_periodic_report(
    db: AsyncSession,
    *,
    provider_id: int,
    product_id: int,
    valid_from: date,
    valid_to: date,
) -> list[Order]:
    active_statuses = {"下单", "配货", "发货", "收货"}
    rows = (
        await db.scalars(
            select(Order)
            .join(OrderItemAllocation, OrderItemAllocation.order_id == Order.id)
            .where(
                OrderItemAllocation.supplier_id == int(provider_id),
                OrderItemAllocation.product_id == int(product_id),
                Order.status.in_(active_statuses),
            )
            .distinct()
        )
    ).all()
    out = []
    for order in rows:
        cover_date = quality_cover_date_for_order(order)
        if valid_from <= cover_date <= valid_to:
            out.append(order)
    return out


async def product_quality_mode_map(db: AsyncSession, product_ids: Iterable[int]) -> dict[int, str]:
    ids = sorted({int(pid) for pid in product_ids if int(pid or 0) > 0})
    if not ids:
        return {}
    rows = (await db.execute(select(Product.id, Product.quality_report_mode).where(Product.id.in_(ids)))).all()
    return {int(pid): str(mode or "batch") for pid, mode in rows}
