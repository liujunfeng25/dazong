from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, parse_client_canteen_id_from_authorization, require_role
from models import ClientCanteen, Order, OrderItemAllocation, Product, QualityReport
from services.order_quality_missing import refresh_order_has_abnormal_for_quality
from services.quality_report_attachments import (
    MAX_FILES_PER_REPORT,
    delete_public_urls,
    file_urls_from_row,
    persist_urls_to_row,
    quality_report_to_dict,
    validate_and_upload_files,
)

router = APIRouter(prefix="/quality-reports", tags=["quality-reports"])


async def _can_view_order_quality_reports(
    db: AsyncSession, order_id: int, user, request: Optional[Request] = None
) -> bool:
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        return False
    role = str(user.role)
    if role in {"operation", "monitor"}:
        return True
    if role == "client":
        if int(order.client_id) != int(user.id):
            return False
        if request is None:
            return False
        raw_cid = parse_client_canteen_id_from_authorization(request.headers.get("authorization"))
        if raw_cid is None:
            return False
        if order.canteen_id is None or int(order.canteen_id) != int(raw_cid):
            return False
        ok = await db.scalar(
            select(ClientCanteen.id).where(
                ClientCanteen.id == int(raw_cid),
                ClientCanteen.school_client_id == user.id,
                ClientCanteen.status == "active",
            )
        )
        return bool(ok)
    if role == "delivery" and int(order.delivery_id) == int(user.id):
        return True
    if role == "supplier":
        return bool(
            await db.scalar(
                select(
                    exists(
                        select(OrderItemAllocation.id).where(
                            OrderItemAllocation.order_id == order_id,
                            OrderItemAllocation.supplier_id == user.id,
                        )
                    )
                )
            )
        )
    if role == "factory":
        return bool(
            await db.scalar(
                select(
                    exists(
                        select(OrderItemAllocation.id)
                        .join(Product, Product.id == OrderItemAllocation.product_id)
                        .where(
                            OrderItemAllocation.order_id == order_id,
                            Product.is_designated_factory.is_(True),
                            Product.designated_factory_id == user.id,
                        )
                    )
                )
            )
        )
    return False


def _assert_allocation_upload_role(
    user, allocation: OrderItemAllocation, product: Optional[Product]
) -> None:
    if str(user.role) not in {"supplier", "factory"}:
        raise HTTPException(403, "仅供货商或指定厂家可上传分单质检报告")
    if str(user.role) == "supplier":
        if int(allocation.supplier_id) != int(user.id):
            raise HTTPException(403, "无权上传非本户分单的质检报告")
    else:
        if not (
            product
            and bool(product.is_designated_factory)
            and int(product.designated_factory_id or 0) == int(user.id)
        ):
            raise HTTPException(403, "工厂仅可上传指定厂家商品对应分单的质检报告")


async def _save_quality_report_for_allocation(
    db: AsyncSession,
    allocation: OrderItemAllocation,
    report_supplier_id: int,
    urls: list[str],
    report_no: str,
) -> QualityReport:
    active_no = (report_no or "").strip() or f"QR-{int(allocation.id)}-{datetime.utcnow().strftime('%H%M%S')}"
    dups = (
        await db.scalars(
            select(QualityReport)
            .where(QualityReport.allocation_id == int(allocation.id))
            .order_by(QualityReport.id.desc())
        )
    ).all()
    if dups:
        target = dups[0]
        delete_public_urls(file_urls_from_row(target))
        persist_urls_to_row(urls, target)
        target.report_no = active_no
        target.status = "待审核"
        for extra in dups[1:]:
            delete_public_urls(file_urls_from_row(extra))
            await db.delete(extra)
        row = target
    else:
        row = QualityReport(
            supplier_id=report_supplier_id,
            product_id=int(allocation.product_id),
            order_id=int(allocation.order_id),
            allocation_id=int(allocation.id),
            report_no=active_no,
            status="待审核",
            created_at=datetime.utcnow(),
        )
        persist_urls_to_row(urls, row)
        db.add(row)
    order_entity = await db.scalar(select(Order).where(Order.id == int(allocation.order_id)))
    if order_entity:
        await refresh_order_has_abnormal_for_quality(db, order_entity)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("")
async def upload_report(
    product_id: int = Form(...),
    order_id: int = Form(...),
    allocation_id: Optional[int] = Form(None),
    report_no: str = Form(...),
    files: list[UploadFile] = File(...),
    user=Depends(require_role("factory")),
    db: AsyncSession = Depends(get_db),
):
    """指定厂家上传质检报告（仅 factory）；支持多图，表单字段名 files 可重复。"""
    allocation = await db.scalar(
        select(OrderItemAllocation)
        .join(Product, Product.id == OrderItemAllocation.product_id)
        .where(
            OrderItemAllocation.order_id == order_id,
            OrderItemAllocation.product_id == product_id,
            OrderItemAllocation.supplier_id == user.id,
            Product.is_designated_factory.is_(True),
            Product.designated_factory_id == user.id,
        )
        .order_by(OrderItemAllocation.id.desc())
    )
    if not allocation:
        raise HTTPException(400, "仅允许上传分配给本厂的指定厂家商品质检报告")
    if allocation_id is not None and int(allocation_id) != int(allocation.id):
        raise HTTPException(400, "分单行不匹配，无法上传报告")
    product = await db.scalar(select(Product).where(Product.id == allocation.product_id))
    _assert_allocation_upload_role(user, allocation, product)
    urls = await validate_and_upload_files(files)
    row = await _save_quality_report_for_allocation(db, allocation, int(user.id), urls, report_no)
    return quality_report_to_dict(row)


