import io
import json
import math
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_role
from models import (
    Order,
    OrderReceivingLine,
    Product,
    SmartScaleRecognitionCategory,
    SmartScaleRecognitionPackage,
    SmartScaleRecognitionRoiProfile,
    SmartScaleRecognitionSample,
    SmartScaleRecognitionTrainTask,
)
from services.recognition import inference as ssr_inference
from services.recognition import train_runner as ssr_train_runner
from services.recognition.materialize import materialize_task
from services.recognition.roi import crop_image_bytes, normalize_roi, profile_roi
from services.recognition.samples import (
    active_roi_profile,
    canonical_roi_device_id,
    create_receiving_candidate,
    ensure_category_for_product,
    process_sample_crop,
)
from services.recognition.paths import (
    ensure_dirs,
    task_class_mapping_file,
    task_dataset_dir,
    task_model_file,
)
from services.storage.minio_client import upload_smart_scale_recognition_sample

router = APIRouter(prefix="/smart-scale-recognition", tags=["smart-scale-recognition"])


class RecognitionCategoryIn(BaseModel):
    name: str
    product_id: Optional[int] = None
    product_name: Optional[str] = None


class RoiProfileIn(BaseModel):
    device_id: str
    device_name: Optional[str] = None
    x: float
    y: float
    width: float
    height: float
    rotation: int = 0
    reference_image_url: Optional[str] = None


class SampleReviewIn(BaseModel):
    sample_ids: list[int]
    status: str
    rejection_reason: Optional[str] = None


class SampleRecropIn(BaseModel):
    sample_ids: list[int]
    device_id: Optional[str] = None
    roi_override: Optional[dict] = None


def _utc_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


def _default_device_name(device_id: str) -> str:
    if device_id.lower().startswith("uvc"):
        return "首衡智能秤"
    return device_id


def _device_display_name(
    device_id: str,
    profile: Optional[SmartScaleRecognitionRoiProfile],
) -> str:
    if device_id.lower().startswith("uvc"):
        return "首衡智能秤"
    return profile.device_name if profile and profile.device_name else _default_device_name(device_id)


def _centroid(features: list[list[float]]) -> list[float]:
    usable = [f for f in features if isinstance(f, list) and len(f) >= 24]
    if not usable:
        return []
    out = [0.0] * 24
    for f in usable:
        for i in range(24):
            out[i] += float(f[i])
    out = [v / len(usable) for v in out]
    norm = math.sqrt(sum(v * v for v in out)) or 1.0
    return [round(v / norm, 6) for v in out]


async def _serialize_category(db: AsyncSession, row: SmartScaleRecognitionCategory) -> dict:
    total_sample_count = int(
        (await db.scalar(
            select(func.count())
            .select_from(SmartScaleRecognitionSample)
            .where(SmartScaleRecognitionSample.category_id == row.id, SmartScaleRecognitionSample.is_deleted.is_(False))
        ))
        or 0
    )
    status_rows = (
        await db.execute(
            select(SmartScaleRecognitionSample.review_status, func.count())
            .where(
                SmartScaleRecognitionSample.category_id == row.id,
                SmartScaleRecognitionSample.is_deleted.is_(False),
            )
            .group_by(SmartScaleRecognitionSample.review_status)
        )
    ).all()
    status_counts = {str(status): int(count) for status, count in status_rows}
    sample_count = int(
        (
            await db.scalar(
                select(func.count())
                .select_from(SmartScaleRecognitionSample)
                .where(
                    SmartScaleRecognitionSample.category_id == row.id,
                    SmartScaleRecognitionSample.is_deleted.is_(False),
                    SmartScaleRecognitionSample.review_status == "approved",
                    SmartScaleRecognitionSample.quality_status == "passed",
                )
            )
        )
        or 0
    )
    return {
        "id": row.id,
        "name": row.name,
        "product_id": row.product_id,
        "product_name": row.product_name,
        "status": row.status,
        "source": row.source,
        "sample_count": sample_count,
        "total_sample_count": total_sample_count,
        "review_counts": status_counts,
        "created_at": _utc_iso(row.created_at),
        "updated_at": _utc_iso(row.created_at),
    }


