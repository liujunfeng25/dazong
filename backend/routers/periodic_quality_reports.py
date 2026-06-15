from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_role
from models import PeriodicQualityReport, Product, User
from schemas.quality_reports import PeriodicQualityReportReviewIn
from services.audit_service import write_audit_log
from services.order_quality_missing import refresh_order_has_abnormal_for_quality
from services.periodic_quality_reports import (
    ACTIVE_REPORT_STATUSES,
    active_orders_for_periodic_report,
    assert_no_overlap,
    assert_provider_can_upload,
    period_days,
    provider_product_options,
    validate_period,
)
from services.quality_report_attachments import (
    MAX_FILES_PER_REPORT,
    delete_public_urls,
    file_urls_from_row,
    periodic_quality_report_to_dict,
    persist_urls_to_row,
    validate_and_upload_files,
)

router = APIRouter(prefix="/periodic-quality-reports", tags=["periodic-quality-reports"])


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError as exc:
        raise HTTPException(400, f"{field} 格式需为 YYYY-MM-DD") from exc


async def _refresh_affected_orders(
    db: AsyncSession,
    *,
    provider_id: int,
    product_id: int,
    valid_from: date,
    valid_to: date,
) -> None:
    orders = await active_orders_for_periodic_report(
        db,
        provider_id=provider_id,
        product_id=product_id,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    for order in orders:
        await refresh_order_has_abnormal_for_quality(db, order)


async def _rows_with_names(
    db: AsyncSession,
    rows: list[PeriodicQualityReport],
) -> list[dict]:
    if not rows:
        return []
    product_ids = sorted({int(r.product_id) for r in rows})
    provider_ids = sorted({int(r.provider_id) for r in rows})
    products = (await db.scalars(select(Product).where(Product.id.in_(product_ids)))).all()
    providers = (await db.scalars(select(User).where(User.id.in_(provider_ids)))).all()
    all_related = (
        await db.scalars(
            select(PeriodicQualityReport).where(
                PeriodicQualityReport.provider_id.in_(provider_ids),
                PeriodicQualityReport.product_id.in_(product_ids),
            )
        )
    ).all()
    product_map = {int(p.id): p for p in products}
    provider_map = {int(u.id): u for u in providers}
    superseded_by = {
        int(r.revision_of_id): int(r.id)
        for r in all_related
        if r.revision_of_id is not None and str(r.status) in {"已通过", "已失效"}
    }
    out = []
    for row in rows:
        payload = periodic_quality_report_to_dict(row)
        product = product_map.get(int(row.product_id))
        provider = provider_map.get(int(row.provider_id))
        payload["product_name"] = product.name if product else f"商品#{int(row.product_id)}"
        payload["product_spec"] = product.spec if product else ""
        payload["provider_name"] = (
            provider.company_name or provider.username if provider else f"供货主体#{int(row.provider_id)}"
        )
        payload["provider_role"] = provider.role if provider else ""
        payload["revision_of_id"] = (
            int(row.revision_of_id) if row.revision_of_id is not None else None
        )
        payload["version"] = int(row.version or 1)
        payload["period_days"] = period_days(row.valid_from, row.valid_to)
        payload["superseded_by_id"] = superseded_by.get(int(row.id))
        payload["upload_eligible"] = False
        if provider is not None:
            try:
                await assert_provider_can_upload(db, provider, int(row.product_id))
                payload["upload_eligible"] = True
            except HTTPException:
                payload["upload_eligible"] = False
        conflicts = [
            int(other.id)
            for other in all_related
            if int(other.id) != int(row.id)
            and int(other.provider_id) == int(row.provider_id)
            and int(other.product_id) == int(row.product_id)
            and str(other.status) in ACTIVE_REPORT_STATUSES
            and str(row.status) in ACTIVE_REPORT_STATUSES
            and row.valid_from <= other.valid_to
            and row.valid_to >= other.valid_from
            and int(other.id) != int(row.revision_of_id or 0)
            and int(other.revision_of_id or 0) != int(row.id)
        ]
        payload["conflict_report_ids"] = sorted(set(conflicts))
        payload["has_overlap_conflict"] = bool(conflicts)
        return_status = str(row.status)
        today = date.today()
        if return_status == "已通过" and row.valid_to < today:
            payload["effective_status"] = "已过期"
        elif return_status == "已通过" and row.valid_from > today:
            payload["effective_status"] = "未开始"
        else:
            payload["effective_status"] = return_status
        out.append(payload)
    return out


@router.get("/products")
async def list_periodic_report_products(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await provider_product_options(db, user)
    return [
        {
            "id": int(p.id),
            "name": p.name,
            "spec": p.spec or "",
            "unit": p.unit or "",
            "quality_report_mode": p.quality_report_mode or "batch",
            "is_designated_factory": bool(p.is_designated_factory),
        }
        for p in rows
    ]


@router.get("")
async def list_periodic_reports(
    status: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    provider_id: Optional[int] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PeriodicQualityReport)
    if str(user.role) in {"supplier", "factory"}:
        stmt = stmt.where(PeriodicQualityReport.provider_id == int(user.id))
    elif str(user.role) != "operation":
        raise HTTPException(403, "无权限查看周期质检报告")
    if status:
        stmt = stmt.where(PeriodicQualityReport.status == status)
    if product_id:
        stmt = stmt.where(PeriodicQualityReport.product_id == int(product_id))
    if provider_id and str(user.role) == "operation":
        stmt = stmt.where(PeriodicQualityReport.provider_id == int(provider_id))
    rows = (await db.scalars(stmt.order_by(PeriodicQualityReport.id.desc()).limit(500))).all()
    return await _rows_with_names(db, rows)


@router.post("")
async def upload_periodic_report(
    request: Request,
    product_id: int = Form(...),
    valid_from: str = Form(...),
    valid_to: str = Form(...),
    report_no: str = Form(...),
    files: list[UploadFile] = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await assert_provider_can_upload(db, user, int(product_id))
    start = _parse_date(valid_from, "valid_from")
    end = _parse_date(valid_to, "valid_to")
    validate_period(start, end)
    await assert_no_overlap(
        db,
        provider_id=int(user.id),
        product_id=int(product_id),
        valid_from=start,
        valid_to=end,
        lock=True,
    )
    urls = await validate_and_upload_files(files)
    try:
        row = PeriodicQualityReport(
            provider_id=int(user.id),
            product_id=int(product_id),
            version=1,
            valid_from=start,
            valid_to=end,
            report_no=(report_no or "").strip()
            or f"PQR-{int(product_id)}-{datetime.utcnow().strftime('%H%M%S')}",
            status="待审核",
            created_at=datetime.utcnow(),
        )
        persist_urls_to_row(urls, row)
        db.add(row)
        await db.flush()
        await write_audit_log(
            db=db,
            actor_user_id=int(user.id),
            action="periodic_quality_report_upload",
            category="quality",
            object_type="periodic_quality_report",
            object_id=int(row.id),
            detail=f"上传周期质检报告 {row.report_no}",
            source_ip=request.client.host if request.client else "",
            after_json={
                "status": row.status,
                "product_id": int(row.product_id),
                "valid_from": row.valid_from.isoformat(),
                "valid_to": row.valid_to.isoformat(),
                "version": int(row.version),
            },
        )
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        delete_public_urls(urls)
        raise
    return (await _rows_with_names(db, [row]))[0]


@router.post("/{report_id}/append")
async def append_periodic_report_attachments(
    report_id: int,
    files: list[UploadFile] = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(PeriodicQualityReport).where(PeriodicQualityReport.id == report_id))
    if not row:
        raise HTTPException(404, "周期报告不存在")
    if str(user.role) not in {"supplier", "factory"} or int(row.provider_id) != int(user.id):
        raise HTTPException(403, "无权修改该周期报告")
    if str(row.status) != "待审核":
        raise HTTPException(409, "仅待审核报告可直接修改附件；已通过报告请提交新版本")
    await assert_provider_can_upload(db, user, int(row.product_id))
    existing = file_urls_from_row(row)
    new_urls = await validate_and_upload_files(files)
    if len(existing) + len(new_urls) > MAX_FILES_PER_REPORT:
        delete_public_urls(new_urls)
        raise HTTPException(400, f"附件总数不能超过 {MAX_FILES_PER_REPORT} 张")
    persist_urls_to_row(existing + new_urls, row)
    await _refresh_affected_orders(
        db,
        provider_id=int(row.provider_id),
        product_id=int(row.product_id),
        valid_from=row.valid_from,
        valid_to=row.valid_to,
    )
    await db.commit()
    await db.refresh(row)
    return (await _rows_with_names(db, [row]))[0]


@router.patch("/{report_id}/attachments/{index}")
async def replace_periodic_report_attachment(
    report_id: int,
    index: int,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if index < 0:
        raise HTTPException(400, "index 无效")
    row = await db.scalar(select(PeriodicQualityReport).where(PeriodicQualityReport.id == report_id))
    if not row:
        raise HTTPException(404, "周期报告不存在")
    if str(user.role) not in {"supplier", "factory"} or int(row.provider_id) != int(user.id):
        raise HTTPException(403, "无权修改该周期报告")
    if str(row.status) != "待审核":
        raise HTTPException(409, "仅待审核报告可直接修改附件；已通过报告请提交新版本")
    await assert_provider_can_upload(db, user, int(row.product_id))
    urls = file_urls_from_row(row)
    if index >= len(urls):
        raise HTTPException(400, "下标超出已有附件数量")
    old_url = urls[index]
    new_url = (await validate_and_upload_files([file]))[0]
    urls[index] = new_url
    persist_urls_to_row(urls, row)
    try:
        await _refresh_affected_orders(
            db,
            provider_id=int(row.provider_id),
            product_id=int(row.product_id),
            valid_from=row.valid_from,
            valid_to=row.valid_to,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        delete_public_urls([new_url])
        raise
    delete_public_urls([old_url])
    await db.refresh(row)
    return (await _rows_with_names(db, [row]))[0]


@router.post("/{report_id}/revisions")
async def create_periodic_report_revision(
    report_id: int,
    request: Request,
    valid_from: str = Form(...),
    valid_to: str = Form(...),
    report_no: str = Form(...),
    files: list[UploadFile] = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = await db.scalar(
        select(PeriodicQualityReport).where(PeriodicQualityReport.id == report_id)
    )
    if not target:
        raise HTTPException(404, "周期报告不存在")
    if str(user.role) not in {"supplier", "factory"} or int(target.provider_id) != int(user.id):
        raise HTTPException(403, "无权为该周期报告提交新版本")
    if str(target.status) != "已通过":
        raise HTTPException(409, "仅已通过报告可提交新版本")
    await assert_provider_can_upload(db, user, int(target.product_id))
    start = _parse_date(valid_from, "valid_from")
    end = _parse_date(valid_to, "valid_to")
    validate_period(start, end)
    await assert_no_overlap(
        db,
        provider_id=int(target.provider_id),
        product_id=int(target.product_id),
        valid_from=start,
        valid_to=end,
        exclude_ids={int(target.id)},
        lock=True,
    )
    urls = await validate_and_upload_files(files)
    try:
        row = PeriodicQualityReport(
            provider_id=int(target.provider_id),
            product_id=int(target.product_id),
            revision_of_id=int(target.id),
            version=int(target.version or 1) + 1,
            valid_from=start,
            valid_to=end,
            report_no=(report_no or "").strip()
            or f"{target.report_no}-V{int(target.version or 1) + 1}",
            status="待审核",
            created_at=datetime.utcnow(),
        )
        persist_urls_to_row(urls, row)
        db.add(row)
        await db.flush()
        await write_audit_log(
            db=db,
            actor_user_id=int(user.id),
            action="periodic_quality_report_revision",
            category="quality",
            object_type="periodic_quality_report",
            object_id=int(row.id),
            detail=f"为报告 #{int(target.id)} 提交版本 {int(row.version)}",
            source_ip=request.client.host if request.client else "",
            before_json={
                "report_id": int(target.id),
                "status": target.status,
                "version": int(target.version or 1),
            },
            after_json={
                "status": row.status,
                "valid_from": row.valid_from.isoformat(),
                "valid_to": row.valid_to.isoformat(),
                "version": int(row.version),
            },
        )
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        delete_public_urls(urls)
        raise
    return (await _rows_with_names(db, [row]))[0]


@router.post("/{report_id}/review")
async def review_periodic_report(
    report_id: int,
    payload: PeriodicQualityReportReviewIn,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(PeriodicQualityReport)
        .where(PeriodicQualityReport.id == report_id)
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "周期报告不存在")
    if str(row.status) != "待审核":
        raise HTTPException(409, "该报告已审核，不能重复操作")
    status = str(payload.status or "").strip()
    if status not in {"已通过", "已驳回"}:
        raise HTTPException(400, "审核状态仅支持已通过或已驳回")
    reject_reason = str(payload.reject_reason or "").strip()
    if status == "已驳回" and not reject_reason:
        raise HTTPException(400, "驳回时请填写原因")
    before_json = {
        "status": row.status,
        "reviewed_by": row.reviewed_by,
        "revision_of_id": row.revision_of_id,
    }
    replaced = None
    if status == "已通过":
        provider = await db.scalar(select(User).where(User.id == int(row.provider_id)))
        if not provider:
            raise HTTPException(409, "报告上传主体不存在")
        await assert_provider_can_upload(db, provider, int(row.product_id))
        validate_period(row.valid_from, row.valid_to)
        pair_rows = (
            await db.scalars(
                select(PeriodicQualityReport)
                .where(
                    PeriodicQualityReport.provider_id == int(row.provider_id),
                    PeriodicQualityReport.product_id == int(row.product_id),
                )
                .with_for_update()
            )
        ).all()
        excluded = {int(row.id)}
        if row.revision_of_id is not None:
            replaced = next(
                (r for r in pair_rows if int(r.id) == int(row.revision_of_id)),
                None,
            )
            if not replaced or str(replaced.status) != "已通过":
                raise HTTPException(409, "被修订的原报告已不再生效，请重新提交")
            excluded.add(int(replaced.id))
        await assert_no_overlap(
            db,
            provider_id=int(row.provider_id),
            product_id=int(row.product_id),
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            exclude_ids=excluded,
            lock=True,
        )
        if replaced is not None:
            replaced.status = "已失效"
    row.status = status
    row.reviewed_by = int(user.id)
    row.reviewed_at = datetime.utcnow()
    row.reject_reason = reject_reason if status == "已驳回" else None
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action=(
            "periodic_quality_report_approve"
            if status == "已通过"
            else "periodic_quality_report_reject"
        ),
        category="quality",
        object_type="periodic_quality_report",
        object_id=int(row.id),
        detail=f"周期报告 {row.report_no} 审核为{status}",
        source_ip=request.client.host if request.client else "",
        before_json=before_json,
        after_json={
            "status": status,
            "reviewed_by": int(user.id),
            "replaced_report_id": int(replaced.id) if replaced else None,
        },
    )
    await _refresh_affected_orders(
        db,
        provider_id=int(row.provider_id),
        product_id=int(row.product_id),
        valid_from=row.valid_from,
        valid_to=row.valid_to,
    )
    if replaced is not None and (
        replaced.valid_from != row.valid_from or replaced.valid_to != row.valid_to
    ):
        await _refresh_affected_orders(
            db,
            provider_id=int(replaced.provider_id),
            product_id=int(replaced.product_id),
            valid_from=replaced.valid_from,
            valid_to=replaced.valid_to,
        )
    await db.commit()
    await db.refresh(row)
    return (await _rows_with_names(db, [row]))[0]
