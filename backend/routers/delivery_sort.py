from datetime import date, datetime
import re
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from database import get_db
from dependencies import require_role
from models import (
    ClientCanteen,
    DeliverySortScanRecord,
    Order,
    OrderItemAllocation,
    Product,
    User,
)
from services.audit_service import write_audit_log

router = APIRouter(prefix="/delivery-sort", tags=["delivery-sort"])
BJ_TZ = ZoneInfo("Asia/Shanghai")


class DeliverySortScanIn(BaseModel):
    barcode_value: str = Field(..., min_length=1, max_length=128)
    device_code: str = Field(default="", max_length=64)


def _parse_allocation_id(raw: str) -> Optional[int]:
    value = (raw or "").strip()
    if not value:
        return None
    upper = value.upper()
    for prefix in ("DZALLOC:", "DZALLOC-", "ALLOC:", "ALLOC-"):
        if upper.startswith(prefix):
            value = value[len(prefix) :].strip()
            break
    if value.isdigit():
        aid = int(value)
        return aid if aid > 0 else None
    match = re.search(r"(?:^|[-\s])A(\d+)\s*$|A(\d+)\s*$", upper)
    if match:
        aid = int(match.group(1) or match.group(2))
        return aid if aid > 0 else None
    return None


def _delivery_date_where(target_date: date) -> Any:
    return or_(
        Order.expected_delivery_date == target_date,
        and_(Order.expected_delivery_date.is_(None), func.date(Order.created_at) == target_date),
    )


def _order_day_matches_today(order: Order) -> bool:
    today = datetime.now(BJ_TZ).date()
    if order.expected_delivery_date:
        return order.expected_delivery_date == today
    return bool(order.created_at and order.created_at.date() == today)


async def _delivery_date_rows(db: AsyncSession, delivery_id: int, target_date: date):
    SupplierUser = aliased(User)
    ClientUser = aliased(User)
    return (
        await db.execute(
            select(
                OrderItemAllocation,
                Order,
                Product,
                SupplierUser,
                ClientUser,
                ClientCanteen,
                DeliverySortScanRecord,
            )
            .join(Order, Order.id == OrderItemAllocation.order_id)
            .join(Product, Product.id == OrderItemAllocation.product_id)
            .join(SupplierUser, SupplierUser.id == OrderItemAllocation.supplier_id)
            .join(ClientUser, ClientUser.id == Order.client_id)
            .outerjoin(ClientCanteen, ClientCanteen.id == Order.canteen_id)
            .outerjoin(
                DeliverySortScanRecord,
                DeliverySortScanRecord.allocation_id == OrderItemAllocation.id,
            )
            .where(
                OrderItemAllocation.delivery_id == delivery_id,
                Order.status != "取消",
                _delivery_date_where(target_date),
            )
            .order_by(
                DeliverySortScanRecord.id.is_not(None),
                Order.expected_delivery_slot,
                Order.id,
                OrderItemAllocation.line_no,
                OrderItemAllocation.id,
            )
        )
    ).all()


def _row_payload(
    alloc: OrderItemAllocation,
    order: Order,
    product: Product,
    supplier: User,
    client: User,
    canteen: Optional[ClientCanteen],
    record: Optional[DeliverySortScanRecord],
) -> dict:
    if record:
        status = "已分检"
    elif str(alloc.status) == "已出库":
        status = "待分检"
    else:
        status = "未出库"
    return {
        "allocation_id": int(alloc.id),
        "barcode_value": f"DZALLOC:{int(alloc.id)}",
        "allocation_label": f"{order.order_no}-A{int(alloc.id)}",
        "order_id": int(order.id),
        "order_no": order.order_no,
        "client_name": client.company_name or client.username,
        "canteen_name": canteen.name if canteen else "",
        "expected_delivery_date": order.expected_delivery_date.isoformat() if order.expected_delivery_date else "",
        "expected_delivery_slot": order.expected_delivery_slot or "",
        "product_name": product.name,
        "spec": product.spec or "",
        "unit": product.unit or "kg",
        "quantity": float(alloc.quantity),
        "supplier_id": int(supplier.id),
        "supplier_name": supplier.company_name or supplier.username,
        "allocation_status": str(alloc.status),
        "sort_status": status,
        "scanned_at": record.scanned_at.isoformat() if record else None,
        "device_code": record.device_code if record else "",
    }


def _summary(items: list[dict]) -> dict:
    total = len(items)
    sorted_count = sum(1 for item in items if item["sort_status"] == "已分检")
    not_ready_count = sum(1 for item in items if item["sort_status"] in {"未出库", "异常"})
    pending_count = sum(1 for item in items if item["sort_status"] == "待分检")
    progress_percent = round((sorted_count / total) * 100) if total else 0
    return {
        "total": total,
        "sorted": sorted_count,
        "pending": pending_count,
        "not_ready": not_ready_count,
        "abnormal": not_ready_count,
        "progress_percent": progress_percent,
    }