@router.get("/categories")
async def list_categories(_=Depends(require_role("operation")), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(SmartScaleRecognitionCategory)
            .where(SmartScaleRecognitionCategory.is_deleted.is_(False))
            .order_by(SmartScaleRecognitionCategory.id.desc())
        )
    ).all()
    return {"items": [await _serialize_category(db, r) for r in rows]}


@router.post("/categories")
async def create_category(
    payload: RecognitionCategoryIn,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "类别名称不能为空")
    product_name = (payload.product_name or "").strip() or None
    if payload.product_id:
        product = await db.scalar(select(Product).where(Product.id == payload.product_id, Product.is_deleted.is_(False)))
        if not product:
            raise HTTPException(400, "绑定商品不存在")
        product_name = product_name or product.name
    row = SmartScaleRecognitionCategory(
        name=name,
        product_id=payload.product_id,
        product_name=product_name,
        source="manual",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return await _serialize_category(db, row)


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    payload: RecognitionCategoryIn,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(SmartScaleRecognitionCategory).where(SmartScaleRecognitionCategory.id == category_id, SmartScaleRecognitionCategory.is_deleted.is_(False)))
    if not row:
        raise HTTPException(404, "类别不存在")
    row.name = payload.name.strip()
    row.product_id = payload.product_id
    row.product_name = (payload.product_name or "").strip() or None
    await db.commit()
    await db.refresh(row)
    return await _serialize_category(db, row)


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int, _=Depends(require_role("operation")), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(SmartScaleRecognitionCategory).where(SmartScaleRecognitionCategory.id == category_id, SmartScaleRecognitionCategory.is_deleted.is_(False)))
    if not row:
        raise HTTPException(404, "类别不存在")
    row.is_deleted = True
    row.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


def _serialize_sample(row: SmartScaleRecognitionSample) -> dict:
    return {
        "id": row.id,
        "category_id": row.category_id,
        "image_url": row.image_url,
        "original_image_url": row.original_image_url or row.image_url,
        "cropped_image_url": row.cropped_image_url,
        "angle": row.angle,
        "quality": row.quality,
        "source": row.source,
        "product_id": row.product_id,
        "order_id": row.order_id,
        "line_index": row.line_index,
        "device_id": row.device_id,
        "roi_profile_id": row.roi_profile_id,
        "roi_version": row.roi_version,
        "roi_override": row.roi_override_json,
        "review_status": row.review_status,
        "quality_status": row.quality_status,
        "quality_reason": row.quality_reason,
        "rejection_reason": row.rejection_reason,
        "reviewed_at": _utc_iso(row.reviewed_at),
        "created_at": _utc_iso(row.created_at),
    }


