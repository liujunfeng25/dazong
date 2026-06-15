from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from dependencies import (
    get_current_user,
    require_client_with_canteen,
    require_role,
    require_roles,
    resolve_client_canteen_id_from_request,
)
from models import (
    Alert,
    AuditLog,
    Category,
    Bill,
    BillingStatement,
    ClientCanteen,
    Delivery,
    DeliveryDispatchItem,
    DeliveryDispatchStop,
    DeliveryDispatchTrip,
    IdempotencyKey,
    IoTData,
    Order,
    OrderItemAllocation,
    OrderReceivingLine,
    OrderReturn,
    OrderReturnLine,
    OrderReview,
    OrderStatusLog,
    QualityReport,
    SortRecord,
    User,
    Product,
    Contract,
)
from schemas.orders import (
    OrderCreateIn,
    PrintAllocationLabelsIn,
    ReceiveOrderIn,
    ReceivingConfirmIn,
    ReceivingDraftIn,
    ReturnReviewIn,
    ReviewIn,
)
from services.event_bus import publish_monitor_event, publish_role_order_update
from services.audit_service import write_audit_log
from services.bill_service import create_receive_bills
from services.billing_service import (
    billing_route_for_role,
    create_receive_billing_statements,
    create_return_reversal_statements,
)
from services.order_return_service import create_returns_after_receive, upsert_returns_for_order
from services.receiving_billing import build_receiving_billing_snapshot
from services.order_receiving_differences import (
    list_receiving_shortage_returns,
    receiving_difference_summary_map,
)
from services.notification_service import push_notification
from services.delivery_slot import DELIVERY_SLOT_RE, parse_delivery_slot_hours
from services.delivery_sort_service import delivery_sort_summary_for_order
from services.delivery_workflow import compute_delivery_stage, delivery_stage_aggregates
from services.order_state_machine import ensure_order_transition
from services.order_detail_aggregator import (
    _receiving_line_payload,
    _return_line_payload,
    _return_status_label,
    build_order_detail_extensions,
    build_order_logistics_tracking,
)
from services.order_quality_missing import missing_quality_allocations
from services.periodic_quality_reports import (
    approved_periodic_report_map,
    periodic_report_payload,
    quality_cover_date_for_order,
)
from services.ticket_service import (
    close_delivery_overdue_alert_if_delivered,
    close_delivery_overdue_ticket_if_delivered,
    ensure_quality_missing_ticket,
)
from services.outbox_service import add_outbox_event
from services.order_service import (
    calc_total_amount,
    create_abnormal_records_and_ticket,
    detect_abnormal_items,
)
from services.storage.minio_client import (
    normalize_public_image_url,
    normalize_public_image_urls,
    upload_receiving_lock_photo,
    upload_receiving_return_photo,
    upload_receiving_signature,
)
from services.recognition.samples import create_receiving_candidate_background
from services.kuaimai_print import (
    KuaimaiPrintError,
    build_label_fields,
    kuaimai_error_to_http,
    print_label_fields_batches,
    resolve_printer_sn,
)

router = APIRouter(prefix="/orders", tags=["orders"])


async def _resolve_client_canteen_id(db: AsyncSession, user: User, request: Request) -> int:
    return await resolve_client_canteen_id_from_request(db, user, request)


async def _supplier_can_act_on_order(db: AsyncSession, order: Order, supplier_user_id: int) -> bool:
    """客户向配送商下单后，仅当配送商已写入分包且本供货商在分单表中有行时，方可查看/操作。"""
    return bool(
        await db.scalar(
            select(
                exists(
                    select(OrderItemAllocation.id).where(
                        OrderItemAllocation.order_id == order.id,
                        OrderItemAllocation.supplier_id == supplier_user_id,
                    )
                )
            )
        )
    )


def _statement_contains_order(statement: BillingStatement, order_id: int) -> bool:
    order_ids = (statement.source_snapshot_json or {}).get("order_ids") or []
    return int(order_id) in {int(i) for i in order_ids}


async def _signed_contract_for_order(
    db: AsyncSession, client_id: int, delivery_id: int
) -> Optional[Contract]:
    """仅「已中标」合约为可下单、计价依据。"""
    today = date.today()
    return await db.scalar(
        select(Contract)
        .where(
            Contract.client_id == client_id,
            Contract.delivery_id == delivery_id,
            Contract.status == "已中标",
            Contract.period_start <= today,
            Contract.period_end >= today,
        )
        .order_by(Contract.id.desc())
    )


def _contract_rate_map_and_fallback(contract: Contract) -> tuple[dict[int, float], float]:
    rate_map: dict[int, float] = {}
    for i in contract.category_rates_json or []:
        if i.get("category_id") is not None:
            rate_map[int(i["category_id"])] = float(i.get("float_rate", 0))
    return rate_map, float(contract.price_float_rate or 0)


def _unit_price_with_contract_rate(
    reference_price: float, category1_id: int, rate_map: dict[int, float], fallback_rate: float
) -> float:
    rate = rate_map.get(int(category1_id), fallback_rate)
    return float(
        round(Decimal(str(reference_price)) * (Decimal("1") + Decimal(str(rate))), 2)
    )


def _new_order_no() -> str:
    return "OD" + datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[-14:]


def _audit_meta(request: Request) -> dict:
    return {
        "trace_id": getattr(request.state, "trace_id", ""),
        "source_ip": request.client.host if request.client else "",
    }


def _to_float_or_none(value) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _order_line_count(order: Order) -> int:
    return len(order.items_json or [])


def _ordered_qty_kg_for_line(order: Order, line_index: int) -> tuple[float, str]:
    """行号 1-based；返回 (下单量 kg, 原始单位文案)。"""
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    if line_index < 1 or line_index > len(items):
        return 0.0, "kg"
    idx = line_index - 1
    item = items[idx] or {}
    snap = (snaps[idx] if idx < len(snaps) else {}) or {}
    qty = float(item.get("quantity") or 0)
    unit = str(snap.get("unit") or item.get("unit") or "kg")
    if "斤" in unit:
        return round(qty * 0.5, 6), unit
    return round(qty, 6), unit


def _line_snapshot(order: Order, line_index: int) -> tuple[dict, dict]:
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    if line_index < 1 or line_index > len(items):
        return {}, {}
    idx = line_index - 1
    return (items[idx] or {}), ((snaps[idx] if idx < len(snaps) else {}) or {})


def _line_standard_type(order: Order, line_index: int) -> str:
    item, snap = _line_snapshot(order, line_index)
    return str(snap.get("standard_type") or item.get("standard_type") or "non_standard")


def _ordered_quantity_for_line(order: Order, line_index: int) -> tuple[float, str]:
    item, snap = _line_snapshot(order, line_index)
    qty = float(item.get("quantity") or snap.get("order_quantity") or 0)
    unit = str(snap.get("unit") or item.get("unit") or "")
    return round(qty, 6), unit


async def _receiving_confirmed_counts(db: AsyncSession, order_ids: list[int]) -> dict[int, int]:
    if not order_ids:
        return {}
    rows = (
        await db.execute(
            select(OrderReceivingLine.order_id, func.count(OrderReceivingLine.id))
            .where(
                OrderReceivingLine.order_id.in_(order_ids),
                OrderReceivingLine.status == "confirmed",
            )
            .group_by(OrderReceivingLine.order_id)
        )
    ).all()
    return {int(r[0]): int(r[1]) for r in rows}


async def _ensure_receiving_lines(db: AsyncSession, order: Order) -> None:
    n = _order_line_count(order)
    if n <= 0:
        return
    existing_idx = set(
        (
            await db.scalars(
                select(OrderReceivingLine.line_index).where(OrderReceivingLine.order_id == order.id)
            )
        ).all()
    )
    for idx in range(1, n + 1):
        if idx not in existing_idx:
            db.add(OrderReceivingLine(order_id=order.id, line_index=idx, status="pending"))
    await db.flush()


async def _has_receiving_lines(db: AsyncSession, order_id: int) -> bool:
    rid = await db.scalar(select(OrderReceivingLine.id).where(OrderReceivingLine.order_id == order_id).limit(1))
    return rid is not None


async def _all_receiving_lines_confirmed(db: AsyncSession, order: Order) -> bool:
    n = _order_line_count(order)
    if n <= 0:
        return True
    rows = (
        await db.scalars(select(OrderReceivingLine).where(OrderReceivingLine.order_id == order.id))
    ).all()
    if len(rows) < n:
        return False
    by_index = {int(r.line_index): r for r in rows}
    for i in range(1, n + 1):
        row = by_index.get(i)
        if not row or str(row.status) != "confirmed":
            return False
        if _line_standard_type(order, i) == "standard":
            if row.confirmed_quantity is None:
                return False
        elif row.confirmed_kg is None:
            return False
    return True


async def _apply_receiving_line_payload(
    db: AsyncSession,
    order: Order,
    line_index: int,
    body: ReceivingConfirmIn,
    user_id: int,
) -> None:
    n = _order_line_count(order)
    if line_index < 1 or line_index > n:
        raise HTTPException(400, f"行号无效：{line_index}")
    row = await db.scalar(
        select(OrderReceivingLine).where(
            OrderReceivingLine.order_id == order.id,
            OrderReceivingLine.line_index == line_index,
        )
    )
    if not row:
        raise HTTPException(500, f"称重行初始化失败：{line_index}")

    is_standard = _line_standard_type(order, line_index) == "standard"
    ordered_qty, ordered_unit = _ordered_quantity_for_line(order, line_index)
    ordered_kg, _u = _ordered_qty_kg_for_line(order, line_index)
    lock_photo_url = normalize_public_image_url((body.lock_photo_url or "").strip()) or None
    eps = 1e-3
    if is_standard:
        if body.received_quantity is None:
            raise HTTPException(400, f"行{line_index}标品请填写实收数量")
        if not lock_photo_url:
            raise HTTPException(400, f"行{line_index}标品需拍照留痕后再确认")
        received_qty = float(body.received_quantity)
        received = float(body.sample_kg or 0)
        is_shortage = ordered_qty > 0 and received_qty + eps < ordered_qty
    else:
        if body.net_kg is None:
            raise HTTPException(400, f"行{line_index}非标品请先称重")
        if not lock_photo_url:
            raise HTTPException(400, f"行{line_index}非标品需锁定读数并拍照后再确认")
        received = float(body.net_kg)
        received_qty = None
        is_shortage = ordered_kg > 0 and received + eps < ordered_kg
    if is_shortage:
        if not body.shortage_reason:
            raise HTTPException(
                400,
                f"行{line_index}实收少于下单量时，请选择少收原因",
            )
        photos = normalize_public_image_urls(
            [u.strip() for u in (body.shortage_reason.photo_urls or []) if u and u.strip()][:8]
        )
        if body.shortage_reason.code == "quality" and not photos:
            raise HTTPException(400, f"行{line_index}质量问题退货必须上传至少1张证据照片")
        row.shortage_reason_code = str(body.shortage_reason.code)
        row.shortage_reason_detail = (body.shortage_reason.detail or "").strip() or None
        row.return_photo_urls_json = photos
        row.return_note = (body.shortage_reason.detail or "").strip() or None
        row.shortage_ordered_kg = ordered_qty if is_standard else ordered_kg
        row.shortage_delta_kg = round((ordered_qty - received_qty) if is_standard and received_qty is not None else (ordered_kg - received), 4)
    else:
        row.shortage_reason_code = None
        row.shortage_reason_detail = None
        row.return_photo_urls_json = None
        row.return_note = None
        row.shortage_ordered_kg = None
        row.shortage_delta_kg = None

    row.confirmed_kg = None if is_standard else received
    row.draft_kg = float(body.sample_kg) if is_standard and body.sample_kg is not None else (None if is_standard else received)
    row.confirmed_quantity = received_qty if is_standard else None
    row.confirmed_unit = (body.received_unit or ordered_unit or "").strip()[:20] if is_standard else None
    row.sample_kg = float(body.sample_kg) if body.sample_kg is not None else None
    row.lock_photo_url = lock_photo_url
    row.lock_photo_taken_at = body.lock_photo_taken_at or (datetime.utcnow() if body.lock_photo_url else None)
    row.lock_photo_device_id = (body.lock_photo_device_id or "").strip() or None
    row.status = "confirmed"
    row.confirmed_at = datetime.utcnow()
    row.confirmed_by_user_id = user_id
    row.updated_at = datetime.utcnow()


def _category_image_for_client(value: str | None) -> str | None:
    """分类图片下发客户端：URL 走 MinIO 规范化；emoji: token / 空值原样透传。"""
    if not value:
        return value
    if value.startswith("http") or value.startswith("/"):
        return normalize_public_image_url(value) or value
    return value


def _serialize_order_for_list(order: Order, confirmed_count: int) -> dict:
    d = jsonable_encoder(order)
    total = _order_line_count(order)
    d["receiving_total_lines"] = total
    d["receiving_confirmed_count"] = min(confirmed_count, total) if total else 0
    return d


def _normalize_signature_payload(sig: dict | None) -> dict | None:
    if not isinstance(sig, dict):
        return sig
    out = dict(sig)
    for key in (
        "warehouse_signature",
        "carrier_signature",
        "warehouse_signature_url",
        "carrier_signature_url",
    ):
        out[key] = normalize_public_image_url(out.get(key)) or out.get(key)
    return out


