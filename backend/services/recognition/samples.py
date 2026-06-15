from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models import (
    Order,
    OrderReceivingLine,
    Product,
    SmartScaleRecognitionCategory,
    SmartScaleRecognitionRoiProfile,
    SmartScaleRecognitionSample,
)
from services.storage.minio_client import upload_smart_scale_recognition_bytes

from .roi import crop_image_bytes, download_image_bytes, profile_roi


logger = logging.getLogger(__name__)
SOHE_FIXED_DEVICE_ID = "uvc-product-1"


def canonical_roi_device_id(device_id: str | None) -> str:
    normalized = str(device_id or "").strip()
    return SOHE_FIXED_DEVICE_ID if normalized.lower().startswith("uvc") else normalized


def product_id_for_order_line(order: Order, line_index: int) -> int | None:
    idx = int(line_index) - 1
    items = order.items_json or []
    snapshots = order.items_snapshot_json or []
    if idx < 0 or idx >= len(items):
        return None
    item = items[idx] if isinstance(items[idx], dict) else {}
    snapshot = snapshots[idx] if idx < len(snapshots) and isinstance(snapshots[idx], dict) else {}
    value = item.get("product_id") or snapshot.get("product_id")
    try:
        product_id = int(value or 0)
    except (TypeError, ValueError):
        return None
    return product_id if product_id > 0 else None


async def ensure_category_for_product(
    db: AsyncSession,
    product: Product,
) -> SmartScaleRecognitionCategory:
    category = await db.scalar(
        select(SmartScaleRecognitionCategory).where(
            SmartScaleRecognitionCategory.product_id == int(product.id),
            SmartScaleRecognitionCategory.is_deleted.is_(False),
        )
    )
    if category:
        return category
    category = SmartScaleRecognitionCategory(
        name=product.name or f"商品#{product.id}",
        product_id=int(product.id),
        product_name=product.name,
        source="receiving",
    )
    db.add(category)
    await db.flush()
    return category


async def active_roi_profile(
    db: AsyncSession,
    device_id: str | None,
) -> SmartScaleRecognitionRoiProfile | None:
    normalized = canonical_roi_device_id(device_id)
    if not normalized:
        return None
    return await db.scalar(
        select(SmartScaleRecognitionRoiProfile)
        .where(
            SmartScaleRecognitionRoiProfile.device_id == normalized,
            SmartScaleRecognitionRoiProfile.status == "active",
        )
        .order_by(SmartScaleRecognitionRoiProfile.version.desc())
    )


async def process_sample_crop(
    db: AsyncSession,
    sample: SmartScaleRecognitionSample,
    *,
    profile: SmartScaleRecognitionRoiProfile | None = None,
    roi_override: dict | None = None,
) -> SmartScaleRecognitionSample:
    if roi_override:
        roi = roi_override
        sample.roi_override_json = roi_override
    else:
        profile = profile or await active_roi_profile(db, sample.device_id)
        if not profile:
            sample.cropped_image_url = None
            sample.roi_profile_id = None
            sample.roi_version = None
            sample.quality_status = "pending"
            sample.quality_reason = "未配置设备 ROI"
            sample.review_status = "needs_attention"
            return sample
        roi = profile_roi(profile)
        sample.roi_profile_id = int(profile.id)
        sample.roi_version = int(profile.version)
        sample.roi_override_json = None

    try:
        original_url = sample.original_image_url or sample.image_url
        original = await download_image_bytes(original_url)
        result = crop_image_bytes(original, roi)
        sample.cropped_image_url = await upload_smart_scale_recognition_bytes(result.data)
        sample.quality = result.quality_score
        sample.quality_status = result.quality_status
        sample.quality_reason = result.quality_reason
        sample.review_status = "pending" if result.quality_status == "passed" else "needs_attention"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to crop smart-scale sample id=%s", sample.id)
        sample.cropped_image_url = None
        sample.quality_status = "failed"
        sample.quality_reason = str(exc)[:255]
        sample.review_status = "needs_attention"
    return sample


async def create_receiving_candidate(
    db: AsyncSession,
    order_id: int,
    line_index: int,
) -> tuple[SmartScaleRecognitionSample | None, str]:
    existing = await db.scalar(
        select(SmartScaleRecognitionSample).where(
            SmartScaleRecognitionSample.order_id == int(order_id),
            SmartScaleRecognitionSample.line_index == int(line_index),
            SmartScaleRecognitionSample.is_deleted.is_(False),
        )
    )
    if existing:
        return existing, "duplicate"

    receiving_line = await db.scalar(
        select(OrderReceivingLine).where(
            OrderReceivingLine.order_id == int(order_id),
            OrderReceivingLine.line_index == int(line_index),
        )
    )
    order = await db.scalar(select(Order).where(Order.id == int(order_id)))
    if (
        not receiving_line
        or not order
        or str(receiving_line.status) != "confirmed"
        or not receiving_line.lock_photo_url
    ):
        return None, "not_ready"

    product_id = product_id_for_order_line(order, line_index)
    if not product_id:
        return None, "missing_product"
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    if not product:
        return None, "missing_product"

    category = await ensure_category_for_product(db, product)
    sample = SmartScaleRecognitionSample(
        category_id=int(category.id),
        image_url=receiving_line.lock_photo_url,
        original_image_url=receiving_line.lock_photo_url,
        angle="收货",
        source="receiving",
        product_id=int(product.id),
        order_id=int(order_id),
        line_index=int(line_index),
        device_id=(receiving_line.lock_photo_device_id or "").strip() or None,
        review_status="pending",
        quality_status="pending",
    )
    db.add(sample)
    await db.flush()
    await process_sample_crop(db, sample)
    return sample, "created"


async def create_receiving_candidate_background(order_id: int, line_index: int) -> None:
    try:
        async with SessionLocal() as db:
            await create_receiving_candidate(db, order_id, line_index)
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Smart-scale candidate creation failed order=%s line=%s",
            order_id,
            line_index,
        )