@router.get("/today")
async def delivery_sort_today(
    delivery_date: Optional[date] = None,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    selected_date = delivery_date or datetime.now(BJ_TZ).date()
    rows = await _delivery_date_rows(db, int(user.id), selected_date)
    items = [_row_payload(*row) for row in rows]
    return {
        "delivery_id": int(user.id),
        "delivery_name": user.company_name or user.username,
        "date": selected_date.isoformat(),
        **_summary(items),
        "items": items,
    }


@router.get("/progress")
async def delivery_sort_progress(
    delivery_date: Optional[date] = None,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    rows = await _delivery_date_rows(db, int(user.id), delivery_date or datetime.now(BJ_TZ).date())
    items = [_row_payload(*row) for row in rows]
    return _summary(items)


@router.post("/scan")
async def delivery_sort_scan(
    payload: DeliverySortScanIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    raw = payload.barcode_value.strip()
    allocation_id = _parse_allocation_id(raw)
    if allocation_id is None:
        return {
            "result": "error",
            "message": "条码格式无法识别",
            "reason": "请扫描供货商标签上的分单条码",
            "suggestion": "确认条码内容为 DZALLOC:分单ID，或联系管理员重新打印标签。",
        }

    SupplierUser = aliased(User)
    ClientUser = aliased(User)
    row = await db.execute(
        select(
            OrderItemAllocation,
            Order,
            Product,
            SupplierUser,
            ClientUser,
            ClientCanteen,
            DeliverySortScanRecord,
        )
        .join(Order, Order.id == OrderItemAllocation.order_id)
        .join(Product, Product.id == OrderItemAllocation.product_id)
        .join(SupplierUser, SupplierUser.id == OrderItemAllocation.supplier_id)
        .join(ClientUser, ClientUser.id == Order.client_id)
        .outerjoin(ClientCanteen, ClientCanteen.id == Order.canteen_id)
        .outerjoin(DeliverySortScanRecord, DeliverySortScanRecord.allocation_id == OrderItemAllocation.id)
        .where(OrderItemAllocation.id == allocation_id)
    )
    found = row.first()
    if not found:
        return {
            "result": "error",
            "message": "条码不存在",
            "reason": f"未找到分单 {raw}",
            "suggestion": "确认是否扫描了大综系统生成的供货商标签。",
        }

    alloc, order, product, supplier, client, canteen, existing = found
    if int(alloc.delivery_id) != int(user.id):
        return {
            "result": "error",
            "message": "条码不属于当前配送商",
            "reason": "该分单归属的配送商与当前登录账号不一致",
            "suggestion": "请联系调度中心核实货品是否送错分检场。",
        }
    if str(order.status) == "取消":
        return {
            "result": "error",
            "message": "订单已取消",
            "reason": "取消订单不允许继续分检",
            "suggestion": "请将该货品交由现场主管处理。",
        }
    if not _order_day_matches_today(order):
        return {
            "result": "error",
            "message": "非当日分检订单",
            "reason": "该分单不在今日待分检范围内",
            "suggestion": "请确认标签日期，必要时联系调度调整。",
            "item": _row_payload(alloc, order, product, supplier, client, canteen, existing),
        }
    if str(alloc.status) != "已出库":
        return {
            "result": "error",
            "message": "供货商尚未出库",
            "reason": f"当前分单状态为 {alloc.status}",
            "suggestion": "请先让供货商完成标签打印和出库登记。",
            "item": _row_payload(alloc, order, product, supplier, client, canteen, existing),
        }
    if existing:
        return {
            "result": "duplicate",
            "message": "该分单已分检",
            "first_scanned_at": existing.scanned_at.isoformat(),
            "item": _row_payload(alloc, order, product, supplier, client, canteen, existing),
            **_summary([_row_payload(*r) for r in await _delivery_date_rows(db, int(user.id), datetime.now(BJ_TZ).date())]),
        }

    now = datetime.utcnow()
    record = DeliverySortScanRecord(
        allocation_id=int(alloc.id),
        order_id=int(order.id),
        delivery_id=int(user.id),
        operator_id=int(user.id),
        barcode_value=raw,
        device_code=(payload.device_code or "").strip(),
        scanned_at=now,
        created_at=now,
    )
    db.add(record)
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="delivery_sort_scan",
        category="order",
        object_type="allocation",
        object_id=int(alloc.id),
        detail=f"配送分检扫码 {raw}",
        after_json={
            "allocation_id": int(alloc.id),
            "order_id": int(order.id),
            "order_no": order.order_no,
            "device_code": record.device_code,
        },
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(DeliverySortScanRecord).where(DeliverySortScanRecord.allocation_id == int(alloc.id))
        )
        return {
            "result": "duplicate",
            "message": "该分单已分检",
            "first_scanned_at": existing.scanned_at.isoformat() if existing else None,
            "item": _row_payload(alloc, order, product, supplier, client, canteen, existing),
            **_summary([_row_payload(*r) for r in await _delivery_date_rows(db, int(user.id), datetime.now(BJ_TZ).date())]),
        }

    rows = await _delivery_date_rows(db, int(user.id), datetime.now(BJ_TZ).date())
    items = [_row_payload(*r) for r in rows]
    current = next((item for item in items if item["allocation_id"] == int(alloc.id)), None)
    return {
        "result": "success",
        "message": "分检完成",
        "item": current or _row_payload(alloc, order, product, supplier, client, canteen, record),
        **_summary(items),
    }