def _supplier_view_status(order_status: str, my_alloc_total: int, my_alloc_shipped: int) -> tuple[str, str]:
    if str(order_status) == "取消":
        return "cancelled", "已取消"
    if my_alloc_total > 0:
        if my_alloc_shipped >= my_alloc_total:
            if str(order_status) in {"收货", "收货确认", "已结算"}:
                return "completed", "已完成"
            return "shipped", "已发货"
        return "pending_ship", "待发货"
    if str(order_status) in {"下单", "配货"}:
        return "pending_ship", "待发货"
    if str(order_status) == "发货":
        return "shipped", "已发货"
    if str(order_status) in {"收货", "收货确认", "已结算"}:
        return "completed", "已完成"
    return "pending_ship", "待发货"


async def _emit_order_status_change(db: AsyncSession, order: Order, old_status: str, new_status: str):
    if old_status == new_status:
        return
    await publish_monitor_event(
        "order_status_change",
        {
            "order_id": order.id,
            "order_no": order.order_no,
            "old_status": old_status,
            "new_status": new_status,
        },
    )
    supplier_targets = await _supplier_user_ids_for_order(db, order)
    cid = int(order.canteen_id) if order.canteen_id is not None else None
    if supplier_targets:
        await publish_role_order_update(
            "supplier",
            supplier_targets,
            order.id,
            order.order_no,
            new_status,
            f"订单状态变更为{new_status}",
            canteen_id=cid,
        )
    await publish_role_order_update(
        "delivery",
        [order.delivery_id],
        order.id,
        order.order_no,
        new_status,
        f"订单状态变更为{new_status}",
        canteen_id=cid,
    )


async def _notify_order_roles(db: AsyncSession, order: Order, title: str, content: str):
    await push_notification(
        db=db,
        role="delivery",
        event_type="order_status_change",
        title=title,
        content=content,
        route=f"/delivery/orders/{order.id}",
        object_type="order",
        object_id=order.id,
        target_user_ids=[order.delivery_id],
    )


async def _supplier_user_ids_for_order(db: AsyncSession, order: Order) -> list[int]:
    """仅通知分单表中出现过的供货商（配送商下游分包方，与供货商端可见范围一致）。"""
    alloc_supplier_ids = (
        await db.scalars(
            select(OrderItemAllocation.supplier_id)
            .where(OrderItemAllocation.order_id == order.id)
            .distinct()
        )
    ).all()
    return [int(i) for i in alloc_supplier_ids]


async def _notify_order_targets(
    db: AsyncSession,
    order: Order,
    title: str,
    content: str,
    *,
    to_client: bool = False,
    to_delivery: bool = False,
    to_suppliers: bool = False,
    event_type: str = "order_status_change",
    client_route: str = "",
    delivery_route: str = "",
    supplier_route: str = "",
    factory_route: str = "",
):
    if to_client:
        await push_notification(
            db=db,
            role="client",
            event_type=event_type,
            title=title,
            content=content,
            route=client_route or f"/client/orders/{order.id}",
            object_type="order",
            object_id=order.id,
            target_user_ids=[order.client_id],
            canteen_id=int(order.canteen_id) if order.canteen_id is not None else None,
        )
    if to_delivery:
        await push_notification(
            db=db,
            role="delivery",
            event_type=event_type,
            title=title,
            content=content,
            route=delivery_route or f"/delivery/orders/{order.id}",
            object_type="order",
            object_id=order.id,
            target_user_ids=[order.delivery_id],
        )
    if to_suppliers:
        supplier_ids = await _supplier_user_ids_for_order(db, order)
        if supplier_ids:
            users = (await db.scalars(select(User).where(User.id.in_(supplier_ids)))).all()
            role_groups: dict[str, list[int]] = {}
            for target in users:
                role_groups.setdefault(str(target.role or "supplier"), []).append(int(target.id))
            for role, target_ids in role_groups.items():
                route = factory_route if role == "factory" and factory_route else supplier_route
                await push_notification(
                    db=db,
                    role=role,
                    event_type=event_type,
                    title=title,
                    content=content,
                    route=route or f"/{role}/orders/{order.id}",
                    object_type="order",
                    object_id=order.id,
                    target_user_ids=target_ids,
                )


async def _allocation_shipping_summary(
    db: AsyncSession, order_id: int, supplier_id: Optional[int] = None
) -> dict:
    """分单发货汇总：用于限制配送取货时机，以及供货商侧按钮禁用。"""
    where = [OrderItemAllocation.order_id == order_id]
    if supplier_id is not None:
        where.append(OrderItemAllocation.supplier_id == supplier_id)
    rows = (
        await db.execute(
            select(OrderItemAllocation.id, OrderItemAllocation.status).where(*where)
        )
    ).all()
    total = len(rows)
    shipped = sum(1 for _, status in rows if str(status) == "已出库")
    return {
        "total": total,
        "shipped": shipped,
        "all_shipped": (total > 0 and shipped == total),
    }


async def _supplier_sort_record(
    db: AsyncSession, order_id: int, supplier_user_id: int
) -> Optional[SortRecord]:
    return await db.scalar(
        select(SortRecord)
        .where(
            SortRecord.order_id == order_id,
            SortRecord.operator_id == supplier_user_id,
        )
        .order_by(SortRecord.sorted_at.desc(), SortRecord.id.desc())
    )


async def _supplier_label_gate_state(
    db: AsyncSession, order_id: int, supplier_user_id: int
) -> dict:
    rows = (
        await db.execute(
            select(OrderItemAllocation.id, OrderItemAllocation.label_print_count).where(
                OrderItemAllocation.order_id == order_id,
                OrderItemAllocation.supplier_id == supplier_user_id,
            )
        )
    ).all()
    my_alloc_ids_int = [int(r[0]) for r in rows]
    counts = {int(r[0]): int(r[1] or 0) for r in rows}
    line_total = len(my_alloc_ids_int)
    printed_line_ids = {aid for aid, cnt in counts.items() if cnt >= 1}
    line_printed_count = len(printed_line_ids)
    all_line_printed = bool(line_total > 0 and line_printed_count == line_total)
    can_ship_by_print = all_line_printed if line_total > 0 else False
    order_record = await _supplier_sort_record(db, order_id, supplier_user_id)
    order_label_printed = bool(order_record and order_record.label_printed)
    total_print_count = sum(counts.values())
    return {
        "order_label_printed": order_label_printed,
        "line_label_total": int(line_total),
        "line_label_printed_count": int(line_printed_count),
        "all_line_labels_printed": all_line_printed,
        "can_ship_by_print": can_ship_by_print,
        "printed_line_ids": sorted(printed_line_ids),
        "total_label_print_count": int(total_print_count),
        "label_print_counts": counts,
    }


async def _resolve_canteen_name(db: AsyncSession, order: Order) -> str:
    if order.canteen_id:
        canteen = await db.scalar(select(ClientCanteen).where(ClientCanteen.id == order.canteen_id))
        if canteen and canteen.name:
            return str(canteen.name)
    client = await db.scalar(select(User).where(User.id == order.client_id))
    return (client.company_name or client.username if client else "") or ""


async def _execute_cloud_label_print(
    db: AsyncSession,
    *,
    order: Order,
    user: User,
    allocation_ids: list[int],
    audit_action: str,
    audit_detail: str,
    mark_order_label: bool = False,
) -> dict:
    sn = resolve_printer_sn(user)
    if not sn:
        raise HTTPException(400, "未配置云打印机，请联系管理员")

    stmt = select(OrderItemAllocation).where(
        OrderItemAllocation.order_id == order.id,
        OrderItemAllocation.supplier_id == user.id,
    )
    if allocation_ids:
        stmt = stmt.where(OrderItemAllocation.id.in_(allocation_ids))
    allocs = (await db.scalars(stmt.order_by(OrderItemAllocation.line_no.asc()))).all()
    if not allocs:
        raise HTTPException(404, "没有可打印的分单明细")
    if allocation_ids and len(allocs) != len(set(allocation_ids)):
        raise HTTPException(404, "部分分单不存在或未分包给当前账号")

    product_ids = {int(a.product_id) for a in allocs}
    products = (
        await db.scalars(select(Product).where(Product.id.in_(list(product_ids))))
    ).all()
    product_map = {int(p.id): p for p in products}
    canteen_name = await _resolve_canteen_name(db, order)

    field_rows: list[dict[str, str]] = []
    for alloc in allocs:
        product = product_map.get(int(alloc.product_id))
        if not product:
            raise HTTPException(400, f"商品 #{alloc.product_id} 不存在，无法打印")
        field_rows.append(
            build_label_fields(
                order=order,
                alloc=alloc,
                product=product,
                canteen_name=canteen_name,
                supplier_user=user,
            )
        )

    try:
        job_ids = await print_label_fields_batches(sn, field_rows)
    except KuaimaiPrintError as exc:
        raise kuaimai_error_to_http(exc) from exc

    printed_ids = [int(a.id) for a in allocs]
    for alloc in allocs:
        alloc.label_print_count = int(alloc.label_print_count or 0) + 1
        alloc.updated_at = datetime.utcnow()

    if mark_order_label:
        record = await _supplier_sort_record(db, order.id, user.id)
        if not record:
            record = SortRecord(
                order_id=order.id,
                operator_id=user.id,
                sorted_at=datetime.utcnow(),
                label_printed=True,
            )
            db.add(record)
        else:
            record.label_printed = True
            record.sorted_at = datetime.utcnow()

    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action=audit_action,
        category="order",
        object_type="order",
        object_id=order.id,
        detail=audit_detail,
        after_json={
            "allocation_ids": printed_ids,
            "job_ids": job_ids,
            "printer_sn": sn,
            "print_count_delta": 1,
        },
    )
    await db.flush()

    gate = await _supplier_label_gate_state(db, order.id, user.id)
    return {
        "message": f"已成功提交 {len(printed_ids)} 张标签打印",
        "printed_count": len(printed_ids),
        "job_ids": job_ids,
        "kuaimai_bind_table": settings.kuaimai_bind_table,
        "first_label_fields": field_rows[0] if field_rows else None,
        "label_print_counts": {str(k): v for k, v in gate["label_print_counts"].items()},
        "my_can_ship_by_print": gate["can_ship_by_print"],
        "sort_done": bool(gate["can_ship_by_print"]),
    }


async def _log_order_transition(
    db: AsyncSession,
    order: Order,
    old_status: str,
    new_status: str,
    actor_user_id: int,
    request: Optional[Request] = None,
):
    db.add(
        OrderStatusLog(
            order_id=order.id,
            old_status=old_status,
            new_status=new_status,
            actor_user_id=actor_user_id,
        )
    )
    await write_audit_log(
        db=db,
        actor_user_id=actor_user_id,
        action="order_status_change",
        category="order",
        object_type="order",
        object_id=order.id,
        detail=f"{old_status}->{new_status}",
        **(_audit_meta(request) if request else {}),
    )
    await add_outbox_event(
        db=db,
        event_type="order_status_change",
        payload={
            "order_id": order.id,
            "order_no": order.order_no,
            "old_status": old_status,
            "new_status": new_status,
        },
        channel="monitor",
    )


_POST_SHIP_STATUSES = {"发货", "收货", "收货确认", "已结算"}


async def _sync_abnormal_for_shipped_missing_quality(
    db: AsyncSession,
    order: Order,
    actor_user_id: int,
    *,
    trigger: str,
    request: Optional[Request] = None,
    new_status: Optional[str] = None,
) -> None:
    """已出库（供货商已发出）的分单若缺质检 → 整单标异常；否则清除异常位。"""
    missing = await missing_quality_allocations(db, int(order.id), shipped_only=True)
    if missing:
        order.has_abnormal = True
        payload = {
            "order_id": int(order.id),
            "order_no": order.order_no,
            "trigger": trigger,
            "new_status": new_status,
            "missing_count": len(missing),
            "missing_allocation_ids": [int(a.id) for a in missing[:50]],
        }
        await write_audit_log(
            db=db,
            actor_user_id=actor_user_id,
            action="quality_missing_marked",
            category="quality",
            object_type="order",
            object_id=int(order.id),
            detail=(
                f"订单 {order.order_no}：{trigger}，仍有 {len(missing)} 条已出库分单缺失质检报告"
                + (f"（订单状态 {new_status}）" if new_status else "")
            ),
            after_json=payload,
            **(_audit_meta(request) if request else {}),
        )
        db.add(
            Alert(
                level="medium",
                type="quality_missing",
                description=(
                    f"订单 {order.order_no}：已出库分单缺质检（{len(missing)} 条），触发：{trigger}"
                ),
                status="open",
                payload_json=payload,
            )
        )
        await ensure_quality_missing_ticket(
            db, order, actor_user_id, missing_count=len(missing)
        )


async def _mark_abnormal_if_quality_missing(
    db: AsyncSession,
    order: Order,
    actor_user_id: int,
    *,
    new_status: str,
    request: Optional[Request] = None,
) -> None:
    """订单状态推进至发货及以后时，检查已出库分单是否缺质检（与供货商发货口径一致）。"""
    if str(new_status) not in _POST_SHIP_STATUSES:
        return
    await _sync_abnormal_for_shipped_missing_quality(
        db,
        order,
        actor_user_id,
        trigger="order_status",
        request=request,
        new_status=new_status,
    )


