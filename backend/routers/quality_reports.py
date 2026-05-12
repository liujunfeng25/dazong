from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, parse_client_canteen_id_from_authorization, require_role
from models import ClientCanteen, Order, OrderItemAllocation, Product, QualityReport
from services.order_quality_missing import refresh_order_has_abnormal_for_quality
from services.storage.minio_client import upload_quality_file

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


@router.post("")
async def upload_report(
    product_id: int = Form(...),
    order_id: int = Form(...),
    allocation_id: Optional[int] = Form(None),
    report_no: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(require_role("factory")),
    db: AsyncSession = Depends(get_db),
):
    """指定厂家上传质检报告（仅 factory）。"""
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
    file_url = await upload_quality_file(file)
    row = QualityReport(
        supplier_id=user.id,
        product_id=product_id,
        order_id=order_id,
        allocation_id=int(allocation.id),
        file_url=file_url,
        report_no=report_no,
        status="待审核",
        created_at=datetime.utcnow(),
    )
    db.add(row)
    order_entity = await db.scalar(select(Order).where(Order.id == order_id))
    if order_entity:
        await refresh_order_has_abnormal_for_quality(db, order_entity)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/by-allocation")
async def upload_report_by_allocation(
    allocation_id: int = Form(...),
    report_no: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """供货商或工厂按分单上传质检报告。
    - 供货商：仅允许上传归属本户的分单。
    - 工厂：仅允许上传指定厂家商品对应的分单。
    """
    if str(user.role) not in {"supplier", "factory"}:
        raise HTTPException(403, "仅供货商或指定厂家可上传分单质检报告")
    allocation = await db.scalar(
        select(OrderItemAllocation).where(OrderItemAllocation.id == allocation_id)
    )
    if not allocation:
        raise HTTPException(404, "分单不存在")
    product = await db.scalar(select(Product).where(Product.id == allocation.product_id))
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
    file_url = await upload_quality_file(file)
    # supplier_id 存「上传主体」：供货商为分单供货商；工厂为指定厂家自身（便于工厂端列表查询）
    report_supplier_id = int(user.id) if str(user.role) == "factory" else int(allocation.supplier_id)
    row = QualityReport(
        supplier_id=report_supplier_id,
        product_id=int(allocation.product_id),
        order_id=int(allocation.order_id),
        allocation_id=int(allocation.id),
        file_url=file_url,
        report_no=(report_no or "").strip() or f"QR-{int(allocation.id)}-{datetime.utcnow().strftime('%H%M%S')}",
        status="待审核",
        created_at=datetime.utcnow(),
    )
    db.add(row)
    order_entity = await db.scalar(select(Order).where(Order.id == int(allocation.order_id)))
    if order_entity:
        await refresh_order_has_abnormal_for_quality(db, order_entity)
    await db.commit()
    await db.refresh(row)
    return row


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
    return rows


@router.get("")
async def list_reports(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """供工厂/供货商查询自己上传过的报告列表。"""
    if str(user.role) not in {"supplier", "factory"}:
        raise HTTPException(403, "仅供货商或工厂可查看")
    return (
        await db.scalars(
            select(QualityReport)
            .where(QualityReport.supplier_id == user.id)
            .order_by(QualityReport.id.desc())
        )
    ).all()