@router.post("/by-allocation")
async def upload_report_by_allocation(
    allocation_id: int = Form(...),
    report_no: str = Form(...),
    files: list[UploadFile] = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """供货商或工厂按分单上传质检报告（多图）；表单字段名 files 可重复。"""
    allocation = await db.scalar(
        select(OrderItemAllocation).where(OrderItemAllocation.id == allocation_id)
    )
    if not allocation:
        raise HTTPException(404, "分单不存在")
    product = await db.scalar(select(Product).where(Product.id == allocation.product_id))
    _assert_allocation_upload_role(user, allocation, product)
    urls = await validate_and_upload_files(files)
    report_supplier_id = int(user.id) if str(user.role) == "factory" else int(allocation.supplier_id)
    row = await _save_quality_report_for_allocation(db, allocation, report_supplier_id, urls, report_no)
    return quality_report_to_dict(row)


@router.post("/by-allocation/{allocation_id}/append")
async def append_quality_attachments(
    allocation_id: int,
    files: list[UploadFile] = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """在已有质检报告末尾追加附件（不删旧图）；总数不超过 MAX_FILES_PER_REPORT。"""
    allocation = await db.scalar(
        select(OrderItemAllocation).where(OrderItemAllocation.id == allocation_id)
    )
    if not allocation:
        raise HTTPException(404, "分单不存在")
    product = await db.scalar(select(Product).where(Product.id == allocation.product_id))
    _assert_allocation_upload_role(user, allocation, product)
    row = await db.scalar(
        select(QualityReport)
        .where(QualityReport.allocation_id == int(allocation.id))
        .order_by(QualityReport.id.desc())
        .limit(1)
    )
    if not row:
        raise HTTPException(404, "请先上传质检报告后再追加照片")
    existing = file_urls_from_row(row)
    new_urls = await validate_and_upload_files(files)
    if len(existing) + len(new_urls) > MAX_FILES_PER_REPORT:
        raise HTTPException(
            400,
            f"附件总数不能超过 {MAX_FILES_PER_REPORT} 张（当前 {len(existing)} 张，本次 {len(new_urls)} 张）",
        )
    merged = existing + new_urls
    persist_urls_to_row(merged, row)
    order_entity = await db.scalar(select(Order).where(Order.id == int(allocation.order_id)))
    if order_entity:
        await refresh_order_has_abnormal_for_quality(db, order_entity)
    await db.commit()
    await db.refresh(row)
    return quality_report_to_dict(row)


@router.patch("/by-allocation/{allocation_id}/attachments/{index}")
async def replace_report_attachment(
    allocation_id: int,
    index: int,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """替换该分单质检中指定下标（0 起）的一张附件。"""
    if index < 0:
        raise HTTPException(400, "index 无效")
    allocation = await db.scalar(
        select(OrderItemAllocation).where(OrderItemAllocation.id == allocation_id)
    )
    if not allocation:
        raise HTTPException(404, "分单不存在")
    product = await db.scalar(select(Product).where(Product.id == allocation.product_id))
    _assert_allocation_upload_role(user, allocation, product)
    row = await db.scalar(
        select(QualityReport)
        .where(QualityReport.allocation_id == int(allocation.id))
        .order_by(QualityReport.id.desc())
        .limit(1)
    )
    if not row:
        raise HTTPException(404, "该分单尚无质检报告，请先整批上传")
    urls = file_urls_from_row(row)
    if index >= len(urls):
        raise HTTPException(400, "下标超出已有附件数量")
    old_url = urls[index]
    new_urls = await validate_and_upload_files([file])
    new_url = new_urls[0]
    urls[index] = new_url
    delete_public_urls([old_url])
    persist_urls_to_row(urls, row)
    order_entity = await db.scalar(select(Order).where(Order.id == int(allocation.order_id)))
    if order_entity:
        await refresh_order_has_abnormal_for_quality(db, order_entity)
    await db.commit()
    await db.refresh(row)
    return quality_report_to_dict(row)


@router.get("/by-order/{order_id}")
async def list_reports_by_order(
    order_id: int,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回该订单全部质检报告。前端可按 allocation_id 优先映射，无 allocation_id 时按 (product_id+supplier_id) 兜底匹配。"""
    if not await _can_view_order_quality_reports(db, order_id, user, request):
        raise HTTPException(403, "无权限查看该订单质检报告")
    rows = (
        await db.scalars(
            select(QualityReport)
            .where(QualityReport.order_id == order_id)
            .order_by(QualityReport.id.desc())
        )
    ).all()
    return [quality_report_to_dict(r) for r in rows]


@router.get("")
async def list_reports(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """供工厂/供货商查询自己上传过的报告列表。"""
    if str(user.role) not in {"supplier", "factory"}:
        raise HTTPException(403, "仅供货商或工厂可查看")
    rows = (
        await db.scalars(
            select(QualityReport)
            .where(QualityReport.supplier_id == user.id)
            .order_by(QualityReport.id.desc())
        )
    ).all()
    return [quality_report_to_dict(r) for r in rows]