@router.post("")
async def create_order(
    payload: OrderCreateIn,
    request: Request,
    user_and_canteen=Depends(require_client_with_canteen),
    db: AsyncSession = Depends(get_db),
):
    user, canteen = user_and_canteen
    if payload.service_duration_min is None or int(payload.service_duration_min) <= 0:
        raise HTTPException(400, "预计服务耗时需大于0分钟")
    if int(payload.service_duration_min) > 240:
        raise HTTPException(400, "预计服务耗时不能超过240分钟")
    if payload.expected_delivery_date is None:
        raise HTTPException(400, "请选择配送日期")
    if not (payload.expected_delivery_slot or "").strip():
        raise HTTPException(400, "请选择配送时段")
    slot_s = str(payload.expected_delivery_slot).strip()
    if not DELIVERY_SLOT_RE.match(slot_s):
        raise HTTPException(400, "配送时段格式非法，须为整点区间，如 06:00-07:00 或 14:00-18:00")
    slot_hours = parse_delivery_slot_hours(slot_s)
    if slot_hours is None:
        raise HTTPException(400, "配送时段解析失败")
    start_hour, end_hour = slot_hours
    if end_hour <= start_hour:
        raise HTTPException(400, "配送时段结束时刻必须晚于开始时刻")
    # 配送日期不得早于今天
    today = datetime.now().date()
    if payload.expected_delivery_date < today:
        raise HTTPException(400, "配送日期不能早于今天")
    # 开始时刻须距当前时间至少 2 小时（避免来不及配送）
    window_start = datetime.combine(payload.expected_delivery_date, time(start_hour % 24))
    if window_start < datetime.now() + timedelta(hours=2):
        raise HTTPException(400, "配送时段须距当前时间至少 2 小时，请重新选择")
    delivery_address = (canteen.address or payload.delivery_address or "").strip()
    if not delivery_address:
        raise HTTPException(400, "请填写配送地址")
    delivery_lng = float(canteen.lng) if canteen.lng is not None else None
    delivery_lat = float(canteen.lat) if canteen.lat is not None else None
    if (delivery_lng is None) or (delivery_lat is None):
        raise HTTPException(400, "当前食堂未配置坐标，请联系运营维护后再下单")
    if delivery_lng is not None and not (-180 <= delivery_lng <= 180):
        raise HTTPException(400, "经度超出范围")
    if delivery_lat is not None and not (-90 <= delivery_lat <= 90):
        raise HTTPException(400, "纬度超出范围")

    # 供货商由配送商分单写入 order_item_allocations；客户端下单不绑 supplier_id
    items = [i.model_dump() for i in payload.items]
    active_contract = await _signed_contract_for_order(db, user.id, int(payload.delivery_id))
    if not active_contract:
        raise HTTPException(400, "所选配送单位没有已生效的合约，请先在「我的合约」完成签订")
    if (
        payload.expected_delivery_date < active_contract.period_start
        or payload.expected_delivery_date > active_contract.period_end
    ):
        raise HTTPException(
            400,
            f"配送日期不在合约有效期内（{active_contract.period_start} ~ {active_contract.period_end}）",
        )
    contract_rate_map, fallback_rate = _contract_rate_map_and_fallback(active_contract)
    item_snapshots = []
    total_volume_m3 = 0.0
    total_weight_kg = 0.0
    has_volume_data = False
    has_weight_data = False
    for item in items:
        product = await db.scalar(
            select(Product).where(Product.id == item["product_id"], Product.is_deleted.is_(False))
        )
        if not product:
            raise HTTPException(400, "存在无效商品，无法下单")
        category1 = await db.scalar(select(Category).where(Category.id == product.category1_id))
        category2 = await db.scalar(select(Category).where(Category.id == product.category2_id))
        rate = contract_rate_map.get(int(product.category1_id), fallback_rate)
        item["unit_price"] = _unit_price_with_contract_rate(
            float(product.reference_price), int(product.category1_id), contract_rate_map, fallback_rate
        )
        item_snapshots.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "unit": product.unit,
                "reference_price": float(product.reference_price),
                "category1_id": product.category1_id,
                "category1_name": category1.name if category1 else "",
                "category2_id": product.category2_id,
                "category2_name": category2.name if category2 else "",
                "order_quantity": item["quantity"],
                "order_unit_price": item["unit_price"],
                "category_float_rate": rate,
                "standard_type": product.standard_type,
                "length_cm": _to_float_or_none(product.length_cm),
                "width_cm": _to_float_or_none(product.width_cm),
                "height_cm": _to_float_or_none(product.height_cm),
                "unit_weight_kg": _to_float_or_none(product.unit_weight_kg),
                "volume_adjust_factor": _to_float_or_none(product.volume_adjust_factor),
            }
        )
        if product.length_cm and product.width_cm and product.height_cm:
            adjust_factor = (
                float(product.volume_adjust_factor)
                if product.volume_adjust_factor and float(product.volume_adjust_factor) > 0
                else 1.0
            )
            line_volume = (
                float(product.length_cm) * float(product.width_cm) * float(product.height_cm) / 1000000
            ) * int(item["quantity"]) * adjust_factor
            total_volume_m3 += line_volume
            has_volume_data = True
        if product.unit_weight_kg:
            line_weight = float(product.unit_weight_kg) * int(item["quantity"])
            total_weight_kg += line_weight
            has_weight_data = True
    abnormal_items = await detect_abnormal_items(db, user.id, payload.delivery_id, items)
    if abnormal_items and not payload.force:
        return {"abnormal_items": abnormal_items, "need_confirm": True}

    order = Order(
        order_no=_new_order_no(),
        client_id=user.id,
        canteen_id=int(canteen.id),
        delivery_id=payload.delivery_id,
        supplier_id=None,
        items_json=items,
        items_snapshot_json=item_snapshots,
        total_amount=calc_total_amount(items),
        total_volume_m3=round(total_volume_m3, 4) if has_volume_data else None,
        total_weight_kg=round(total_weight_kg, 3) if has_weight_data else None,
        delivery_address=delivery_address,
        delivery_lng=delivery_lng,
        delivery_lat=delivery_lat,
        expected_delivery_date=payload.expected_delivery_date,
        expected_delivery_slot=payload.expected_delivery_slot.strip(),
        service_duration_min=int(payload.service_duration_min),
        status="下单",
        has_abnormal=bool(abnormal_items),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    await db.flush()
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_create",
        category="order",
        object_type="order",
        object_id=order.id,
        detail=f"创建订单 {order.order_no}",
        after_json={
            "order_no": order.order_no,
            "total_amount": float(order.total_amount),
            "delivery_address": order.delivery_address,
            "delivery_lng": float(order.delivery_lng) if order.delivery_lng is not None else None,
            "delivery_lat": float(order.delivery_lat) if order.delivery_lat is not None else None,
            "expected_delivery_date": str(payload.expected_delivery_date),
            "expected_delivery_slot": payload.expected_delivery_slot,
            "service_duration_min": int(payload.service_duration_min),
        },
        **_audit_meta(request),
    )
    if abnormal_items:
        await create_abnormal_records_and_ticket(db, order, abnormal_items, user.id)
    await db.commit()
    await db.refresh(order)
    await _emit_order_status_change(db, order, "N/A", order.status)
    await _notify_order_roles(
        db,
        order,
        title=f"新订单 {order.order_no}",
        content="客户端已下单，请关注后续履约状态。",
    )
    await db.commit()
    return order