@router.get("/categories/{category_id}/samples")
async def list_samples(
    category_id: int,
    review_status: Optional[str] = Query(None),
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    conditions = [
        SmartScaleRecognitionSample.category_id == category_id,
        SmartScaleRecognitionSample.is_deleted.is_(False),
    ]
    if review_status and review_status != "all":
        conditions.append(SmartScaleRecognitionSample.review_status == review_status)
    rows = (
        await db.scalars(
            select(SmartScaleRecognitionSample)
            .where(*conditions)
            .order_by(SmartScaleRecognitionSample.id.desc())
        )
    ).all()
    return {"items": [_serialize_sample(row) for row in rows]}


@router.post("/categories/{category_id}/samples")
async def upload_sample(
    category_id: int,
    file: UploadFile = File(...),
    angle: str = Form(""),
    quality: float = Form(0.0),
    feature_json: str = Form("[]"),
    upload_mode: str = Form("external"),
    device_id: Optional[str] = Form(None),
    roi_override_json: str = Form(""),
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    cat = await db.scalar(select(SmartScaleRecognitionCategory).where(SmartScaleRecognitionCategory.id == category_id, SmartScaleRecognitionCategory.is_deleted.is_(False)))
    if not cat:
        raise HTTPException(404, "类别不存在")
    try:
        feature = json.loads(feature_json or "[]")
    except Exception:
        feature = []
    image_url = await upload_smart_scale_recognition_sample(file)
    try:
        roi_override = json.loads(roi_override_json) if roi_override_json else None
        if roi_override:
            roi_override = normalize_roi(roi_override)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    row = SmartScaleRecognitionSample(
        category_id=category_id,
        image_url=image_url,
        original_image_url=image_url,
        angle=angle[:40],
        quality=quality,
        feature_json=feature,
        source="manual" if upload_mode == "external" else "device_manual",
        product_id=cat.product_id,
        device_id=(device_id or "").strip() or None,
        review_status="pending",
        quality_status="pending",
    )
    db.add(row)
    await db.flush()
    await process_sample_crop(db, row, roi_override=roi_override)
    await db.commit()
    await db.refresh(row)
    return _serialize_sample(row)


@router.delete("/samples/{sample_id}")
async def delete_sample(sample_id: int, _=Depends(require_role("operation")), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(SmartScaleRecognitionSample).where(SmartScaleRecognitionSample.id == sample_id, SmartScaleRecognitionSample.is_deleted.is_(False)))
    if not row:
        raise HTTPException(404, "样本不存在")
    row.is_deleted = True
    row.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


@router.post("/samples/review")
async def review_samples(
    payload: SampleReviewIn,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    status = payload.status.strip()
    if status not in {"approved", "rejected"}:
        raise HTTPException(400, "审核状态仅支持 approved/rejected")
    sample_ids = sorted({int(sample_id) for sample_id in payload.sample_ids if int(sample_id) > 0})
    rows = (
        await db.scalars(
            select(SmartScaleRecognitionSample).where(
                SmartScaleRecognitionSample.id.in_(sample_ids),
                SmartScaleRecognitionSample.is_deleted.is_(False),
            )
        )
    ).all()
    if not rows:
        raise HTTPException(404, "未找到可审核样本")
    if status == "approved":
        blocked = [
            row.id
            for row in rows
            if row.quality_status != "passed" or not row.cropped_image_url
        ]
        if blocked:
            raise HTTPException(400, f"样本 {blocked} 未通过质量检查或没有裁剪图")
    now = datetime.utcnow()
    for row in rows:
        row.review_status = status
        row.reviewed_by = int(getattr(user, "id", 0)) or None
        row.reviewed_at = now
        row.rejection_reason = (
            (payload.rejection_reason or "").strip()[:255] or None
            if status == "rejected"
            else None
        )
    await db.commit()
    return {"updated": len(rows), "status": status}


@router.post("/samples/recrop")
async def recrop_samples(
    payload: SampleRecropIn,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    sample_ids = sorted({int(sample_id) for sample_id in payload.sample_ids if int(sample_id) > 0})
    rows = (
        await db.scalars(
            select(SmartScaleRecognitionSample).where(
                SmartScaleRecognitionSample.id.in_(sample_ids),
                SmartScaleRecognitionSample.is_deleted.is_(False),
            )
        )
    ).all()
    if not rows:
        raise HTTPException(404, "未找到可重裁剪样本")
    roi_override = None
    if payload.roi_override:
        try:
            roi_override = normalize_roi(payload.roi_override)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    for row in rows:
        if payload.device_id is not None:
            row.device_id = payload.device_id.strip() or None
        row.review_status = "pending"
        row.reviewed_by = None
        row.reviewed_at = None
        row.rejection_reason = None
        await process_sample_crop(db, row, roi_override=roi_override)
    await db.commit()
    return {
        "updated": len(rows),
        "items": [_serialize_sample(row) for row in rows],
    }


def _serialize_roi_profile(row: SmartScaleRecognitionRoiProfile) -> dict:
    return {
        "id": row.id,
        "device_id": row.device_id,
        "device_name": row.device_name,
        "version": row.version,
        "x": row.x,
        "y": row.y,
        "width": row.width,
        "height": row.height,
        "rotation": row.rotation,
        "reference_image_url": row.reference_image_url,
        "status": row.status,
        "created_at": _utc_iso(row.created_at),
    }


@router.get("/devices")
async def list_devices(
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    lines = (
        await db.scalars(
            select(OrderReceivingLine)
            .where(
                OrderReceivingLine.lock_photo_device_id.is_not(None),
                OrderReceivingLine.lock_photo_device_id != "",
                OrderReceivingLine.status == "confirmed",
            )
            .order_by(OrderReceivingLine.lock_photo_taken_at.desc(), OrderReceivingLine.id.desc())
        )
    ).all()
    latest_by_device: dict[str, OrderReceivingLine] = {}
    for line in lines:
        device_id = canonical_roi_device_id(line.lock_photo_device_id)
        if device_id and device_id not in latest_by_device:
            latest_by_device[device_id] = line
    profiles = (
        await db.scalars(
            select(SmartScaleRecognitionRoiProfile).where(
                SmartScaleRecognitionRoiProfile.status == "active"
            )
        )
    ).all()
    profile_map = {row.device_id: row for row in profiles}
    return {
        "items": [
            {
                "device_id": device_id,
                "device_name": _device_display_name(device_id, profile_map.get(device_id)),
                "latest_image_url": line.lock_photo_url,
                "latest_photo_at": _utc_iso(line.lock_photo_taken_at),
                "roi_profile": (
                    _serialize_roi_profile(profile_map[device_id])
                    if device_id in profile_map
                    else None
                ),
            }
            for device_id, line in latest_by_device.items()
        ]
    }


@router.get("/roi-profiles")
async def list_roi_profiles(
    device_id: Optional[str] = Query(None),
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if device_id:
        conditions.append(SmartScaleRecognitionRoiProfile.device_id == device_id.strip())
    rows = (
        await db.scalars(
            select(SmartScaleRecognitionRoiProfile)
            .where(*conditions)
            .order_by(
                SmartScaleRecognitionRoiProfile.device_id.asc(),
                SmartScaleRecognitionRoiProfile.version.desc(),
            )
        )
    ).all()
    return {"items": [_serialize_roi_profile(row) for row in rows]}


@router.post("/roi-profiles")
async def create_roi_profile(
    payload: RoiProfileIn,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    device_id = payload.device_id.strip()
    if not device_id:
        raise HTTPException(400, "请选择设备")
    try:
        roi = normalize_roi(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    current = await active_roi_profile(db, device_id)
    version = int(
        (
            await db.scalar(
                select(func.max(SmartScaleRecognitionRoiProfile.version)).where(
                    SmartScaleRecognitionRoiProfile.device_id == device_id
                )
            )
        )
        or 0
    ) + 1
    if current:
        current.status = "archived"
    reference_image_url = (payload.reference_image_url or "").strip() or None
    if not reference_image_url:
        latest_line = await db.scalar(
            select(OrderReceivingLine)
            .where(OrderReceivingLine.lock_photo_device_id == device_id)
            .order_by(OrderReceivingLine.lock_photo_taken_at.desc(), OrderReceivingLine.id.desc())
        )
        reference_image_url = latest_line.lock_photo_url if latest_line else None
    row = SmartScaleRecognitionRoiProfile(
        device_id=device_id,
        device_name=(payload.device_name or "").strip()[:120] or None,
        version=version,
        reference_image_url=reference_image_url,
        created_by=int(getattr(user, "id", 0)) or None,
        status="active",
        **roi,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize_roi_profile(row)


@router.post("/publish")
async def publish_package(notes: str = "", _=Depends(require_role("operation")), db: AsyncSession = Depends(get_db)):
    cats = (
        await db.scalars(
            select(SmartScaleRecognitionCategory)
            .where(SmartScaleRecognitionCategory.is_deleted.is_(False), SmartScaleRecognitionCategory.status == "active")
            .order_by(SmartScaleRecognitionCategory.id.asc())
        )
    ).all()
    payload_cats = []
    for cat in cats:
        samples = (
            await db.scalars(
                select(SmartScaleRecognitionSample)
                .where(SmartScaleRecognitionSample.category_id == cat.id, SmartScaleRecognitionSample.is_deleted.is_(False))
            )
        ).all()
        features = [s.feature_json for s in samples if s.feature_json]
        center = _centroid(features)
        if not center:
            continue
        payload_cats.append({
            "id": f"remote-{cat.id}",
            "name": cat.name,
            "productId": cat.product_id,
            "productName": cat.product_name,
            "samples": [],
            "centroid": center,
            "updatedAt": int(datetime.utcnow().timestamp() * 1000),
            "sampleCount": len(samples),
        })
    if not payload_cats:
        raise HTTPException(400, "没有可发布的样本特征")
    version = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    await db.execute(SmartScaleRecognitionPackage.__table__.update().where(SmartScaleRecognitionPackage.status == "active").values(status="archived"))
    pkg = SmartScaleRecognitionPackage(version=version, status="active", payload_json={"version": version, "categories": payload_cats}, notes=notes, published_at=datetime.utcnow())
    db.add(pkg)
    await db.commit()
    await db.refresh(pkg)
    return {"id": pkg.id, "version": pkg.version, "category_count": len(payload_cats)}


@router.post("/packages/{package_id}/revoke")
async def revoke_package(package_id: int, _=Depends(require_role("operation")), db: AsyncSession = Depends(get_db)):
    pkg = await db.scalar(select(SmartScaleRecognitionPackage).where(SmartScaleRecognitionPackage.id == package_id))
    if not pkg:
        raise HTTPException(404, "发布包不存在")
    pkg.status = "revoked"
    await db.commit()
    return {"message": "ok"}


@router.get("/packages/latest")
async def latest_package(_=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    pkg = await db.scalar(
        select(SmartScaleRecognitionPackage)
        .where(SmartScaleRecognitionPackage.status == "active")
        .order_by(SmartScaleRecognitionPackage.id.desc())
    )
    if not pkg:
        return {"version": None, "categories": []}
    return pkg.payload_json


# ============================================================================
# 真训练（PyTorch MobileNetV2）—— 以下为 2026-05 升级新增端点
# ============================================================================


class ImportReceivingIn(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    product_ids: Optional[list[int]] = None
    limit: int = 500


async def _ensure_category_for_product(db: AsyncSession, product: Product) -> SmartScaleRecognitionCategory:
    """按 product_id 找已有类目；无则建一个（名称取 product.name）。"""
    return await ensure_category_for_product(db, product)


@router.post("/import-receiving")
async def import_receiving_samples(
    payload: ImportReceivingIn,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    """从已确认收货行批量导入样本：按订单行 product_id 自动归入对应 SKU 类目，去重幂等。"""
    # 1. 拉满足条件的收货行
    conds = [
        OrderReceivingLine.status == "confirmed",
        OrderReceivingLine.lock_photo_url.is_not(None),
        OrderReceivingLine.lock_photo_url != "",
    ]
    if payload.date_from:
        conds.append(OrderReceivingLine.confirmed_at >= datetime.combine(payload.date_from, datetime.min.time()))
    if payload.date_to:
        conds.append(OrderReceivingLine.confirmed_at <= datetime.combine(payload.date_to, datetime.max.time()))
    rl_rows = (
        await db.scalars(
            select(OrderReceivingLine)
            .where(and_(*conds))
            .order_by(OrderReceivingLine.confirmed_at.desc())
            .limit(max(1, min(payload.limit, 5000)))
        )
    ).all()
    if not rl_rows:
        return {"imported": 0, "skipped": 0, "by_product": [], "message": "没有符合条件的已确认收货行"}

    # 2. 批拉对应 Order 拿 items_json / items_snapshot_json
    order_ids = sorted({int(r.order_id) for r in rl_rows})
    orders = {
        int(o.id): o
        for o in (await db.scalars(select(Order).where(Order.id.in_(order_ids)))).all()
    }

    # 3. 解析 (product_id, image_url, order_id, line_index)
    triples: list[tuple[int, OrderReceivingLine]] = []
    for rl in rl_rows:
        order = orders.get(int(rl.order_id))
        if not order:
            continue
        items = order.items_json or []
        snaps = order.items_snapshot_json or []
        idx0 = int(rl.line_index) - 1
        if idx0 < 0 or idx0 >= len(items):
            continue
        item = items[idx0] or {}
        snap = snaps[idx0] if idx0 < len(snaps) and isinstance(snaps[idx0], dict) else {}
        pid = int(item.get("product_id") or snap.get("product_id") or 0)
        if pid <= 0:
            continue
        if payload.product_ids and pid not in set(payload.product_ids):
            continue
        triples.append((pid, rl))
    if not triples:
        return {"imported": 0, "skipped": 0, "by_product": [], "message": "未解析到带 product_id 的收货行"}

    # 4. 批拉 Product
    pid_set = sorted({pid for pid, _ in triples})
    products_map = {
        int(p.id): p
        for p in (
            await db.scalars(
                select(Product).where(Product.id.in_(pid_set), Product.is_deleted.is_(False))
            )
        ).all()
    }

    # 5. 复用日常自动入池链路，历史照片同样只进入待审核池
    imported = 0
    skipped = 0
    per_product: dict[int, int] = {}
    for pid, rl in triples:
        product = products_map.get(pid)
        if not product:
            skipped += 1
            continue
        _, outcome = await create_receiving_candidate(
            db,
            int(rl.order_id),
            int(rl.line_index),
        )
        if outcome != "created":
            skipped += 1
            continue
        imported += 1
        per_product[pid] = per_product.get(pid, 0) + 1
    await db.commit()
    by_product = [
        {"product_id": pid, "product_name": (products_map.get(pid).name if products_map.get(pid) else None), "count": cnt}
        for pid, cnt in sorted(per_product.items(), key=lambda x: -x[1])
    ]
    return {"imported": imported, "skipped": skipped, "by_product": by_product}


class TrainIn(BaseModel):
    epochs: int = 10
    batch_size: int = 16
    min_samples_per_class: int = 10
    notes: Optional[str] = None


async def _trainable_classes(db: AsyncSession, min_samples: int) -> list[dict]:
    """枚举满足最小样本数的活跃类目，附带 sample_count、product 信息。"""
    cats = (
        await db.scalars(
            select(SmartScaleRecognitionCategory)
            .where(
                SmartScaleRecognitionCategory.is_deleted.is_(False),
                SmartScaleRecognitionCategory.status == "active",
            )
            .order_by(SmartScaleRecognitionCategory.id.asc())
        )
    ).all()
    result: list[dict] = []
    for c in cats:
        cnt = int(
            (
                await db.scalar(
                    select(func.count())
                    .select_from(SmartScaleRecognitionSample)
                    .where(
                        SmartScaleRecognitionSample.category_id == c.id,
                        SmartScaleRecognitionSample.is_deleted.is_(False),
                        SmartScaleRecognitionSample.review_status == "approved",
                        SmartScaleRecognitionSample.quality_status == "passed",
                        SmartScaleRecognitionSample.cropped_image_url.is_not(None),
                    )
                )
            )
            or 0
        )
        if cnt < min_samples:
            continue
        result.append(
            {
                "category_id": int(c.id),
                "product_id": c.product_id,
                "product_name": c.product_name or c.name,
                "sample_count": cnt,
            }
        )
    return result


@router.post("/train")
async def start_training(
    payload: TrainIn,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    """启动一次真训练。同一时刻只允许 1 个 running 任务。"""
    if ssr_train_runner.is_running():
        raise HTTPException(409, "已有训练任务在跑，请等待其结束或取消")
    epochs = max(1, min(payload.epochs, 100))
    batch_size = max(1, min(payload.batch_size, 64))
    min_samples = max(2, payload.min_samples_per_class)

    trainable = await _trainable_classes(db, min_samples)
    if len(trainable) < 2:
        raise HTTPException(
            400,
            f"可训练类目不足 2 个（要求每类样本≥{min_samples}）。当前满足条件的类目数：{len(trainable)}",
        )

    ensure_dirs()
    version = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    task = SmartScaleRecognitionTrainTask(
        version=version,
        status="preparing",
        epochs=epochs,
        batch_size=batch_size,
        classes_json=trainable,
        roi_versions_json={
            row.device_id: {
                "profile_id": int(row.id),
                "version": int(row.version),
                **profile_roi(row),
            }
            for row in (
                await db.scalars(
                    select(SmartScaleRecognitionRoiProfile).where(
                        SmartScaleRecognitionRoiProfile.status == "active"
                    )
                )
            ).all()
        },
        notes=payload.notes,
        created_by=int(getattr(user, "id", 0)) or None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 把样本图拉到本地 ImageFolder 目录
    cat_ids = [c["category_id"] for c in trainable]
    counts = await materialize_task(db, task.id, cat_ids)
    # 剔除下载后实际仍不够的类目
    survived = [c for c in trainable if counts.get(c["category_id"], 0) >= min_samples]
    if len(survived) < 2:
        task.status = "error"
        task.error_message = (
            f"下载样本后可训练类目不足 2 个；类目下载结果：{counts}"
        )
        await db.commit()
        raise HTTPException(400, task.error_message)

    # idx -> cat_{cid}（与训练脚本 ImageFolder 排序一致：按目录名字典序）
    sorted_cats = sorted(survived, key=lambda c: f"cat_{c['category_id']}")
    mapping = {str(i): f"cat_{c['category_id']}" for i, c in enumerate(sorted_cats)}
    task.class_mapping_json = mapping
    task.classes_json = sorted_cats
    task.status = "running"
    await db.commit()

    ok = ssr_train_runner.start_train(
        task.id, task_dataset_dir(task.id), epochs=epochs, batch_size=batch_size
    )
    if not ok:
        task.status = "error"
        task.error_message = "训练子进程启动失败"
        await db.commit()
        raise HTTPException(500, task.error_message)
    return {
        "task_id": task.id,
        "version": task.version,
        "status": task.status,
        "classes": sorted_cats,
    }


async def _refresh_task_status(db: AsyncSession, task: SmartScaleRecognitionTrainTask) -> dict:
    """把 status.json 合并到 db；done/error 时落库 metrics/model_path。"""
    s = ssr_train_runner.get_status(task.id)
    stat = str(s.get("status") or "")
    changed = False
    if stat == "done" and task.status != "done":
        task.status = "done"
        task.metrics_json = {
            "val_acc": s.get("val_acc"),
            "train_acc": s.get("train_acc"),
            "loss": s.get("loss"),
        }
        task.model_path = str(task_model_file(task.id))
        changed = True
    elif stat == "error" and task.status != "error":
        task.status = "error"
        task.error_message = s.get("message") or "训练失败"
        changed = True
    if changed:
        await db.commit()
        await db.refresh(task)
    return {
        "task_id": task.id,
        "version": task.version,
        "status": task.status,
        "is_deployed": bool(task.is_deployed),
        "epochs": task.epochs,
        "batch_size": task.batch_size,
        "classes": task.classes_json or [],
        "metrics": task.metrics_json,
        "error_message": task.error_message,
        "roi_versions": task.roi_versions_json or {},
        "progress": s,
    }


@router.get("/train/{task_id}")
async def get_training_status(
    task_id: int,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    task = await db.scalar(select(SmartScaleRecognitionTrainTask).where(SmartScaleRecognitionTrainTask.id == task_id))
    if not task:
        raise HTTPException(404, "训练任务不存在")
    return await _refresh_task_status(db, task)


@router.post("/train/{task_id}/cancel")
async def cancel_training(
    task_id: int,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    task = await db.scalar(select(SmartScaleRecognitionTrainTask).where(SmartScaleRecognitionTrainTask.id == task_id))
    if not task:
        raise HTTPException(404, "训练任务不存在")
    if task.status not in ("preparing", "running"):
        return {"message": "任务非运行中，无需取消", "status": task.status}
    ssr_train_runner.cancel_task(task_id)
    task.status = "cancelled"
    await db.commit()
    return {"message": "ok", "status": task.status}


@router.get("/models")
async def list_models(
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.scalars(
            select(SmartScaleRecognitionTrainTask).order_by(SmartScaleRecognitionTrainTask.id.desc())
        )
    ).all()
    # 主动刷新仍在跑的任务，便于前端不用单独轮询每个
    out: list[dict] = []
    for r in rows:
        if r.status in ("preparing", "running"):
            out.append(await _refresh_task_status(db, r))
        else:
            out.append(
                {
                    "task_id": r.id,
                    "version": r.version,
                    "status": r.status,
                    "is_deployed": bool(r.is_deployed),
                    "epochs": r.epochs,
                    "batch_size": r.batch_size,
                    "classes": r.classes_json or [],
                    "metrics": r.metrics_json,
                    "error_message": r.error_message,
                    "roi_versions": r.roi_versions_json or {},
                    "created_at": _utc_iso(r.created_at),
                }
            )
    return {"items": out}


@router.post("/models/{task_id}/deploy")
async def deploy_model(
    task_id: int,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    task = await db.scalar(select(SmartScaleRecognitionTrainTask).where(SmartScaleRecognitionTrainTask.id == task_id))
    if not task:
        raise HTTPException(404, "训练任务不存在")
    if task.status != "done":
        raise HTTPException(400, f"仅完成的训练才能部署（当前状态：{task.status}）")
    if not task.model_path or not task_model_file(task.id).exists():
        raise HTTPException(400, "模型文件缺失")
    # 仅允许 1 个部署
    await db.execute(
        SmartScaleRecognitionTrainTask.__table__.update()
        .where(SmartScaleRecognitionTrainTask.is_deployed.is_(True))
        .values(is_deployed=False)
    )
    task.is_deployed = True
    await db.commit()
    # 推理缓存即时失效，下次 recognize 重新加载
    ssr_inference.evict(str(task_model_file(task.id)), str(task_class_mapping_file(task.id)))
    return {"message": "ok", "task_id": task.id, "version": task.version}


@router.post("/recognize")
async def recognize_image(
    file: UploadFile = File(...),
    device_id: Optional[str] = Form(None),
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    """运营端识别测试：上传一张图，返回 top-5 SKU 候选及置信度。"""
    task = await db.scalar(
        select(SmartScaleRecognitionTrainTask).where(
            SmartScaleRecognitionTrainTask.is_deployed.is_(True),
            SmartScaleRecognitionTrainTask.status == "done",
        )
    )
    if not task:
        raise HTTPException(503, "当前没有已部署的识别模型，请先训练并部署")
    model_path = task_model_file(task.id)
    mapping_path = task_class_mapping_file(task.id)
    if not model_path.exists():
        raise HTTPException(503, "已部署模型的文件丢失，请重新训练")

    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"图片解析失败: {e}")

    normalized_device_id = (device_id or "").strip()
    roi_versions = task.roi_versions_json or {}
    applied_roi = roi_versions.get(normalized_device_id) if normalized_device_id else None
    if roi_versions and not normalized_device_id:
        raise HTTPException(400, "请选择图片来源设备，确保识别使用模型绑定的 ROI")
    if normalized_device_id and not applied_roi:
        if roi_versions:
            raise HTTPException(400, "当前模型不包含该设备的 ROI 版本，请重新训练并部署")
        legacy_profile = await active_roi_profile(db, normalized_device_id)
        applied_roi = profile_roi(legacy_profile) if legacy_profile else None
    if normalized_device_id and not applied_roi:
        raise HTTPException(400, "该设备尚未配置 ROI")
    if applied_roi:
        try:
            cropped = crop_image_bytes(contents, applied_roi)
            image = Image.open(io.BytesIO(cropped.data)).convert("RGB")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    raw_top = ssr_inference.recognize(
        image,
        model_path=str(model_path),
        class_mapping_path=str(mapping_path) if mapping_path.exists() else None,
        device="cpu",
        top_k=5,
    )
    # label="cat_{id}" → 反查 Category / Product 信息
    cat_ids: list[int] = []
    for r in raw_top:
        lbl = str(r.get("label") or "")
        if lbl.startswith("cat_"):
            try:
                cat_ids.append(int(lbl[4:]))
            except ValueError:
                pass
    cat_map: dict[int, SmartScaleRecognitionCategory] = {}
    if cat_ids:
        rows = (
            await db.scalars(
                select(SmartScaleRecognitionCategory).where(
                    SmartScaleRecognitionCategory.id.in_(sorted(set(cat_ids)))
                )
            )
        ).all()
        cat_map = {int(c.id): c for c in rows}
    results = []
    for r in raw_top:
        lbl = str(r.get("label") or "")
        cid = None
        if lbl.startswith("cat_"):
            try:
                cid = int(lbl[4:])
            except ValueError:
                cid = None
        c = cat_map.get(int(cid)) if cid else None
        results.append(
            {
                "category_id": cid,
                "category_name": (c.name if c else None),
                "product_id": (c.product_id if c else None),
                "product_name": (c.product_name if c else None),
                "score": r.get("score"),
            }
        )
    return {
        "model_task_id": task.id,
        "model_version": task.version,
        "device_id": normalized_device_id or None,
        "roi_version": applied_roi.get("version") if applied_roi else None,
        "results": results,
    }