@router.get("/meta")
async def order_meta(
    delivery_id: Optional[int] = None,
    user=Depends(get_current_user),
    _=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    did_rows = (
        await db.execute(
            select(Contract.delivery_id)
            .where(
                Contract.client_id == user.id,
                Contract.status == "已中标",
                Contract.period_start <= today,
                Contract.period_end >= today,
            )
            .distinct()
        )
    ).all()
    delivery_ids = [r[0] for r in did_rows]
    if not delivery_ids:
        return {"deliveries": []}
    delivery_stmt = (
        select(User)
        .where(User.role == "delivery", User.status == "active", User.id.in_(delivery_ids))
        .order_by(User.id.asc())
    )
    deliveries = (await db.scalars(delivery_stmt)).all()
    out: dict = {
        "deliveries": [
            {"id": row.id, "name": row.company_name or row.username, "username": row.username}
            for row in deliveries
        ],
    }
    if delivery_id:
        c = await _signed_contract_for_order(db, user.id, int(delivery_id))
        if c:
            rm, fb = _contract_rate_map_and_fallback(c)
            out["contract_rates"] = {
                "by_category": {str(k): v for k, v in rm.items()},
                "fallback": fb,
                "period_start": str(c.period_start),
                "period_end": str(c.period_end),
            }
            allowed_cat_ids: list[int] = []
            for x in c.category_ids_json or []:
                try:
                    cid = int(x)
                    if cid > 0:
                        allowed_cat_ids.append(cid)
                except (TypeError, ValueError):
                    continue
            if allowed_cat_ids:
                cat_rows = (
                    await db.scalars(select(Category).where(Category.id.in_(allowed_cat_ids)))
                ).all()
                name_map = {int(row.id): row.name for row in cat_rows}
                img_map = {int(row.id): row.image_url for row in cat_rows}
                # 二级子分类（用于客户端二级筛选 chip）
                child_rows = (
                    await db.scalars(
                        select(Category)
                        .where(
                            Category.level == 2,
                            Category.parent_id.in_(allowed_cat_ids),
                            Category.is_deleted.is_(False),
                        )
                        .order_by(Category.sort_order, Category.id)
                    )
                ).all()
                children_map: dict[int, list[dict]] = {}
                for row in child_rows:
                    children_map.setdefault(int(row.parent_id), []).append(
                        {
                            "id": int(row.id),
                            "name": row.name,
                            "image_url": _category_image_for_client(row.image_url),
                        }
                    )
                out["contract_categories"] = [
                    {
                        "id": cid,
                        "name": name_map.get(cid, f"分类#{cid}"),
                        "image_url": _category_image_for_client(img_map.get(cid)),
                        "children": children_map.get(cid, []),
                    }
                    for cid in allowed_cat_ids
                ]
            else:
                out["contract_categories"] = []
    return out


def _product_standard_type_str(row: Product) -> str:
    """与运营端 products.standard_type 一致：standard | non_standard"""
    raw = getattr(row, "standard_type", None)
    if hasattr(raw, "value"):
        raw = raw.value
    s = str(raw or "").strip()
    return "non_standard" if s == "non_standard" else "standard"


def _product_thumb_url(row: Product) -> Optional[str]:
    if row.logo:
        return row.logo
    imgs = row.image_list_json or []
    if isinstance(imgs, list) and len(imgs) > 0 and isinstance(imgs[0], str):
        return imgs[0]
    return None


async def _serialize_order_products(
    db: AsyncSession, rows: list[Product], user_id: int, delivery_id: Optional[int] = None
) -> list[dict]:
    signed = None
    rate_map: dict[int, float] = {}
    fallback_rate = 0.0
    if delivery_id:
        signed = await _signed_contract_for_order(db, user_id, int(delivery_id))
        if signed:
            rate_map, fallback_rate = _contract_rate_map_and_fallback(signed)

    lvl1_ids = {int(r.category1_id) for r in rows if r.category1_id is not None}
    max_float_by_cat: dict[int, float] = {}
    if lvl1_ids:
        cap_rows = (await db.scalars(select(Category).where(Category.id.in_(lvl1_ids)))).all()
        max_float_by_cat = {
            int(c.id): float(c.max_float_rate) if c.max_float_rate is not None else 1.0
            for c in cap_rows
        }

    items = []
    for row in rows:
        ref = float(row.reference_price)
        cid1 = int(row.category1_id) if row.category1_id is not None else None
        cap = max_float_by_cat.get(cid1, 1.0) if cid1 is not None else 1.0
        ceiling = float(
            round(Decimal(str(ref)) * (Decimal("1") + Decimal(str(cap))), 2)
        )
        entry = {
            "id": row.id,
            "name": row.name,
            "unit": row.unit,
            "spec": row.spec or "",
            "reference_price": ref,
            "category1_id": row.category1_id,
            "category2_id": row.category2_id,
            "logo": row.logo,
            "thumb_url": _product_thumb_url(row),
            "guide_price": ref,
            "guide_ceiling_price": ceiling,
            "category_max_float_rate": cap,
            "standard_type": _product_standard_type_str(row),
        }
        if delivery_id and signed:
            entry["contract_unit_price"] = _unit_price_with_contract_rate(
                ref, int(row.category1_id), rate_map, fallback_rate
            )
        items.append(entry)
    return items


@router.get("/products/search")
async def search_order_products(
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 24,
    delivery_id: Optional[int] = None,
    category1_id: Optional[int] = Query(None, ge=1),
    category2_id: Optional[int] = Query(None, ge=1),
    contract_categories_only: bool = Query(
        False,
        description="为 true 时仅返回当前客户对该配送商已生效合约中的一级分类下的商品；须同时传 delivery_id 与 expected_delivery_date",
    ),
    expected_delivery_date: Optional[date] = Query(
        None,
        description="期望配送日；contract_categories_only 为 true 时必填，且须落在合约有效期内",
    ),
    user=Depends(get_current_user),
    _=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    base_where = [Product.is_deleted.is_(False), Product.status == "active"]
    if keyword and keyword.strip():
        base_where.append(Product.name.like(f"%{keyword.strip()}%"))
    if category1_id is not None:
        base_where.append(Product.category1_id == int(category1_id))
    if category2_id is not None:
        base_where.append(Product.category2_id == int(category2_id))

    if contract_categories_only:
        if not delivery_id or int(delivery_id) <= 0:
            raise HTTPException(400, "按合约筛选商品时必须传有效的 delivery_id")
        if expected_delivery_date is None:
            raise HTTPException(400, "按合约筛选商品时必须传 expected_delivery_date")
        active_contract = await _signed_contract_for_order(db, user.id, int(delivery_id))
        if not active_contract:
            raise HTTPException(400, "所选配送单位没有已生效合约，无法按合约筛选商品")
        if (
            expected_delivery_date < active_contract.period_start
            or expected_delivery_date > active_contract.period_end
        ):
            raise HTTPException(
                400,
                f"配送日期不在合约有效期内（{active_contract.period_start} ~ {active_contract.period_end}）",
            )
        allowed_cat: list[int] = []
        for x in active_contract.category_ids_json or []:
            try:
                cid = int(x)
                if cid > 0:
                    allowed_cat.append(cid)
            except (TypeError, ValueError):
                continue
        if not allowed_cat:
            raise HTTPException(400, "当前合约未配置可采购分类，无法筛选商品")
        base_where.append(Product.category1_id.in_(allowed_cat))

    safe_page = max(int(page or 1), 1)
    safe_size = min(max(int(page_size or 24), 1), 100)
    offset = (safe_page - 1) * safe_size

    count_stmt = select(func.count(Product.id)).where(*base_where)
    total = int(await db.scalar(count_stmt) or 0)

    stmt = (
        select(Product)
        .where(*base_where)
        .order_by(Product.id.desc())
        .offset(offset)
        .limit(safe_size)
    )
    rows = (await db.scalars(stmt)).all()
    items = await _serialize_order_products(db, rows, user.id, delivery_id)
    return {"items": items, "total": total, "page": safe_page, "page_size": safe_size}


@router.get("/products/by-ids")
async def order_products_by_ids(
    ids: str = Query(..., description="逗号分隔商品ID列表"),
    delivery_id: Optional[int] = None,
    user=Depends(get_current_user),
    _=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    product_ids: list[int] = []
    for part in (ids or "").split(","):
        txt = (part or "").strip()
        if not txt:
            continue
        try:
            pid = int(txt)
        except ValueError:
            continue
        if pid > 0:
            product_ids.append(pid)
    if not product_ids:
        return {"items": []}
    product_ids = list(dict.fromkeys(product_ids))
    rows = (
        await db.scalars(
            select(Product).where(
                Product.id.in_(product_ids),
                Product.is_deleted.is_(False),
                Product.status == "active",
            )
        )
    ).all()
    by_id = {int(r.id): r for r in rows}
    ordered_rows = [by_id[pid] for pid in product_ids if pid in by_id]
    items = await _serialize_order_products(db, ordered_rows, user.id, delivery_id)
    return {"items": items}


@router.get("")
async def list_orders(
    request: Request,
    status: Optional[str] = None,
    order_no: Optional[str] = None,
    created_date_start: Optional[str] = None,
    created_date_end: Optional[str] = None,
    expected_delivery_date_start: Optional[str] = None,
    expected_delivery_date_end: Optional[str] = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.utcnow().date()
    use_delivery_filter = bool(expected_delivery_date_start or expected_delivery_date_end)
    try:
        if use_delivery_filter:
            ed_start = date.fromisoformat(expected_delivery_date_start) if expected_delivery_date_start else today
            ed_end = date.fromisoformat(expected_delivery_date_end) if expected_delivery_date_end else ed_start
        else:
            start_date = date.fromisoformat(created_date_start) if created_date_start else today
            end_date = date.fromisoformat(created_date_end) if created_date_end else today
    except ValueError:
        raise HTTPException(400, "时间筛选格式错误，需为 YYYY-MM-DD")
    if use_delivery_filter:
        if ed_end < ed_start:
            raise HTTPException(400, "结束日期不能早于开始日期")
    else:
        if end_date < start_date:
            raise HTTPException(400, "结束日期不能早于开始日期")
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date + timedelta(days=1), time.min)

    stmt = select(Order).order_by(Order.id.desc())
    if user.role == "client":
        cid = await _resolve_client_canteen_id(db, user, request)
        stmt = stmt.where(Order.client_id == user.id, Order.canteen_id == cid)
    elif user.role == "delivery":
        stmt = stmt.where(Order.delivery_id == user.id)
    elif user.role == "supplier":
        allocated_to_me = Order.id.in_(
            select(OrderItemAllocation.order_id)
            .where(OrderItemAllocation.supplier_id == user.id)
            .distinct()
        )
        stmt = stmt.where(allocated_to_me)
    if status:
        stmt = stmt.where(Order.status == status)
    if order_no and order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))
    if use_delivery_filter:
        stmt = stmt.where(
            Order.expected_delivery_date >= ed_start,
            Order.expected_delivery_date <= ed_end,
        )
    else:
        stmt = stmt.where(Order.created_at >= start_dt, Order.created_at < end_dt)
    orders = (await db.scalars(stmt)).all()
    order_ids = [o.id for o in orders]
    confirmed_map = await _receiving_confirmed_counts(db, order_ids)
    rows = [_serialize_order_for_list(o, int(confirmed_map.get(o.id, 0))) for o in orders]
    diff_map = await receiving_difference_summary_map(db, orders)
    for d in rows:
        d["receiving_difference"] = diff_map.get(
            int(d["id"]),
            {
                "has_receiving_difference": False,
                "difference_type": "none",
                "difference_label": "无差异",
                "shortage_kg": 0,
                "overage_kg": 0,
                "deduction_amount": 0,
            },
        )
    if user.role == "delivery":
        uid_set: set[int] = set()
        ccid_set: set[int] = set()
        for d in rows:
            if d.get("client_id") is not None:
                uid_set.add(int(d["client_id"]))
            raw_cc = d.get("canteen_id")
            if raw_cc is not None:
                ccid_set.add(int(raw_cc))
        user_map: dict[int, User] = {}
        if uid_set:
            urows = (await db.scalars(select(User).where(User.id.in_(list(uid_set))))).all()
            user_map = {int(u.id): u for u in urows}
        canteen_name_map: dict[int, str] = {}
        if ccid_set:
            crows = (
                await db.scalars(select(ClientCanteen).where(ClientCanteen.id.in_(list(ccid_set))))
            ).all()
            canteen_name_map = {int(c.id): (c.name or "") for c in crows}
        for d in rows:
            cid = int(d.get("client_id") or 0)
            cu = user_map.get(cid)
            d["client_name"] = (cu.company_name or cu.username if cu else "") or ""
            raw_cc = d.get("canteen_id")
            d["canteen_name"] = canteen_name_map.get(int(raw_cc), "") if raw_cc is not None else ""
        agg_map = await delivery_stage_aggregates(db, order_ids)
        for d in rows:
            agg = agg_map.get(int(d["id"]), {})
            d["allocation_total"] = int(agg.get("alloc_total", 0))
            d["allocation_shipped"] = int(agg.get("alloc_shipped", 0))
            d["all_allocations_shipped"] = bool(agg.get("all_shipped", False))
            d["delivery_sort_total"] = int(agg.get("sort_total", 0))
            d["delivery_sort_done"] = int(agg.get("sort_done", 0))
            d["delivery_sort_all_done"] = bool(agg.get("sort_all_done", True))
            d["stage"] = compute_delivery_stage(
                d.get("status"),
                int(agg.get("alloc_total", 0)),
                int(agg.get("alloc_shipped", 0)),
                bool(agg.get("all_shipped", False)),
                bool(agg.get("sort_all_done", True)),
            )
    if user.role == "supplier":
        oids = [int(d["id"]) for d in rows]
        portion_map: dict[int, float] = {}
        if oids:
            pr = (
                await db.execute(
                    select(
                        OrderItemAllocation.order_id,
                        func.coalesce(
                            func.sum(OrderItemAllocation.quantity * OrderItemAllocation.unit_price),
                            0,
                        ),
                    )
                    .where(
                        OrderItemAllocation.order_id.in_(oids),
                        OrderItemAllocation.supplier_id == user.id,
                    )
                    .group_by(OrderItemAllocation.order_id)
                )
            ).all()
            portion_map = {int(r[0]): float(r[1] or 0) for r in pr}
        uid_set: set[int] = set()
        for d in rows:
            if d.get("client_id") is not None:
                uid_set.add(int(d["client_id"]))
            if d.get("delivery_id") is not None:
                uid_set.add(int(d["delivery_id"]))
        user_map: dict[int, User] = {}
        if uid_set:
            urows = (await db.scalars(select(User).where(User.id.in_(list(uid_set))))).all()
            user_map = {int(u.id): u for u in urows}
        for d in rows:
            oid = int(d["id"])
            part = round(float(portion_map.get(oid, 0)), 2)
            d.pop("items_json", None)
            d.pop("items_snapshot_json", None)
            d.pop("receive_signatures_json", None)
            d.pop("total_volume_m3", None)
            d.pop("total_weight_kg", None)
            d["supply_portion_amount"] = part
            d["total_amount"] = part
            d.pop("supplier_id", None)
            cid = int(d.pop("client_id", 0) or 0)
            did = int(d.pop("delivery_id", 0) or 0)
            cu = user_map.get(cid)
            du = user_map.get(did)
            d["client_name"] = (cu.company_name or cu.username if cu else "") or ""
            d["delivery_name"] = (du.company_name or du.username if du else "") or ""
            d.pop("receiving_total_lines", None)
            d.pop("receiving_confirmed_count", None)
    return rows


@router.get("/receiving/differences")
@router.get("/receiving-differences")
async def list_receiving_differences(
    order_no: Optional[str] = None,
    client_keyword: Optional[str] = None,
    supplier_keyword: Optional[str] = None,
    reason: Optional[str] = None,
    status: Optional[str] = None,
    created_date_start: Optional[str] = None,
    created_date_end: Optional[str] = None,
    expected_delivery_date_start: Optional[str] = None,
    expected_delivery_date_end: Optional[str] = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in {"client", "delivery", "operation"}:
        raise HTTPException(403, "无权限查看收货差异")
    try:
        start_dt = datetime.combine(date.fromisoformat(created_date_start), time.min) if created_date_start else None
        end_dt = (
            datetime.combine(date.fromisoformat(created_date_end) + timedelta(days=1), time.min)
            if created_date_end
            else None
        )
        delivery_start = date.fromisoformat(expected_delivery_date_start) if expected_delivery_date_start else None
        delivery_end = date.fromisoformat(expected_delivery_date_end) if expected_delivery_date_end else None
    except ValueError:
        raise HTTPException(400, "时间筛选格式错误，需为 YYYY-MM-DD")
    return await list_receiving_shortage_returns(
        db,
        role=str(user.role),
        user_id=int(user.id),
        order_no=order_no,
        client_keyword=client_keyword,
        supplier_keyword=supplier_keyword,
        reason=reason,
        status=status,
        created_date_start=start_dt,
        created_date_end=end_dt,
        expected_delivery_date_start=delivery_start,
        expected_delivery_date_end=delivery_end,
    )


async def _statement_contains_order(statement: BillingStatement, order_id: int) -> bool:
    source = statement.source_snapshot_json or {}
    try:
        return int(order_id) in {int(i) for i in (source.get("order_ids") or [])}
    except (TypeError, ValueError):
        return False


async def _notify_return_reversals(db: AsyncSession, order: Order, created: list) -> None:
    """退货红冲后，只给每条红冲所属对账单的 owner 推送（不广播全员）。"""
    for rev in created or []:
        ss = rev.source_snapshot_json or {}
        nums = "、".join(str(n) for n in (ss.get("order_numbers") or []) if n) or (order.order_no or "")
        amount = abs(float(rev.amount or 0))
        await push_notification(
            db,
            role=str(rev.role),
            event_type="billing_return_reversal",
            title="退货冲减",
            content=f"订单 {nums} 退货已冲减 ¥{amount:.2f}，已自动抵减你的对账单净额。",
            route=billing_route_for_role(str(rev.role)),
            target_user_ids=[int(rev.owner_user_id)],
            object_type="billing_statement",
            object_id=int(rev.id),
        )


async def _rebuild_unconfirmed_receive_billing(db: AsyncSession, order: Order, order_return=None) -> None:
    candidate_statements = (await db.scalars(select(BillingStatement))).all()
    statements = [s for s in candidate_statements if await _statement_contains_order(s, int(order.id))]
    locked_statements = [s for s in statements if str(s.status) != "待确认"]
    if locked_statements:
        # P3c 退货红冲：对账单已确认/结清，不能改原账单 → 自动开负额红冲单冲减（含上游腿），
        # 已付款部分自动结转为下期可抵扣。无退货单（如非退货触发）时不处理。
        if order_return is not None:
            created = await create_return_reversal_statements(db, order, order_return)
            await _notify_return_reversals(db, order, created)
        return

    # 对账单仍未确认：沿用「删除随单账单/明细后按当前净额重建」
    bills = (await db.scalars(select(Bill).where(Bill.order_id == int(order.id)))).all()
    locked_bills = [b for b in bills if str(b.status) != "待结算"]
    if locked_bills:
        raise HTTPException(409, "相关随单账单已结算，不能自动调整，请走人工账务调整")
    if not bills and not statements:
        return
    if bills:
        await db.execute(delete(Bill).where(Bill.order_id == int(order.id)))
    for statement in statements:
        await db.delete(statement)
    await create_receive_bills(db, order)
    await create_receive_billing_statements(db, order)


@router.post("/returns/{return_id}/review", dependencies=[Depends(require_role("delivery"))])
async def review_order_return(
    return_id: int,
    body: ReturnReviewIn,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ret = await db.scalar(select(OrderReturn).where(OrderReturn.id == return_id, OrderReturn.source == "receive_shortage"))
    if not ret:
        raise HTTPException(404, "退货单不存在")
    order = await db.scalar(select(Order).where(Order.id == int(ret.order_id)))
    if not order:
        raise HTTPException(404, "订单不存在")
    if int(order.delivery_id) != int(user.id):
        raise HTTPException(403, "仅订单所属配送商可审核")
    if str(ret.status) != "pending_delivery_review":
        raise HTTPException(400, "仅待配送商审核的退货单可审核")

    old_status = str(ret.status)
    if body.action == "approve":
        ret.status = "confirmed"
    else:
        ret.status = "rejected"
    ret.reviewed_by_user_id = int(user.id)
    ret.reviewed_at = datetime.utcnow()
    ret.review_note = (body.note or "").strip() or None

    if body.action == "approve":
        await _rebuild_unconfirmed_receive_billing(db, order, ret)

    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_return_delivery_review",
        category="order",
        object_type="order_return",
        object_id=ret.id,
        detail=f"配送商审核退货单 {ret.return_no}: {old_status} -> {ret.status}",
        before_json={"status": old_status},
        after_json={"status": ret.status, "review_note": ret.review_note},
        **_audit_meta(request),
    )
    await db.commit()
    return {
        "message": "审核完成",
        "return_id": int(ret.id),
        "return_no": ret.return_no,
        "status": ret.status,
        "status_label": _return_status_label(ret.status),
    }


@router.post("/{order_id}/receiving/lines/{line_index}/draft", dependencies=[Depends(require_role("client"))])
async def save_receiving_line_draft(
    order_id: int,
    line_index: int,
    body: ReceivingDraftIn,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "收货":
        raise HTTPException(400, "仅收货状态可记录称重草稿")
    n = _order_line_count(order)
    if line_index < 1 or line_index > n:
        raise HTTPException(400, "行号无效")
    await _ensure_receiving_lines(db, order)
    row = await db.scalar(
        select(OrderReceivingLine).where(
            OrderReceivingLine.order_id == order.id,
            OrderReceivingLine.line_index == line_index,
        )
    )
    if not row:
        raise HTTPException(500, "称重行初始化失败")
    if str(row.status) != "pending":
        raise HTTPException(400, "该行已确认，请先撤销确认再修改草稿")
    row.draft_kg = float(body.net_kg) if body.net_kg is not None else float(body.sample_kg) if body.sample_kg is not None else None
    row.confirmed_quantity = float(body.received_quantity) if body.received_quantity is not None else row.confirmed_quantity
    row.confirmed_unit = (body.received_unit or row.confirmed_unit or "").strip()[:20] or None
    row.sample_kg = float(body.sample_kg) if body.sample_kg is not None else row.sample_kg
    row.updated_at = datetime.utcnow()
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_receiving_draft",
        category="order",
        object_type="order",
        object_id=order.id,
        detail=f"行{line_index}收货草稿 net_kg={body.net_kg} received_quantity={body.received_quantity}",
        **_audit_meta(request),
    )
    await db.commit()
    return {"message": "ok", "line_index": line_index, "draft_kg": float(row.draft_kg) if row.draft_kg is not None else None}


@router.post("/{order_id}/receiving/lines/{line_index}/confirm", dependencies=[Depends(require_role("client"))])
async def confirm_receiving_line(
    order_id: int,
    line_index: int,
    body: ReceivingConfirmIn,
    request: Request,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "收货":
        raise HTTPException(400, "仅收货状态可确认称重")
    n = _order_line_count(order)
    if line_index < 1 or line_index > n:
        raise HTTPException(400, "行号无效")
    await _ensure_receiving_lines(db, order)
    row = await db.scalar(
        select(OrderReceivingLine).where(
            OrderReceivingLine.order_id == order.id,
            OrderReceivingLine.line_index == line_index,
        )
    )
    if not row:
        raise HTTPException(500, "称重行初始化失败")
    if str(row.status) != "pending":
        raise HTTPException(400, "该行已确认")
    await _apply_receiving_line_payload(db, order, line_index, body, user.id)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_receiving_confirm_line",
        category="order",
        object_type="order",
        object_id=order.id,
        detail=f"行{line_index}确认收货 net_kg={body.net_kg} received_quantity={body.received_quantity}",
        **_audit_meta(request),
    )
    await upsert_returns_for_order(db, order, user.id)
    await db.commit()
    background_tasks.add_task(create_receiving_candidate_background, order_id, line_index)
    return {"message": "ok", "line_index": line_index, "status": "confirmed"}


@router.post("/{order_id}/receiving/lines/{line_index}/lock-photo", dependencies=[Depends(require_role("client"))])
async def upload_receiving_line_lock_photo(
    order_id: int,
    line_index: int,
    request: Request,
    file: UploadFile = File(...),
    device_id: Optional[str] = Form(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "收货":
        raise HTTPException(400, "仅收货状态可上传称重留痕")
    n = _order_line_count(order)
    if line_index < 1 or line_index > n:
        raise HTTPException(400, "行号无效")
    await _ensure_receiving_lines(db, order)
    row = await db.scalar(
        select(OrderReceivingLine).where(
            OrderReceivingLine.order_id == order.id,
            OrderReceivingLine.line_index == line_index,
        )
    )
    if not row:
        raise HTTPException(500, "称重行初始化失败")
    if str(row.status) != "pending":
        raise HTTPException(400, "该行已确认，请先撤销确认再上传照片")
    url = await upload_receiving_lock_photo(file)
    taken_at = datetime.utcnow()
    row.lock_photo_url = url
    row.lock_photo_taken_at = taken_at
    row.lock_photo_device_id = (device_id or "").strip()[:128] or None
    row.updated_at = taken_at
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_receiving_lock_photo",
        category="order",
        object_type="order",
        object_id=order.id,
        detail=f"行{line_index}上传称重留痕照片",
        **_audit_meta(request),
    )
    await db.commit()
    return {
        "message": "ok",
        "line_index": line_index,
        "lock_photo_url": url,
        "lock_photo_taken_at": taken_at.isoformat(),
        "lock_photo_device_id": row.lock_photo_device_id,
    }


@router.post("/{order_id}/receiving/return-photo", dependencies=[Depends(require_role("client"))])
async def upload_receiving_return_evidence_photo(
    order_id: int,
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.client_id == user.id, Order.canteen_id == cid)
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "收货":
        raise HTTPException(400, "仅收货状态可上传退货证据")
    url = await upload_receiving_return_photo(file)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_receiving_return_photo",
        category="order",
        object_type="order",
        object_id=order.id,
        detail="上传退货证据照片",
        **_audit_meta(request),
    )
    await db.commit()
    return {"message": "ok", "url": url}


@router.post("/{order_id}/receiving/signature-photo", dependencies=[Depends(require_role("client"))])
async def upload_receiving_signature_photo(
    order_id: int,
    request: Request,
    file: UploadFile = File(...),
    role: str = Form(""),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.client_id == user.id, Order.canteen_id == cid)
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "收货":
        raise HTTPException(400, "仅收货状态可上传签字")
    url = await upload_receiving_signature(file)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_receiving_signature_photo",
        category="order",
        object_type="order",
        object_id=order.id,
        detail="上传食堂签收人签字照片" if role == "warehouse" else "上传送货方签字照片" if role == "carrier" else "上传收货签字照片",
        **_audit_meta(request),
    )
    await db.commit()
    return {"message": "ok", "url": url, "role": role}


@router.post("/{order_id}/receiving/lines/{line_index}/reopen", dependencies=[Depends(require_role("client"))])
async def reopen_receiving_line(
    order_id: int,
    line_index: int,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "收货":
        raise HTTPException(400, "仅收货状态可撤销行确认")
    n = _order_line_count(order)
    if line_index < 1 or line_index > n:
        raise HTTPException(400, "行号无效")
    row = await db.scalar(
        select(OrderReceivingLine).where(
            OrderReceivingLine.order_id == order.id,
            OrderReceivingLine.line_index == line_index,
        )
    )
    if not row:
        raise HTTPException(404, "该行尚无称重记录")
    if str(row.status) != "confirmed":
        raise HTTPException(400, "该行未处于已确认状态")
    row.status = "pending"
    row.confirmed_kg = None
    row.confirmed_at = None
    row.confirmed_by_user_id = None
    row.shortage_reason_code = None
    row.shortage_reason_detail = None
    row.shortage_ordered_kg = None
    row.shortage_delta_kg = None
    row.return_photo_urls_json = None
    row.return_note = None
    row.updated_at = datetime.utcnow()
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_receiving_reopen_line",
        category="order",
        object_type="order",
        object_id=order.id,
        detail=f"撤销行{line_index}称重确认",
        **_audit_meta(request),
    )
    await upsert_returns_for_order(db, order, user.id)
    await db.commit()
    return {"message": "ok", "line_index": line_index, "status": "pending"}


async def _get_order_for_detail_access(
    order_id: int,
    request: Request,
    user: User,
    db: AsyncSession,
) -> Order:
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    if user.role == "client":
        if order.client_id != user.id:
            raise HTTPException(403, "无权限查看")
        cid = await _resolve_client_canteen_id(db, user, request)
        if order.canteen_id is None or int(order.canteen_id) != cid:
            raise HTTPException(403, "订单不属于当前所选食堂")
    elif user.role == "delivery":
        if order.delivery_id != user.id:
            raise HTTPException(403, "无权限查看")
    elif user.role in {"supplier", "factory"}:
        if not await _supplier_can_act_on_order(db, order, user.id):
            raise HTTPException(403, "无权限查看")
    elif user.role != "operation":
        raise HTTPException(403, "无权限查看")
    return order


@router.get("/{order_id}/logistics-tracking")
async def order_logistics_tracking(
    order_id: int,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role in {"supplier", "factory"}:
        raise HTTPException(403, "无权限查看物流位置")
    order = await _get_order_for_detail_access(order_id, request, user, db)
    tracking = await build_order_logistics_tracking(
        db,
        order,
        viewer_role=str(user.role),
        viewer_user_id=int(user.id),
    )
    return {
        "order_id": int(order.id),
        "order_status": str(order.status),
        "refreshed_at": datetime.utcnow().isoformat(),
        "logistics_tracking": tracking,
    }


@router.get("/{order_id}")
async def order_detail(
    order_id: int,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await _get_order_for_detail_access(order_id, request, user, db)

    payload = jsonable_encoder(order)
    payload["receive_signatures_json"] = _normalize_signature_payload(payload.get("receive_signatures_json"))

    if user.role in {"client", "delivery"}:
        ext = await build_order_detail_extensions(
            db, order, viewer_role=str(user.role), viewer_user_id=int(user.id)
        )
        payload.update(ext)
        c_user = await db.scalar(select(User).where(User.id == order.client_id))
        payload["client_name"] = (c_user.company_name or c_user.username if c_user else "") or ""
        all_alloc_summary = await _allocation_shipping_summary(db, order.id)
        payload["allocation_total"] = int(all_alloc_summary["total"])
        payload["allocation_shipped"] = int(all_alloc_summary["shipped"])
        payload["all_allocations_shipped"] = bool(all_alloc_summary["all_shipped"])
        sort_summary = await delivery_sort_summary_for_order(db, int(order.id))
        payload["delivery_sort_total"] = int(sort_summary["total"])
        payload["delivery_sort_done"] = int(sort_summary["sorted"])
        payload["delivery_sort_all_done"] = bool(sort_summary["all_sorted"])
        if int(sort_summary["total"]) <= 0:
            payload["delivery_sort_status_text"] = "无分检任务"
        elif bool(sort_summary["all_sorted"]):
            payload["delivery_sort_status_text"] = "分检完成待发货"
        elif int(sort_summary["sorted"]) > 0:
            payload["delivery_sort_status_text"] = "分检中"
        else:
            payload["delivery_sort_status_text"] = "待分检"
        # 按供货商聚合的进度/取货阻塞含供货商身份，仅配送商可见；客户视角已脱敏，不构建。
        if user.role == "delivery":
            allocations = payload["allocations"]
            alloc_summary_map: dict[int, dict] = {}
            for row in allocations:
                sid = int(row["supplier_id"])
                entry = alloc_summary_map.setdefault(
                    sid,
                    {
                        "supplier_id": sid,
                        "supplier_name": row["supplier_name"],
                        "allocation_total": 0,
                        "allocation_shipped": 0,
                        "total_amount": 0.0,
                    },
                )
                entry["allocation_total"] += 1
                entry["total_amount"] += float(row.get("amount") or 0)
                if str(row.get("status") or "") == "已出库":
                    entry["allocation_shipped"] += 1
            allocation_status_summary = sorted(
                [
                    {
                        **v,
                        "total_amount": round(float(v.get("total_amount") or 0), 2),
                        "all_shipped": bool(
                            v["allocation_total"] > 0 and v["allocation_shipped"] == v["allocation_total"]
                        ),
                    }
                    for v in alloc_summary_map.values()
                ],
                key=lambda x: x["supplier_id"],
            )
            payload["allocation_status_summary"] = allocation_status_summary
            payload["pickup_blockers"] = [
                {
                    "supplier_id": int(s["supplier_id"]),
                    "supplier_name": s["supplier_name"],
                    "remaining_count": int(s["allocation_total"] - s["allocation_shipped"]),
                }
                for s in allocation_status_summary
                if int(s["allocation_shipped"]) < int(s["allocation_total"])
            ]
        payload["dispatch_trip"] = None
        payload["dispatch_items"] = []
        payload["dispatch_loaded_count"] = 0
        payload["dispatch_not_loaded_count"] = 0
        dispatch_row = (
            await db.execute(
                select(DeliveryDispatchTrip, DeliveryDispatchStop)
                .join(DeliveryDispatchStop, DeliveryDispatchStop.trip_id == DeliveryDispatchTrip.id)
                .where(
                    DeliveryDispatchStop.order_id == order.id,
                    DeliveryDispatchTrip.status.in_(["待发车", "有阻塞", "运输中", "已完成"]),
                )
                .order_by(DeliveryDispatchTrip.id.desc())
                .limit(1)
            )
        ).first()
        if dispatch_row:
            dispatch_trip, dispatch_stop = dispatch_row
            dispatch_items = (
                await db.scalars(
                    select(DeliveryDispatchItem)
                    .where(DeliveryDispatchItem.stop_id == dispatch_stop.id)
                    .order_by(DeliveryDispatchItem.id.asc())
                )
            ).all()
            not_loaded_statuses = {"滞留未装", "取消随车", "供应商迟到", "质量问题", "现场缺货", "其他异常"}
            payload["dispatch_trip"] = {
                "id": int(dispatch_trip.id),
                "route_no": dispatch_trip.route_no,
                "status": dispatch_trip.status,
                "depart_mode": dispatch_trip.depart_mode,
                "vehicle_no": dispatch_trip.vehicle_no,
                "driver_name": dispatch_trip.driver_name,
                "departure_time": dispatch_trip.departure_time,
                "departed_at": dispatch_trip.departed_at.isoformat() if dispatch_trip.departed_at else None,
            }
            payload["dispatch_items"] = [
                {
                    "id": int(item.id),
                    "allocation_id": int(item.allocation_id),
                    "supplier_id": int(item.supplier_id),
                    "supplier_name": item.supplier_name,
                    "product_name": item.product_name,
                    "spec_unit": item.spec_unit,
                    "quantity": float(item.quantity or 0),
                    "unit": item.unit,
                    "status": item.status,
                    "reason_code": item.reason_code,
                    "reason_detail": item.reason_detail,
                    "attachments_json": item.attachments_json or [],
                }
                for item in dispatch_items
            ]
            payload["dispatch_loaded_count"] = len(
                [item for item in dispatch_items if str(item.status) == "已装车"]
            )
            payload["dispatch_not_loaded_count"] = len(
                [item for item in dispatch_items if str(item.status) in not_loaded_statuses]
            )
        return payload

    item_snapshot_map: dict[int, dict] = {}
    for idx, snap in enumerate(order.items_snapshot_json or [], 1):
        if isinstance(snap, dict):
            item_snapshot_map[idx] = snap
    product_ids_from_order = {
        int(i.get("product_id") or 0) for i in (order.items_json or []) if int(i.get("product_id") or 0) > 0
    }
    product_meta_map: dict[int, dict] = {}
    if product_ids_from_order:
        product_rows = (
            await db.scalars(
                select(Product).where(Product.id.in_(list(product_ids_from_order)))
            )
        ).all()
        product_meta_map = {
            int(p.id): {
                "unit": p.unit or "",
                "spec": p.spec or "",
                "name": p.name or f"商品#{int(p.id)}",
                "quality_report_mode": str(p.quality_report_mode or "batch"),
                "standard_type": str(p.standard_type or "standard"),
                "unit_weight_kg": _to_float_or_none(p.unit_weight_kg),
            }
            for p in product_rows
        }
    order_items = []
    for idx, item in enumerate(order.items_json or [], 1):
        snap = item_snapshot_map.get(idx, {})
        pid = int(item.get("product_id") or snap.get("product_id") or 0)
        pmeta = product_meta_map.get(pid, {})
        qty = float(item.get("quantity") or 0)
        unit_price = float(item.get("unit_price") or 0)
        amount = round(qty * unit_price, 2)
        order_items.append(
            {
                "line_no": idx,
                "product_id": pid,
                "product_name": snap.get("product_name") or pmeta.get("name") or f"商品#{pid}",
                "spec": snap.get("spec") or pmeta.get("spec") or "",
                "unit": snap.get("unit") or pmeta.get("unit") or "",
                "quantity": qty,
                "unit_price": unit_price,
                "amount": amount,
                "standard_type": snap.get("standard_type") or pmeta.get("standard_type") or "standard",
                "unit_weight_kg": snap.get("unit_weight_kg") if snap.get("unit_weight_kg") is not None else pmeta.get("unit_weight_kg"),
                "category1_id": snap.get("category1_id"),
                "category1_name": snap.get("category1_name") or "",
                "category2_id": snap.get("category2_id"),
                "category2_name": snap.get("category2_name") or "",
            }
        )
    payload["order_items"] = order_items

    recv_rows = (
        await db.scalars(
            select(OrderReceivingLine)
            .where(OrderReceivingLine.order_id == order.id)
            .order_by(OrderReceivingLine.line_index.asc())
        )
    ).all()
    receiving_billing = await build_receiving_billing_snapshot(db, order)
    receiving_billing_lines = {
        int(x.get("line_index") or 0): x for x in (receiving_billing.get("lines") or [])
    }
    recv_by_line = {int(r.line_index): r for r in recv_rows}
    for it in order_items:
        ln = int(it["line_no"])
        rr = recv_by_line.get(ln)
        it["receiving_status"] = str(rr.status) if rr else None
        it["receiving_draft_kg"] = float(rr.draft_kg) if rr and rr.draft_kg is not None else None
        it["receiving_confirmed_kg"] = float(rr.confirmed_kg) if rr and rr.confirmed_kg is not None else None
        it["receiving_confirmed_quantity"] = float(rr.confirmed_quantity) if rr and rr.confirmed_quantity is not None else None
        it["receiving_confirmed_unit"] = rr.confirmed_unit if rr else None
        it["receiving_sample_kg"] = float(rr.sample_kg) if rr and rr.sample_kg is not None else None
        it["shortage_reason_code"] = rr.shortage_reason_code if rr else None
        it["shortage_reason_detail"] = rr.shortage_reason_detail if rr else None
        it["shortage_delta_kg"] = float(rr.shortage_delta_kg) if rr and rr.shortage_delta_kg is not None else None
        it["return_photo_urls"] = normalize_public_image_urls(rr.return_photo_urls_json if rr and rr.return_photo_urls_json else [])
        it["return_note"] = rr.return_note if rr else None
        it["lock_photo_url"] = normalize_public_image_url(rr.lock_photo_url if rr else None)
        it["lock_photo_taken_at"] = rr.lock_photo_taken_at.isoformat() if rr and rr.lock_photo_taken_at else None
        it["lock_photo_device_id"] = rr.lock_photo_device_id if rr else None
    order_item_by_line = {int(it["line_no"]): it for it in order_items}
    payload["receiving_lines"] = [
        _receiving_line_payload(r, receiving_billing_lines, order_item_by_line) for r in recv_rows
    ]
    nlines = _order_line_count(order)
    payload["receiving_total_lines"] = nlines
    payload["receiving_confirmed_count"] = len([r for r in recv_rows if str(r.status) == "confirmed"])

    ret_hdr = await db.scalar(
        select(OrderReturn).where(OrderReturn.order_id == order.id, OrderReturn.source == "receive_shortage")
    )
    if ret_hdr:
        ret_lns = (
            await db.scalars(
                select(OrderReturnLine).where(OrderReturnLine.order_return_id == int(ret_hdr.id))
            )
        ).all()
        payload["order_return"] = {
            "id": int(ret_hdr.id),
            "return_no": ret_hdr.return_no,
            "status": str(ret_hdr.status),
            "status_label": _return_status_label(ret_hdr.status),
            "reviewed_by_user_id": int(ret_hdr.reviewed_by_user_id) if ret_hdr.reviewed_by_user_id is not None else None,
            "reviewed_at": ret_hdr.reviewed_at.isoformat() if ret_hdr.reviewed_at else None,
            "review_note": ret_hdr.review_note,
            "source": "receive_shortage",
            "source_label": "收货少收退货单",
            "lines": [_return_line_payload(x) for x in ret_lns],
        }
    else:
        payload["order_return"] = None
    payload["receiving_billing"] = receiving_billing
    payload["receiving_total_kg"] = receiving_billing.get("received_kg")
    payload["receiving_amount"] = receiving_billing.get("received_amount")
    payload["receiving_deduction_amount"] = receiving_billing.get("deduction_amount")

    alloc_rows = (
        await db.scalars(
            select(OrderItemAllocation)
            .where(OrderItemAllocation.order_id == order.id)
            .order_by(OrderItemAllocation.line_no.asc(), OrderItemAllocation.id.asc())
        )
    ).all()
    supplier_ids = sorted({int(r.supplier_id) for r in alloc_rows})
    supplier_name_map: dict[int, str] = {}
    if supplier_ids:
        supplier_rows = (
            await db.scalars(
                select(User).where(User.id.in_(supplier_ids))
            )
        ).all()
        supplier_name_map = {
            int(s.id): (s.company_name or s.username or f"供货商#{s.id}") for s in supplier_rows
        }
    periodic_by_key = await approved_periodic_report_map(
        db,
        alloc_rows,
        cover_date=quality_cover_date_for_order(order),
    )
    allocations = []
    for row in alloc_rows:
        line_no = int(row.line_no)
        item_snap = item_snapshot_map.get(line_no, {})
        pmeta = product_meta_map.get(int(row.product_id), {})
        qmode = str(pmeta.get("quality_report_mode") or "batch")
        periodic_report = None
        if qmode == "periodic":
            periodic_report = periodic_report_payload(
                periodic_by_key.get((int(row.product_id), int(row.supplier_id)))
            )
        allocations.append(
            {
                "id": int(row.id),
                "line_no": line_no,
                "product_id": int(row.product_id),
                "product_name": item_snap.get("product_name") or pmeta.get("name") or f"商品#{int(row.product_id)}",
                "spec": item_snap.get("spec") or pmeta.get("spec") or "",
                "unit": item_snap.get("unit") or pmeta.get("unit") or "",
                "quantity": float(row.quantity),
                "unit_price": float(row.unit_price),
                "amount": round(float(row.quantity) * float(row.unit_price), 2),
                "supplier_id": int(row.supplier_id),
                "supplier_name": supplier_name_map.get(int(row.supplier_id), f"供货商#{int(row.supplier_id)}"),
                "status": row.status,
                "label_print_count": int(row.label_print_count or 0),
                "quality_report_mode": qmode,
                "periodic_quality_report": periodic_report,
                "quality_covered_by": "periodic" if periodic_report else None,
                "missing_quality": bool(qmode == "periodic" and periodic_report is None),
                "missing_quality_shipped": bool(
                    qmode == "periodic" and periodic_report is None and str(row.status) == "已出库"
                ),
            }
        )
    payload["allocations"] = allocations

    alloc_summary_map: dict[int, dict] = {}
    for row in allocations:
        sid = int(row["supplier_id"])
        entry = alloc_summary_map.setdefault(
            sid,
            {
                "supplier_id": sid,
                "supplier_name": row["supplier_name"],
                "allocation_total": 0,
                "allocation_shipped": 0,
                "total_amount": 0.0,
            },
        )
        entry["allocation_total"] += 1
        entry["total_amount"] += float(row.get("amount") or 0)
        if str(row.get("status") or "") == "已出库":
            entry["allocation_shipped"] += 1
    allocation_status_summary = sorted(
        [
            {
                **v,
                "total_amount": round(float(v.get("total_amount") or 0), 2),
                "all_shipped": bool(v["allocation_total"] > 0 and v["allocation_shipped"] == v["allocation_total"]),
            }
            for v in alloc_summary_map.values()
        ],
        key=lambda x: x["supplier_id"],
    )
    payload["allocation_status_summary"] = allocation_status_summary

    all_alloc_summary = await _allocation_shipping_summary(db, order.id)
    payload["allocation_total"] = int(all_alloc_summary["total"])
    payload["allocation_shipped"] = int(all_alloc_summary["shipped"])
    payload["all_allocations_shipped"] = bool(all_alloc_summary["all_shipped"])
    sort_summary = await delivery_sort_summary_for_order(db, int(order.id))
    payload["delivery_sort_total"] = int(sort_summary["total"])
    payload["delivery_sort_done"] = int(sort_summary["sorted"])
    payload["delivery_sort_all_done"] = bool(sort_summary["all_sorted"])
    if int(sort_summary["total"]) <= 0:
        payload["delivery_sort_status_text"] = "无分检任务"
    elif bool(sort_summary["all_sorted"]):
        payload["delivery_sort_status_text"] = "分检完成待发货"
    elif int(sort_summary["sorted"]) > 0:
        payload["delivery_sort_status_text"] = "分检中"
    else:
        payload["delivery_sort_status_text"] = "待分检"
    payload["pickup_blockers"] = [
        {
            "supplier_id": int(s["supplier_id"]),
            "supplier_name": s["supplier_name"],
            "remaining_count": int(s["allocation_total"] - s["allocation_shipped"]),
        }
        for s in allocation_status_summary
        if int(s["allocation_shipped"]) < int(s["allocation_total"])
    ]
    if user.role in {"supplier", "factory"}:
        portion = await db.scalar(
            select(
                func.coalesce(
                    func.sum(OrderItemAllocation.quantity * OrderItemAllocation.unit_price),
                    0,
                )
            ).where(
                OrderItemAllocation.order_id == order.id,
                OrderItemAllocation.supplier_id == user.id,
            )
        )
        any_alloc = await db.scalar(
            select(
                exists(
                    select(OrderItemAllocation.id).where(OrderItemAllocation.order_id == order.id)
                )
            )
        )
        part_amt = float(portion or 0)
        payload["supply_portion_amount"] = round(part_amt, 2)
        payload["has_delivery_allocation"] = bool(any_alloc)
        my_alloc_summary = await _allocation_shipping_summary(db, order.id, supplier_id=user.id)
        payload["my_allocation_total"] = int(my_alloc_summary["total"])
        payload["my_allocation_shipped"] = int(my_alloc_summary["shipped"])
        payload["my_allocations_shipped"] = bool(my_alloc_summary["all_shipped"])
        supplier_status, supplier_status_text = _supplier_view_status(
            str(order.status or ""),
            int(my_alloc_summary["total"]),
            int(my_alloc_summary["shipped"]),
        )
        payload["supplier_status"] = supplier_status
        payload["supplier_status_text"] = supplier_status_text
        my_sort_record = await _supplier_sort_record(db, order.id, user.id)
        label_gate = await _supplier_label_gate_state(db, order.id, user.id)
        payload["my_label_printed"] = bool(my_sort_record and my_sort_record.label_printed)
        payload["my_sort_status_text"] = "分拣完成" if bool(label_gate["can_ship_by_print"]) else "待分拣"
        payload["my_sorted_at"] = my_sort_record.sorted_at if my_sort_record else None
        payload["my_order_label_printed"] = bool(label_gate["order_label_printed"])
        payload["my_line_label_total"] = int(label_gate["line_label_total"])
        payload["my_line_label_printed_count"] = int(label_gate["line_label_printed_count"])
        payload["my_all_line_labels_printed"] = bool(label_gate["all_line_labels_printed"])
        payload["my_can_ship_by_print"] = bool(label_gate["can_ship_by_print"])
        payload["my_printed_line_ids"] = list(label_gate["printed_line_ids"])
        payload["my_unprinted_line_count"] = max(
            0,
            int(label_gate["line_label_total"]) - int(label_gate["line_label_printed_count"]),
        )
        payload["my_total_label_print_count"] = int(label_gate.get("total_label_print_count") or 0)
        counts_map = label_gate.get("label_print_counts") or {}
        for row in allocations:
            if int(row.get("supplier_id") or 0) != int(user.id):
                continue
            aid = int(row.get("id") or 0)
            cnt = int(counts_map.get(aid, row.get("label_print_count") or 0))
            row["label_print_count"] = cnt
            row["line_label_printed"] = cnt >= 1
        # 供货商为配送商下游分包方：仅可见本户分包行，不返回整单明细、他户分包及收货双签等
        my_alloc_rows = [r for r in allocations if int(r.get("supplier_id") or 0) == int(user.id)]
        my_line_nos = {int(r["line_no"]) for r in my_alloc_rows}
        payload["allocations"] = my_alloc_rows
        payload["allocation_status_summary"] = [
            s for s in allocation_status_summary if int(s.get("supplier_id") or 0) == int(user.id)
        ]
        payload["pickup_blockers"] = []
        payload["items_json"] = []
        payload["items_snapshot_json"] = []
        payload["order_items"] = [it for it in order_items if int(it.get("line_no") or 0) in my_line_nos]
        payload["receiving_lines"] = [
            r for r in payload["receiving_lines"] if int(r.get("line_index") or 0) in my_line_nos
        ]
        payload["receiving_total_lines"] = len(my_line_nos) if my_line_nos else 0
        payload["receiving_confirmed_count"] = len(
            [r for r in payload["receiving_lines"] if str(r.get("status")) == "confirmed"]
        )
        payload["allocation_total"] = int(my_alloc_summary["total"])
        payload["allocation_shipped"] = int(my_alloc_summary["shipped"])
        payload["all_allocations_shipped"] = bool(my_alloc_summary["all_shipped"])
        payload["receive_signatures_json"] = None
        c_user = await db.scalar(select(User).where(User.id == order.client_id))
        d_user = await db.scalar(select(User).where(User.id == order.delivery_id))
        payload["client_name"] = (c_user.company_name or c_user.username if c_user else "") or ""
        payload["delivery_name"] = (d_user.company_name or d_user.username if d_user else "") or ""
        for k in ("client_id", "delivery_id", "supplier_id"):
            payload.pop(k, None)
        part_amt = float(payload.get("supply_portion_amount") or 0)
        payload["total_amount"] = round(part_amt, 2)
        payload.pop("total_volume_m3", None)
        payload.pop("total_weight_kg", None)
    return payload


@router.put("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    request: Request,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "下单":
        raise HTTPException(400, "仅下单状态可取消")
    old_status = order.status
    ensure_order_transition(old_status, "取消")
    order.status = "取消"
    order.version += 1
    order.updated_at = datetime.utcnow()
    await _log_order_transition(db, order, old_status, order.status, user.id, request)
    await db.commit()
    await _emit_order_status_change(db, order, old_status, order.status)
    await _notify_order_roles(db, order, title=f"订单 {order.order_no} 已取消", content="该订单已由客户端取消。")
    await db.commit()
    return order


@router.post("/{order_id}/sort-start")
async def sort_start(
    order_id: int,
    user=Depends(require_roles("supplier", "factory")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    if not await _supplier_can_act_on_order(db, order, user.id):
        raise HTTPException(403, "无权限操作该订单")
    old_status = order.status
    ensure_order_transition(old_status, "配货")
    order.status = "配货"
    order.version += 1
    order.updated_at = datetime.utcnow()
    await _log_order_transition(db, order, old_status, order.status, 0)
    await db.commit()
    await _emit_order_status_change(db, order, old_status, order.status)
    await _notify_order_roles(
        db, order, title=f"订单 {order.order_no} 已进入配货", content="有分包供货商已开始配货。"
    )
    await db.commit()
    return order


@router.post("/{order_id}/sort-done")
async def sort_done(
    order_id: int,
    user=Depends(require_roles("supplier", "factory")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    if not await _supplier_can_act_on_order(db, order, user.id):
        raise HTTPException(403, "无权限操作该订单")
    db.add(
        SortRecord(
            order_id=order_id,
            operator_id=user.id,
            sorted_at=datetime.utcnow(),
            label_printed=False,
        )
    )
    await db.commit()
    return {"message": "分拣完成"}


@router.post("/{order_id}/print-label")
async def print_label(
    order_id: int,
    user=Depends(require_roles("supplier", "factory")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    if not await _supplier_can_act_on_order(db, order, user.id):
        raise HTTPException(403, "无权限操作该订单")
    result = await _execute_cloud_label_print(
        db,
        order=order,
        user=user,
        allocation_ids=[],
        audit_action="supplier_print_order_label",
        audit_detail=f"云打印全部标签 {order.order_no}",
        mark_order_label=True,
    )
    await db.commit()
    return result


@router.post("/{order_id}/print-allocation-labels")
async def print_allocation_labels(
    order_id: int,
    body: PrintAllocationLabelsIn,
    user=Depends(require_roles("supplier", "factory")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    if not await _supplier_can_act_on_order(db, order, user.id):
        raise HTTPException(403, "无权限操作该订单")
    ids = [int(i) for i in (body.allocation_ids or []) if int(i) > 0]
    result = await _execute_cloud_label_print(
        db,
        order=order,
        user=user,
        allocation_ids=ids,
        audit_action="supplier_print_allocation_label",
        audit_detail=f"云打印所选标签 {order.order_no} ids={ids}",
        mark_order_label=False,
    )
    await db.commit()
    return result


@router.post("/{order_id}/print-allocation-label/{allocation_id}")
async def print_allocation_label(
    order_id: int,
    allocation_id: int,
    user=Depends(require_roles("supplier", "factory")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    if not await _supplier_can_act_on_order(db, order, user.id):
        raise HTTPException(403, "无权限操作该订单")
    result = await _execute_cloud_label_print(
        db,
        order=order,
        user=user,
        allocation_ids=[int(allocation_id)],
        audit_action="supplier_print_allocation_label",
        audit_detail=f"云打印行级标签 allocation={allocation_id} {order.order_no}",
        mark_order_label=False,
    )
    await db.commit()
    return result


@router.post("/{order_id}/ship")
async def ship_order(
    order_id: int,
    user=Depends(require_roles("supplier", "factory")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    if not await _supplier_can_act_on_order(db, order, user.id):
        raise HTTPException(403, "无权限操作该订单")
    if order.status not in {"下单", "配货"}:
        raise HTTPException(400, "当前订单状态不允许分包方发货")
    label_gate = await _supplier_label_gate_state(db, order.id, user.id)
    if not bool(label_gate["can_ship_by_print"]):
        remaining = int(label_gate["line_label_total"]) - int(label_gate["line_label_printed_count"])
        raise HTTPException(
            400,
            f"请先为每条分单至少云打印 1 次标签后再发货（当前剩余{max(remaining, 0)}行未打印）",
        )

    any_alloc = await db.scalar(
        select(
            exists(
                select(OrderItemAllocation.id).where(OrderItemAllocation.order_id == order.id)
            )
        )
    )

    if any_alloc:
        my_allocs = (
            await db.scalars(
                select(OrderItemAllocation).where(
                    OrderItemAllocation.order_id == order.id,
                    OrderItemAllocation.supplier_id == user.id,
                )
            )
        ).all()
        if not my_allocs:
            raise HTTPException(403, "该订单未分包给当前账号")
        for alloc in my_allocs:
            alloc.status = "已出库"
            alloc.updated_at = datetime.utcnow()
        await _sync_abnormal_for_shipped_missing_quality(
            db, order, int(user.id), trigger="supplier_ship"
        )
    else:
        # 历史无分单订单：沿用旧逻辑
        old_status = order.status
        ensure_order_transition(old_status, "发货")
        order.status = "发货"
        order.version += 1
        order.updated_at = datetime.utcnow()
        await _log_order_transition(db, order, old_status, order.status, 0)
        await _mark_abnormal_if_quality_missing(
            db, order, actor_user_id=int(user.id), new_status=order.status
        )
        await db.commit()
        await _emit_order_status_change(db, order, old_status, order.status)
        await _notify_order_roles(db, order, title=f"订单 {order.order_no} 已发货", content="订单已发货，进入配送阶段。")
        await db.commit()
        return order

    all_summary = await _allocation_shipping_summary(db, order.id)
    await db.commit()
    if all_summary["all_shipped"]:
        await _notify_order_roles(
            db,
            order,
            title=f"订单 {order.order_no} 分包侧已全部发货",
            content="全部分包供货商已发货，配送商可确认取货。",
        )
    else:
        await _notify_order_roles(
            db,
            order,
            title=f"订单 {order.order_no} 有分包供货商发货",
            content="仍有部分分包供货商未发货，暂不可确认取货。",
        )
    await db.commit()
    return {"message": "分包发货已登记"}


@router.post("/{order_id}/pickup")
async def pickup_order(
    order_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id, Order.delivery_id == user.id))
    if not order:
        raise HTTPException(404, "订单不存在")

    any_alloc = await db.scalar(
        select(
            exists(
                select(OrderItemAllocation.id).where(OrderItemAllocation.order_id == order.id)
            )
        )
    )
    dispatch_trip = None
    if any_alloc:
        all_summary = await _allocation_shipping_summary(db, order.id)
        if not all_summary["all_shipped"]:
            raise HTTPException(400, "仍有分包供货商未发货，暂不可确认取货")
        sort_summary = await delivery_sort_summary_for_order(db, int(order.id))
        if not sort_summary["all_sorted"]:
            remaining = max(int(sort_summary["total"]) - int(sort_summary["sorted"]), 0)
            raise HTTPException(400, f"仍有 {remaining} 条分单未完成分检，暂不可确认取货")
        dispatch_trip = (
            await db.scalars(
                select(DeliveryDispatchTrip)
                .join(DeliveryDispatchStop, DeliveryDispatchStop.trip_id == DeliveryDispatchTrip.id)
                .where(
                    DeliveryDispatchStop.order_id == order.id,
                    DeliveryDispatchTrip.delivery_id == user.id,
                    DeliveryDispatchTrip.status.in_(["待发车", "有阻塞", "运输中"]),
                )
                .order_by(DeliveryDispatchTrip.id.desc())
            )
        ).first()
        if not dispatch_trip:
            raise HTTPException(400, "请先在智能排线中保存发车计划并分配司机车辆，再按车次发车")
        if str(dispatch_trip.status) != "运输中":
            raise HTTPException(
                400,
                f"订单已在车次 {dispatch_trip.route_no} 中，请到发车计划执行整车发车或异常发车",
            )
        alloc_rows = (
            await db.scalars(
                select(OrderItemAllocation).where(OrderItemAllocation.order_id == order.id)
            )
        ).all()
        supplier_ids = sorted({int(a.supplier_id) for a in alloc_rows})
        supplier_rows = (
            await db.scalars(select(User).where(User.id.in_(supplier_ids)))
        ).all() if supplier_ids else []
        supplier_name_map = {
            int(s.id): (s.company_name or s.username or f"供货商#{s.id}") for s in supplier_rows
        }
        pickup_snapshot = [
            {
                "allocation_id": int(a.id),
                "line_no": int(a.line_no),
                "supplier_id": int(a.supplier_id),
                "supplier_name": supplier_name_map.get(int(a.supplier_id), f"供货商#{int(a.supplier_id)}"),
                "quantity": float(a.quantity),
                "unit_price": float(a.unit_price),
                "status": a.status,
            }
            for a in alloc_rows
        ]
    else:
        pickup_snapshot = []

    old_status = order.status
    ensure_order_transition(old_status, "发货")
    order.status = "发货"
    order.version += 1
    order.updated_at = datetime.utcnow()
    delivery = await db.scalar(select(Delivery).where(Delivery.order_id == order_id))
    if not delivery:
        delivery = Delivery(
            order_id=order_id,
            driver_name=(dispatch_trip.driver_name if dispatch_trip else "") or "待填写",
            vehicle_no=(dispatch_trip.vehicle_no if dispatch_trip else "") or "待填写",
            route_json=(dispatch_trip.route_path_json if dispatch_trip else []) or [],
            departed_at=datetime.utcnow(),
            status="运输中",
        )
        db.add(delivery)
    else:
        if dispatch_trip:
            delivery.driver_name = dispatch_trip.driver_name or delivery.driver_name
            delivery.vehicle_no = dispatch_trip.vehicle_no or delivery.vehicle_no
            delivery.route_json = dispatch_trip.route_path_json or delivery.route_json or []
        delivery.departed_at = datetime.utcnow()
        delivery.status = "运输中"
    await _log_order_transition(db, order, old_status, order.status, user.id)
    await _mark_abnormal_if_quality_missing(
        db, order, actor_user_id=int(user.id), new_status=order.status
    )
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_pickup_confirm",
        category="order",
        object_type="order",
        object_id=order.id,
        detail=f"确认取货 {order.order_no}",
        after_json={
            "order_no": order.order_no,
            "old_status": old_status,
            "new_status": order.status,
            "allocation_count": len(pickup_snapshot),
            "allocation_snapshot": pickup_snapshot[:50],
            "dispatch_trip_id": int(dispatch_trip.id) if dispatch_trip else None,
            "dispatch_route_no": dispatch_trip.route_no if dispatch_trip else "",
        },
    )
    await db.commit()
    await _emit_order_status_change(db, order, old_status, order.status)
    await _notify_order_targets(
        db,
        order,
        title=f"订单 {order.order_no} 配送中",
        content="配送商已确认取货，订单进入配送中。",
        to_client=True,
        to_delivery=True,
        to_suppliers=True,
    )
    await db.commit()
    return {"message": "确认取货"}


@router.post("/{order_id}/deliver")
async def deliver_order(
    order_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id, Order.delivery_id == user.id))
    if not order:
        raise HTTPException(404, "订单不存在")
    old_status = order.status
    ensure_order_transition(old_status, "收货")
    order.status = "收货"
    order.version += 1
    order.updated_at = datetime.utcnow()
    delivery = await db.scalar(select(Delivery).where(Delivery.order_id == order_id))
    if delivery:
        delivery.arrived_at = datetime.utcnow()
        delivery.status = "已送达"
    dispatch_stops = (
        await db.scalars(
            select(DeliveryDispatchStop)
            .join(DeliveryDispatchTrip, DeliveryDispatchTrip.id == DeliveryDispatchStop.trip_id)
            .where(
                DeliveryDispatchStop.order_id == order_id,
                DeliveryDispatchTrip.delivery_id == user.id,
            )
        )
    ).all()
    touched_trip_ids: set[int] = set()
    now = datetime.utcnow()
    for stop in dispatch_stops:
        stop.status = "已送达"
        stop.affected = False
        stop.updated_at = now
        touched_trip_ids.add(int(stop.trip_id))
    for trip_id in touched_trip_ids:
        trip = await db.scalar(select(DeliveryDispatchTrip).where(DeliveryDispatchTrip.id == trip_id))
        if not trip:
            continue
        trip_stops = (
            await db.scalars(select(DeliveryDispatchStop).where(DeliveryDispatchStop.trip_id == trip_id))
        ).all()
        if trip_stops and all(str(s.status) == "已送达" for s in trip_stops):
            trip.status = "已完成"
            trip.completed_at = trip.completed_at or now
        trip.updated_at = now
    await _log_order_transition(db, order, old_status, order.status, user.id)
    await _mark_abnormal_if_quality_missing(
        db, order, actor_user_id=int(user.id), new_status=order.status
    )
    await close_delivery_overdue_ticket_if_delivered(db, order)
    await close_delivery_overdue_alert_if_delivered(db, order)
    await db.commit()
    await _emit_order_status_change(db, order, old_status, order.status)
    await _notify_order_targets(
        db,
        order,
        title=f"订单 {order.order_no} 已送达",
        content="订单已送达，等待客户端确认收货。",
        to_client=True,
        to_delivery=True,
        to_suppliers=True,
    )
    await db.commit()
    return order


@router.post("/{order_id}/receive")
async def receive_order(
    order_id: int,
    request: Request,
    payload: Optional[ReceiveOrderIn] = Body(None),
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != "收货":
        raise HTTPException(400, "订单未处于可收货状态")
    idem_key = request.headers.get("Idempotency-Key")
    if idem_key:
        existing = await db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.idempotency_key == idem_key,
                IdempotencyKey.scope == "order_receive",
                IdempotencyKey.resource_id == order.id,
            )
        )
        if existing:
            return {"message": "收货请求已处理", "order_id": order.id}

    body = payload or ReceiveOrderIn()
    if body.receiving_lines:
        n = _order_line_count(order)
        if len(body.receiving_lines) != n:
            raise HTTPException(400, f"称重明细数量不完整，应提交 {n} 行")
        seen: set[int] = set()
        for line in body.receiving_lines:
            if line.line_index in seen:
                raise HTTPException(400, f"称重明细行号重复：{line.line_index}")
            seen.add(line.line_index)
        if seen != set(range(1, n + 1)):
            raise HTTPException(400, "称重明细行号必须完整覆盖订单明细")
        await _ensure_receiving_lines(db, order)
        for line in body.receiving_lines:
            await _apply_receiving_line_payload(db, order, line.line_index, line, user.id)
        await write_audit_log(
            db=db,
            actor_user_id=user.id,
            action="order_receiving_batch_confirm",
            category="order",
            object_type="order",
            object_id=order.id,
            detail=f"双签收货批量提交称重明细 {len(body.receiving_lines)} 行",
            **_audit_meta(request),
        )

    use_receiving = bool(body.receiving_lines) or await _has_receiving_lines(db, order.id)
    if use_receiving:
        if not await _all_receiving_lines_confirmed(db, order):
            raise HTTPException(400, "尚有订单明细未完成称重确认")
        wh = normalize_public_image_url((body.warehouse_signature_url or body.warehouse_signature or "").strip()) or ""
        cr = normalize_public_image_url((body.carrier_signature_url or body.carrier_signature or "").strip()) or ""
        if len(wh) < 50 or len(cr) < 50:
            raise HTTPException(400, "请完成收货方与送货方签字后再提交")
        order.receive_signatures_json = {
            "warehouse_signature": wh,
            "carrier_signature": cr,
            "warehouse_signature_url": normalize_public_image_url(body.warehouse_signature_url) or None,
            "carrier_signature_url": normalize_public_image_url(body.carrier_signature_url) or None,
            "recorded_at": datetime.utcnow().isoformat() + "Z",
        }
    else:
        wh = normalize_public_image_url((body.warehouse_signature_url or body.warehouse_signature or "").strip()) or ""
        cr = normalize_public_image_url((body.carrier_signature_url or body.carrier_signature or "").strip()) or ""
        if wh or cr:
            order.receive_signatures_json = {
                "warehouse_signature": wh or None,
                "carrier_signature": cr or None,
                "warehouse_signature_url": normalize_public_image_url(body.warehouse_signature_url) or None,
                "carrier_signature_url": normalize_public_image_url(body.carrier_signature_url) or None,
                "recorded_at": datetime.utcnow().isoformat() + "Z",
            }

    iot_weight = sum(float(i.get("quantity", 0)) for i in (order.items_json or []))
    if use_receiving:
        rows = (
            await db.scalars(select(OrderReceivingLine).where(OrderReceivingLine.order_id == order.id))
        ).all()
        iot_weight = sum(float(r.confirmed_kg or 0) for r in rows)

    old_status = order.status
    ensure_order_transition(old_status, "收货确认")
    order.status = "收货确认"
    order.version += 1
    order.updated_at = datetime.utcnow()
    db.add(
        IoTData(
            device_type="scale",
            device_id=f"SCALE-{order.id}",
            payload_json={
                "weight": iot_weight,
                "product_name": "混合物资",
                "unit": "kg",
                "receiving_snapshot": use_receiving,
            },
            recorded_at=datetime.utcnow(),
        )
    )
    await create_returns_after_receive(db, order, user.id, idem_key)
    await create_receive_bills(db, order)
    await create_receive_billing_statements(db, order)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="bill_create_on_receive",
        category="bill",
        object_type="order",
        object_id=order.id,
        detail="收货后自动生成客户（食堂）与配送商、配送商与供货商/厂家账单",
        **_audit_meta(request),
    )
    if idem_key:
        db.add(
            IdempotencyKey(
                idempotency_key=idem_key,
                scope="order_receive",
                resource_id=order.id,
            )
        )
    await _log_order_transition(db, order, old_status, order.status, user.id, request)
    await _mark_abnormal_if_quality_missing(
        db,
        order,
        actor_user_id=int(user.id),
        new_status=order.status,
        request=request,
    )
    await db.commit()
    await _emit_order_status_change(db, order, old_status, order.status)
    await _notify_order_targets(
        db,
        order,
        title="账单已生成（客户（食堂）-配送商）",
        content=f"订单 {order.order_no} 已生成客户（食堂）与配送商账单，请及时对账。",
        to_client=True,
        to_delivery=True,
        event_type="bill_created",
        client_route="/client/bills",
        delivery_route="/delivery/bills",
    )
    await _notify_order_targets(
        db,
        order,
        title="供货商/厂家应收已入账",
        content=f"订单 {order.order_no} 已生成账单（客户（食堂）应付配送商；配送商应付供货商/厂家）。",
        to_delivery=True,
        to_suppliers=True,
        event_type="bill_created",
        delivery_route="/delivery/bills",
        supplier_route="/supplier/bills",
        factory_route="/factory/bills",
    )
    await db.commit()
    return {"message": "收货完成并已入账"}


@router.post("/{order_id}/review")
async def review_order(
    order_id: int,
    payload: ReviewIn,
    request: Request,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    row = await db.scalar(select(OrderReview).where(OrderReview.order_id == order_id))
    if row:
        row.rating = payload.rating
        row.comment = payload.comment
    else:
        db.add(
            OrderReview(
                order_id=order_id, client_id=user.id, rating=payload.rating, comment=payload.comment
            )
        )
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="order_review",
        category="order",
        object_type="order",
        object_id=order_id,
        detail=f"评分={payload.rating}",
        **_audit_meta(request),
    )
    await db.commit()
    return {"message": "评价成功"}


@router.post("/{order_id}/settle")
async def settle_order(
    order_id: int,
    request: Request,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    cid = await _resolve_client_canteen_id(db, user, request)
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.client_id == user.id,
            Order.canteen_id == cid,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    idem_key = request.headers.get("Idempotency-Key")
    if idem_key:
        existing = await db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.idempotency_key == idem_key,
                IdempotencyKey.scope == "order_settle",
                IdempotencyKey.resource_id == order.id,
            )
        )
        if existing:
            return order
    old_status = order.status
    ensure_order_transition(old_status, "已结算")
    order.status = "已结算"
    order.version += 1
    order.updated_at = datetime.utcnow()
    bills = (await db.scalars(select(Bill).where(Bill.order_id == order_id))).all()
    for bill in bills:
        bill.status = "已结算"
    statements = (
        await db.scalars(
            select(BillingStatement).where(
                BillingStatement.owner_user_id.in_([order.client_id, order.delivery_id]),
                BillingStatement.counterparty_user_id.in_([order.client_id, order.delivery_id]),
            )
        )
    ).all()
    settled_statement_count = 0
    for statement in statements:
        if not _statement_contains_order(statement, int(order.id)):
            continue
        statement.settled_amount = statement.amount
        statement.confirmed_amount = statement.amount
        statement.status = "已结清"
        statement.confirmed_at = statement.confirmed_at or datetime.utcnow()
        settled_statement_count += 1
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="bill_settle",
        category="bill",
        object_type="order",
        object_id=order.id,
        detail=f"订单账单结算条数={len(bills)}，账期账单结算条数={settled_statement_count}",
        **_audit_meta(request),
    )
    if idem_key:
        db.add(
            IdempotencyKey(
                idempotency_key=idem_key,
                scope="order_settle",
                resource_id=order.id,
            )
        )
    await _log_order_transition(db, order, old_status, order.status, user.id, request)
    await _mark_abnormal_if_quality_missing(
        db,
        order,
        actor_user_id=int(user.id),
        new_status=order.status,
        request=request,
    )
    await db.commit()
    await _emit_order_status_change(db, order, old_status, order.status)
    await _notify_order_targets(
        db,
        order,
        title="账单已结算（客户（食堂）-配送商）",
        content=f"订单 {order.order_no} 客户（食堂）与配送商账单已结算。",
        to_client=True,
        to_delivery=True,
        event_type="bill_settled",
        client_route="/client/bills",
        delivery_route="/delivery/bills",
    )
    await _notify_order_targets(
        db,
        order,
        title="供货商/厂家应收已结算",
        content=f"订单 {order.order_no} 相关账单已结算（客户（食堂）与配送商、配送商与供货商/厂家）。",
        to_delivery=True,
        to_suppliers=True,
        event_type="bill_settled",
        delivery_route="/delivery/bills",
        supplier_route="/supplier/bills",
        factory_route="/factory/bills",
    )
    await db.commit()
    return order
