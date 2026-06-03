from datetime import date, datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db, seed_data
from dependencies import require_role
from models import (
    Alert,
    AuditLog,
    Bill,
    BillingStatement,
    ClientCanteen,
    Contract,
    Delivery,
    DeliveryDispatchItem,
    DeliveryDispatchStop,
    DeliveryDispatchTrip,
    DeliveryDevice,
    DeliverySortScanRecord,
    DeliveryVehicle,
    DeliveryVehicleDeviceBinding,
    IdempotencyKey,
    IoTData,
    Notification,
    Order,
    OrderAbnormal,
    OrderItemAllocation,
    OrderItemStatusLog,
    OrderReceivingLine,
    OrderReview,
    OrderReturn,
    OrderReturnLine,
    OrderStatusLog,
    OutboxEvent,
    Product,
    QualityReport,
    SortRecord,
    SupplierProductQuote,
    Tender,
    TenderBid,
    Ticket,
    User,
)
from services.audit_service import write_audit_log
from services.bill_service import create_receive_bills
from services.billing_service import create_receive_billing_statements
from services.event_bus import publish_monitor_event, publish_role_order_update
from services.notification_service import push_notification
from services.order_detail_aggregator import _signed_contract_for_order_on_date
from services.order_quality_missing import missing_quality_allocations
from services.order_return_service import create_returns_after_receive
from services.outbox_service import add_outbox_event
from services.ticket_service import (
    close_delivery_overdue_alert_if_delivered,
    close_delivery_overdue_ticket_if_delivered,
    ensure_quality_missing_ticket,
)

router = APIRouter(prefix="/demo", tags=["demo"])


def _ensure_demo_mode():
    if not settings.demo_mode:
        raise HTTPException(403, "仅演示模式可用")


@router.get("/client-accounts")
async def demo_client_accounts(
    db: AsyncSession = Depends(get_db),
):
    """演示控制台用：返回库中全部启用状态的采购方账号及下属食堂（无需登录；仅 demo_mode 放行）。"""
    _ensure_demo_mode()
    rows = (
        await db.scalars(
            select(User)
            .where(User.role == "client", User.status == "active")
            .order_by(User.username.asc())
        )
    ).all()
    if not rows:
        return []
    uids = [int(r.id) for r in rows]
    c_rows = (
        await db.scalars(
            select(ClientCanteen)
            .where(ClientCanteen.school_client_id.in_(uids))
            .order_by(ClientCanteen.school_client_id.asc(), ClientCanteen.sort_order.asc(), ClientCanteen.id.asc())
        )
    ).all()
    by_school: dict[int, list[dict]] = {}
    for c in c_rows:
        sid = int(c.school_client_id)
        by_school.setdefault(sid, []).append(
            {
                "id": int(c.id),
                "name": (c.name or "").strip(),
                "status": str(c.status),
            }
        )
    out = []
    for r in rows:
        lng = float(r.lng) if r.lng is not None else None
        lat = float(r.lat) if r.lat is not None else None
        rid = int(r.id)
        out.append(
            {
                "username": r.username,
                "company_name": (r.company_name or "").strip(),
                "address": (r.address or "").strip(),
                "lng": lng,
                "lat": lat,
                "canteens": by_school.get(rid, []),
            }
        )
    return out


@router.get("/supplier-accounts")
async def demo_supplier_accounts(
    db: AsyncSession = Depends(get_db),
):
    """演示控制台用：全部启用供货商（含绑定 delivery_id，便于核对单配送商模型）；仅 demo_mode。"""
    _ensure_demo_mode()
    rows = (
        await db.scalars(
            select(User)
            .where(User.role == "supplier", User.status == "active")
            .order_by(User.username.asc())
        )
    ).all()
    out = []
    for r in rows:
        out.append(
            {
                "username": r.username,
                "company_name": (r.company_name or "").strip(),
                "supplier_delivery_id": int(r.supplier_delivery_id) if r.supplier_delivery_id is not None else None,
            }
        )
    return out


class SupplierShipBulkIn(BaseModel):
    """演示用：指定供货商对其在这些订单下的分包行一键标「已出库」（跳过打印门禁，等同供货商端发货结果）。"""

    order_ids: list[int] = Field(..., min_length=1)
    supplier_username: str = Field(..., min_length=1, description="供货商登录名，如 supplier001")


class OrderIdsIn(BaseModel):
    order_ids: list[int] = Field(..., min_length=1)


class DispatchDemoPrepareIn(BaseModel):
    delivery_username: str = "delivery001"
    planning_date: date | None = None
    order_ids: list[int] = Field(default_factory=list)
    target_order_count: int = Field(default=6, ge=1, le=30)
    create_if_missing: bool = True
    mark_shipped: bool = True
    mark_sorted: bool = True


def _empty_delete_summary(requested_orders: int = 0) -> dict[str, int]:
    return {
        "requested_orders": requested_orders,
        "matched_orders": 0,
        "deleted_orders": 0,
        "deleted_dispatch_trips": 0,
        "deleted_dispatch_stops": 0,
        "deleted_dispatch_items": 0,
        "deleted_sort_records": 0,
        "deleted_sort_scan_records": 0,
        "deleted_returns": 0,
        "deleted_return_lines": 0,
        "deleted_receiving_lines": 0,
        "deleted_allocations": 0,
        "deleted_allocation_status_logs": 0,
        "deleted_order_status_logs": 0,
        "deleted_quality_reports": 0,
        "deleted_iot_data": 0,
        "deleted_deliveries": 0,
        "deleted_bills": 0,
        "deleted_statements": 0,
        "deleted_tickets": 0,
        "deleted_abnormals": 0,
        "deleted_reviews": 0,
        "deleted_alerts": 0,
        "deleted_notifications": 0,
        "deleted_audit_logs": 0,
        "deleted_idempotency_keys": 0,
        "deleted_outbox_events": 0,
    }


def _json_order_ids(value: Any) -> set[int]:
    out: set[int] = set()

    def visit(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                visit(v, str(k))
            return
        if isinstance(node, list):
            for item in node:
                visit(item, key)
            return
        if key in {"order_id", "order_ids", "source_order_id"}:
            try:
                n = int(str(node).strip())
                if n > 0:
                    out.add(n)
            except (TypeError, ValueError):
                return

    visit(value)
    return out


def _json_mentions_orders(value: Any, order_ids: set[int], order_nos: set[str]) -> bool:
    id_texts = {str(i) for i in order_ids}

    def scalar_hit(node: Any) -> bool:
        if isinstance(node, bool) or node is None:
            return False
        if isinstance(node, (int, float)):
            try:
                return int(node) in order_ids
            except (TypeError, ValueError):
                return False
        text = str(node)
        return text in id_texts or any(no and no in text for no in order_nos)

    def visit(node: Any) -> bool:
        if isinstance(node, dict):
            return any(scalar_hit(k) or visit(v) for k, v in node.items())
        if isinstance(node, list):
            return any(visit(item) for item in node)
        return scalar_hit(node)

    return visit(value)


async def _delete_orders_cascade(db: AsyncSession, order_ids: list[int]) -> dict[str, int]:
    ids = sorted({int(i) for i in order_ids if int(i) > 0})
    if not ids:
        raise HTTPException(400, "order_ids 非法")
    summary = _empty_delete_summary(len(ids))

    orders = (await db.scalars(select(Order).where(Order.id.in_(ids)))).all()
    matched_ids = sorted({int(o.id) for o in orders})
    if not matched_ids:
        return summary
    id_set = set(matched_ids)
    order_nos = {str(o.order_no).strip() for o in orders if str(o.order_no or "").strip()}
    summary["matched_orders"] = len(matched_ids)

    async def delete_count(stmt) -> int:
        res = await db.execute(stmt)
        return int(res.rowcount or 0)

    alloc_ids = sorted(
        {
            int(a)
            for a in (
                await db.scalars(
                    select(OrderItemAllocation.id).where(OrderItemAllocation.order_id.in_(matched_ids))
                )
            ).all()
        }
    )

    stop_trip_ids = (
        await db.scalars(select(DeliveryDispatchStop.trip_id).where(DeliveryDispatchStop.order_id.in_(matched_ids)))
    ).all()
    item_trip_ids = (
        await db.scalars(select(DeliveryDispatchItem.trip_id).where(DeliveryDispatchItem.order_id.in_(matched_ids)))
    ).all()
    dispatch_trip_ids = sorted({int(x) for x in [*stop_trip_ids, *item_trip_ids] if x})

    return_ids = sorted(
        {
            int(x)
            for x in (
                await db.scalars(select(OrderReturn.id).where(OrderReturn.order_id.in_(matched_ids)))
            ).all()
        }
    )

    direct_ticket_ids = {
        int(x)
        for x in (await db.scalars(select(Ticket.id).where(Ticket.order_id.in_(matched_ids)))).all()
    }

    statements = (await db.scalars(select(BillingStatement))).all()
    statement_ids = sorted(
        {
            int(s.id)
            for s in statements
            if _json_order_ids(s.source_snapshot_json or {}) & id_set
            or _json_mentions_orders(s.source_snapshot_json or {}, id_set, order_nos)
        }
    )
    statement_ticket_ids = set()
    if statement_ids:
        statement_ticket_ids = {
            int(x)
            for x in (
                await db.scalars(select(Ticket.id).where(Ticket.billing_statement_id.in_(statement_ids)))
            ).all()
        }
    ticket_ids = sorted(direct_ticket_ids | statement_ticket_ids)

    alerts = (await db.scalars(select(Alert))).all()
    alert_ids = sorted(
        {
            int(a.id)
            for a in alerts
            if _json_mentions_orders(a.payload_json or {}, id_set, order_nos)
            or any(no and no in str(a.description or "") for no in order_nos)
        }
    )

    outbox_events = (await db.scalars(select(OutboxEvent))).all()
    outbox_ids = sorted(
        {
            int(e.id)
            for e in outbox_events
            if _json_mentions_orders(e.payload_json or {}, id_set, order_nos)
            or (dispatch_trip_ids and _json_mentions_orders(e.payload_json or {}, set(dispatch_trip_ids), set()))
            or (statement_ids and _json_mentions_orders(e.payload_json or {}, set(statement_ids), set()))
            or (ticket_ids and _json_mentions_orders(e.payload_json or {}, set(ticket_ids), set()))
        }
    )

    if alloc_ids:
        summary["deleted_sort_scan_records"] += await delete_count(
            delete(DeliverySortScanRecord).where(DeliverySortScanRecord.allocation_id.in_(alloc_ids))
        )
    summary["deleted_sort_scan_records"] += await delete_count(
        delete(DeliverySortScanRecord).where(DeliverySortScanRecord.order_id.in_(matched_ids))
    )

    if dispatch_trip_ids:
        summary["deleted_notifications"] += await delete_count(
            delete(Notification).where(
                Notification.object_type == "delivery_dispatch_trip",
                Notification.object_id.in_(dispatch_trip_ids),
            )
        )
        summary["deleted_audit_logs"] += await delete_count(
            delete(AuditLog).where(
                AuditLog.object_type == "delivery_dispatch_trip",
                AuditLog.object_id.in_(dispatch_trip_ids),
            )
        )
        summary["deleted_dispatch_items"] += await delete_count(
            delete(DeliveryDispatchItem).where(DeliveryDispatchItem.trip_id.in_(dispatch_trip_ids))
        )
        summary["deleted_dispatch_stops"] += await delete_count(
            delete(DeliveryDispatchStop).where(DeliveryDispatchStop.trip_id.in_(dispatch_trip_ids))
        )
        summary["deleted_dispatch_trips"] += await delete_count(
            delete(DeliveryDispatchTrip).where(DeliveryDispatchTrip.id.in_(dispatch_trip_ids))
        )

    if return_ids:
        summary["deleted_return_lines"] += await delete_count(
            delete(OrderReturnLine).where(OrderReturnLine.order_return_id.in_(return_ids))
        )
        summary["deleted_returns"] += await delete_count(delete(OrderReturn).where(OrderReturn.id.in_(return_ids)))

    summary["deleted_receiving_lines"] += await delete_count(
        delete(OrderReceivingLine).where(OrderReceivingLine.order_id.in_(matched_ids))
    )
    if alloc_ids:
        summary["deleted_allocation_status_logs"] += await delete_count(
            delete(OrderItemStatusLog).where(OrderItemStatusLog.allocation_id.in_(alloc_ids))
        )
        summary["deleted_audit_logs"] += await delete_count(
            delete(AuditLog).where(AuditLog.object_type == "allocation", AuditLog.object_id.in_(alloc_ids))
        )
        summary["deleted_notifications"] += await delete_count(
            delete(Notification).where(Notification.object_type == "allocation", Notification.object_id.in_(alloc_ids))
        )
    summary["deleted_allocations"] += await delete_count(
        delete(OrderItemAllocation).where(OrderItemAllocation.order_id.in_(matched_ids))
    )

    summary["deleted_order_status_logs"] += await delete_count(
        delete(OrderStatusLog).where(OrderStatusLog.order_id.in_(matched_ids))
    )
    summary["deleted_quality_reports"] += await delete_count(
        delete(QualityReport).where(QualityReport.order_id.in_(matched_ids))
    )
    summary["deleted_sort_records"] += await delete_count(delete(SortRecord).where(SortRecord.order_id.in_(matched_ids)))
    # 收货确认时按 device_id=SCALE-<order_id> 写入的称重 IoT（真实 receive_order 与演示 receive 同口径），无 order 外键，按设备号匹配清理
    summary["deleted_iot_data"] += await delete_count(
        delete(IoTData).where(IoTData.device_id.in_([f"SCALE-{i}" for i in matched_ids]))
    )
    summary["deleted_deliveries"] += await delete_count(delete(Delivery).where(Delivery.order_id.in_(matched_ids)))
    summary["deleted_bills"] += await delete_count(delete(Bill).where(Bill.order_id.in_(matched_ids)))

    if ticket_ids:
        summary["deleted_notifications"] += await delete_count(
            delete(Notification).where(Notification.object_type == "ticket", Notification.object_id.in_(ticket_ids))
        )
        summary["deleted_audit_logs"] += await delete_count(
            delete(AuditLog).where(AuditLog.object_type == "ticket", AuditLog.object_id.in_(ticket_ids))
        )
        summary["deleted_tickets"] += await delete_count(delete(Ticket).where(Ticket.id.in_(ticket_ids)))

    if statement_ids:
        summary["deleted_notifications"] += await delete_count(
            delete(Notification).where(
                Notification.object_type == "billing_statement",
                Notification.object_id.in_(statement_ids),
            )
        )
        summary["deleted_audit_logs"] += await delete_count(
            delete(AuditLog).where(
                AuditLog.object_type == "billing_statement",
                AuditLog.object_id.in_(statement_ids),
            )
        )
        summary["deleted_statements"] += await delete_count(
            delete(BillingStatement).where(BillingStatement.id.in_(statement_ids))
        )

    summary["deleted_abnormals"] += await delete_count(
        delete(OrderAbnormal).where(OrderAbnormal.order_id.in_(matched_ids))
    )
    summary["deleted_reviews"] += await delete_count(delete(OrderReview).where(OrderReview.order_id.in_(matched_ids)))

    if alert_ids:
        summary["deleted_notifications"] += await delete_count(
            delete(Notification).where(Notification.object_type == "alert", Notification.object_id.in_(alert_ids))
        )
        summary["deleted_audit_logs"] += await delete_count(
            delete(AuditLog).where(AuditLog.object_type == "alert", AuditLog.object_id.in_(alert_ids))
        )
        summary["deleted_alerts"] += await delete_count(delete(Alert).where(Alert.id.in_(alert_ids)))

    summary["deleted_notifications"] += await delete_count(
        delete(Notification).where(Notification.object_type == "order", Notification.object_id.in_(matched_ids))
    )
    summary["deleted_audit_logs"] += await delete_count(
        delete(AuditLog).where(AuditLog.object_type == "order", AuditLog.object_id.in_(matched_ids))
    )
    summary["deleted_idempotency_keys"] += await delete_count(
        delete(IdempotencyKey).where(IdempotencyKey.resource_id.in_(matched_ids))
    )
    if outbox_ids:
        summary["deleted_outbox_events"] += await delete_count(delete(OutboxEvent).where(OutboxEvent.id.in_(outbox_ids)))

    summary["deleted_orders"] += await delete_count(delete(Order).where(Order.id.in_(matched_ids)))
    return summary


async def _ensure_dispatch_demo_vehicles(db: AsyncSession, delivery_id: int) -> list[DeliveryVehicle]:
    specs = [
        ("京A12345", "4.2米冷链厢货", "张师傅", 2200, 12, 116.3978, 39.9094),
        ("京B67890", "新能源厢货", "李师傅", 1800, 10, 116.4196, 39.9289),
        ("京C24680", "轻型厢货", "王师傅", 1500, 8, 116.3723, 39.8898),
    ]
    now = datetime.utcnow()
    now_ms = int(now.timestamp() * 1000)
    out: list[DeliveryVehicle] = []
    for vehicle_no, model, driver_name, weight, volume, lng, lat in specs:
        row = await db.scalar(
            select(DeliveryVehicle).where(
                DeliveryVehicle.delivery_id == delivery_id,
                DeliveryVehicle.vehicle_no == vehicle_no,
            )
        )
        if not row:
            row = DeliveryVehicle(
                delivery_id=delivery_id,
                vehicle_no=vehicle_no,
                vehicle_model=model,
                driver_name=driver_name,
                capacity_weight_kg=weight,
                capacity_volume_m3=volume,
                status="active",
            )
            db.add(row)
            await db.flush()
        else:
            row.vehicle_model = row.vehicle_model or model
            row.driver_name = row.driver_name or driver_name
            row.capacity_weight_kg = row.capacity_weight_kg or weight
            row.capacity_volume_m3 = row.capacity_volume_m3 or volume
            row.status = "active"
        device_code = f"BD-DEMO-{delivery_id}-{vehicle_no}"
        raw_payload = {
            "jingdu": lng,
            "weidu": lat,
            "ljingdu": lng,
            "lweidu": lat,
            "speed": 0,
            "course": "",
            "heart_time": now_ms,
            "server_time": now_ms,
            "datetime": now_ms,
            "reported_at": f"{now.isoformat()}Z",
            "status": "online",
            "source": "demo_dispatch_prepare",
        }
        device = await db.scalar(
            select(DeliveryDevice).where(
                DeliveryDevice.vendor == "beidou",
                DeliveryDevice.device_code == device_code,
                DeliveryDevice.channel_no == 0,
            )
        )
        if not device:
            device = DeliveryDevice(
                delivery_id=delivery_id,
                device_type="beidou",
                vendor="beidou",
                device_code=device_code,
                device_name=f"{vehicle_no} 演示北斗",
                channel_no=0,
                status="active",
                raw_payload_json=raw_payload,
            )
            db.add(device)
            await db.flush()
        else:
            device.delivery_id = delivery_id
            device.device_type = "beidou"
            device.device_name = device.device_name or f"{vehicle_no} 演示北斗"
            device.status = "active"
            device.raw_payload_json = raw_payload
        binding = await db.scalar(
            select(DeliveryVehicleDeviceBinding).where(DeliveryVehicleDeviceBinding.device_id == int(device.id))
        )
        if not binding:
            db.add(
                DeliveryVehicleDeviceBinding(
                    delivery_id=delivery_id,
                    vehicle_id=int(row.id),
                    device_id=int(device.id),
                )
            )
        elif int(binding.vehicle_id) == int(row.id):
            binding.delivery_id = delivery_id
        out.append(row)
    return out


async def _dispatch_demo_suppliers(db: AsyncSession, delivery_id: int) -> list[User]:
    rows = (
        await db.scalars(
            select(User)
            .where(
                User.role.in_(["supplier", "factory"]),
                User.status == "active",
                User.supplier_delivery_id == delivery_id,
            )
            .order_by(User.id.asc())
        )
    ).all()
    if rows:
        return rows
    sup = await db.scalar(select(User).where(User.username == "supplier001", User.role == "supplier"))
    if not sup:
        raise HTTPException(500, "演示供货商 supplier001 不存在，请先初始化演示数据")
    sup.supplier_delivery_id = delivery_id
    sup.status = "active"
    return [sup]


async def _dispatch_demo_product_pool(db: AsyncSession, limit: int = 24) -> list[Product]:
    rows = (
        await db.scalars(
            select(Product)
            .where(Product.is_deleted.is_(False), Product.status == "active")
            .order_by(Product.id.asc())
            .limit(limit)
        )
    ).all()
    if not rows:
        raise HTTPException(500, "演示商品池为空，请先初始化商品数据")
    return rows


async def _dispatch_demo_canteen(db: AsyncSession, client_id: int) -> ClientCanteen | None:
    return await db.scalar(
        select(ClientCanteen)
        .where(ClientCanteen.school_client_id == client_id, ClientCanteen.status == "active")
        .order_by(ClientCanteen.sort_order.asc(), ClientCanteen.id.asc())
        .limit(1)
    )


def _order_item_payload(
    product: Product,
    quantity: float,
    *,
    rate_map: dict[int, float] | None = None,
    fallback_rate: float = 0.18,
) -> tuple[dict, dict, float]:
    # 客户价 = 指导价 ×(1+一级分类上浮)，与真实下单 orders.py 口径一致；
    # 上浮率优先取合约对应一级分类费率，缺失则用 fallback_rate（保证非零，避免实付较指导价算成 0%）。
    reference_price = float(product.reference_price or 10.0)
    rate = float((rate_map or {}).get(int(product.category1_id or 0), fallback_rate))
    if rate <= 0:
        rate = fallback_rate
    unit_price = round(reference_price * (1.0 + rate), 2)
    item = {"product_id": int(product.id), "quantity": quantity, "unit_price": unit_price}
    snap = {
        "product_id": int(product.id),
        "product_name": product.name,
        "unit": product.unit or "kg",
        "reference_price": reference_price,
        "category1_id": product.category1_id,
        "category2_id": product.category2_id,
        "order_quantity": quantity,
        "order_unit_price": unit_price,
        # 实付较指导价反推依赖该字段，真实下单也会写入；缺它会被当成 0% 上浮
        "category_float_rate": rate,
        "standard_type": product.standard_type or "standard",
    }
    return item, snap, round(unit_price * quantity, 2)


async def _create_dispatch_demo_orders(
    db: AsyncSession,
    *,
    delivery_id: int,
    planning_date: date,
    count: int,
    products: list[Product],
) -> list[Order]:
    clients = (
        await db.scalars(
            select(User)
            .where(User.role == "client", User.status == "active")
            .order_by(User.username.asc())
            .limit(max(count, 6))
        )
    ).all()
    if not clients:
        raise HTTPException(500, "演示客户为空，请先初始化演示数据")
    slots = ["06:00-07:00", "07:00-08:00", "08:00-09:00", "09:00-10:00"]
    created: list[Order] = []
    for idx in range(count):
        client = clients[idx % len(clients)]
        canteen = await _dispatch_demo_canteen(db, int(client.id))
        # 取该单适用合约的一级分类上浮率，使 demo 客户价/快照费率与详情页「合约与上浮」自洽
        contract = await _signed_contract_for_order_on_date(
            db, int(client.id), delivery_id, planning_date
        )
        rate_map: dict[int, float] = {}
        fallback_rate = 0.18
        if contract is not None:
            for r in contract.category_rates_json or []:
                if r.get("category_id") is not None:
                    try:
                        rate_map[int(r["category_id"])] = float(r.get("float_rate", 0))
                    except (TypeError, ValueError):
                        continue
            if float(contract.price_float_rate or 0) > 0:
                fallback_rate = float(contract.price_float_rate)
        p1 = products[(idx * 2) % len(products)]
        p2 = products[(idx * 2 + 1) % len(products)]
        i1, s1, t1 = _order_item_payload(p1, 3 + (idx % 4), rate_map=rate_map, fallback_rate=fallback_rate)
        i2, s2, t2 = _order_item_payload(p2, 2 + (idx % 3), rate_map=rate_map, fallback_rate=fallback_rate)
        order_no = f"ODDEMO{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%m%d%H%M%S')}{uuid4().hex[:4].upper()}"
        address = (canteen.address if canteen and canteen.address else client.address) or f"{client.company_name or client.username}演示点"
        order = Order(
            order_no=order_no,
            client_id=int(client.id),
            canteen_id=int(canteen.id) if canteen else None,
            delivery_id=delivery_id,
            supplier_id=None,
            items_json=[i1, i2],
            items_snapshot_json=[s1, s2],
            total_amount=round(t1 + t2, 2),
            total_volume_m3=round(0.06 + idx * 0.01, 4),
            total_weight_kg=round(18 + idx * 2.5, 3),
            delivery_address=address,
            delivery_lng=client.lng,
            delivery_lat=client.lat,
            expected_delivery_date=planning_date,
            expected_delivery_slot=slots[idx % len(slots)],
            service_duration_min=25,
            status="下单",
            has_abnormal=False,
        )
        db.add(order)
        await db.flush()
        created.append(order)
    return created


# —— 演示链路副作用复刻：与 routers/orders.py 的私有薄包装逐行对应，调用同一批 services ——
# （不抽取 orders.py 私有函数以免波及真实端点 14+ 处热点调用；这里复刻等价逻辑、副作用一致）


async def _demo_supplier_user_ids(db: AsyncSession, order: Order) -> list[int]:
    rows = (
        await db.scalars(
            select(OrderItemAllocation.supplier_id).where(OrderItemAllocation.order_id == order.id).distinct()
        )
    ).all()
    return [int(i) for i in rows]


async def _demo_log_transition(db: AsyncSession, order: Order, old_status: str, new_status: str, actor_user_id: int):
    """= orders.py _log_order_transition：OrderStatusLog + 审计 + outbox（演示无 request meta）。"""
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


async def _demo_emit_status_change(db: AsyncSession, order: Order, old_status: str, new_status: str):
    """= orders.py _emit_order_status_change：监管事件总线 + 供货商/配送商角色 websocket 推送。"""
    if old_status == new_status:
        return
    await publish_monitor_event(
        "order_status_change",
        {"order_id": order.id, "order_no": order.order_no, "old_status": old_status, "new_status": new_status},
    )
    cid = int(order.canteen_id) if order.canteen_id is not None else None
    sup = await _demo_supplier_user_ids(db, order)
    if sup:
        await publish_role_order_update(
            "supplier", sup, order.id, order.order_no, new_status, f"订单状态变更为{new_status}", canteen_id=cid
        )
    await publish_role_order_update(
        "delivery", [order.delivery_id], order.id, order.order_no, new_status, f"订单状态变更为{new_status}", canteen_id=cid
    )


async def _demo_notify(
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
    """= orders.py _notify_order_targets：按角色写 Notification（push_notification 含 websocket 广播）。"""
    if to_client:
        await push_notification(
            db=db, role="client", event_type=event_type, title=title, content=content,
            route=client_route or f"/client/orders/{order.id}", object_type="order", object_id=order.id,
            target_user_ids=[order.client_id],
            canteen_id=int(order.canteen_id) if order.canteen_id is not None else None,
        )
    if to_delivery:
        await push_notification(
            db=db, role="delivery", event_type=event_type, title=title, content=content,
            route=delivery_route or f"/delivery/orders/{order.id}", object_type="order", object_id=order.id,
            target_user_ids=[order.delivery_id],
        )
    if to_suppliers:
        sup = await _demo_supplier_user_ids(db, order)
        if sup:
            users = (await db.scalars(select(User).where(User.id.in_(sup)))).all()
            role_groups: dict[str, list[int]] = {}
            for u in users:
                role_groups.setdefault(str(u.role or "supplier"), []).append(int(u.id))
            for role, ids in role_groups.items():
                route = factory_route if role == "factory" and factory_route else supplier_route
                await push_notification(
                    db=db, role=role, event_type=event_type, title=title, content=content,
                    route=route or f"/{role}/orders/{order.id}", object_type="order", object_id=order.id,
                    target_user_ids=ids,
                )


_DEMO_POST_SHIP_STATUSES = {"发货", "收货", "收货确认", "已结算"}


async def _demo_sync_abnormal(db: AsyncSession, order: Order, actor_user_id: int, *, trigger: str, new_status: str | None = None):
    """= orders.py _sync_abnormal_for_shipped_missing_quality：已出库分单缺质检 → 标异常 + 预警 + 工单。

    与真实端点的差异：同一订单已有 open 的 quality_missing 预警时不再重复插 Alert（每步去重，避免演示预警中心被同一单刷屏），工单仍按 upsert。
    """
    missing = await missing_quality_allocations(db, int(order.id), shipped_only=True)
    if not missing:
        return
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
        db=db, actor_user_id=actor_user_id, action="quality_missing_marked", category="quality",
        object_type="order", object_id=int(order.id),
        detail=(
            f"订单 {order.order_no}：{trigger}，仍有 {len(missing)} 条已出库分单缺失质检报告"
            + (f"（订单状态 {new_status}）" if new_status else "")
        ),
        after_json=payload,
    )
    already_open = await db.scalar(
        select(Alert.id).where(
            Alert.type == "quality_missing", Alert.status == "open",
            Alert.description.like(f"订单 {order.order_no}：%"),
        ).limit(1)
    )
    if not already_open:
        db.add(
            Alert(
                level="medium", type="quality_missing",
                description=f"订单 {order.order_no}：已出库分单缺质检（{len(missing)} 条），触发：{trigger}",
                status="open", payload_json=payload,
            )
        )
    await ensure_quality_missing_ticket(db, order, actor_user_id, missing_count=len(missing))


async def _demo_mark_abnormal(db: AsyncSession, order: Order, actor_user_id: int, new_status: str):
    """= orders.py _mark_abnormal_if_quality_missing：状态推进到发货及以后时检查质检缺失。"""
    if str(new_status) not in _DEMO_POST_SHIP_STATUSES:
        return
    await _demo_sync_abnormal(db, order, actor_user_id, trigger="order_status", new_status=new_status)


async def _demo_after_ship(db: AsyncSession, order: Order, actor_user_id: int):
    """供货商发货后副作用（= ship_order 分单分支）：质检缺失同步 + 通知配送商。"""
    await _demo_sync_abnormal(db, order, actor_user_id, trigger="supplier_ship")
    allocs = (await db.scalars(select(OrderItemAllocation.status).where(OrderItemAllocation.order_id == order.id))).all()
    all_shipped = bool(allocs) and all(str(s) == "已出库" for s in allocs)
    await _demo_notify(
        db, order,
        title=f"订单 {order.order_no} {'分包侧已全部发货' if all_shipped else '有分包供货商发货'}",
        content="全部分包供货商已发货，配送商可确认取货。" if all_shipped else "仍有部分分包供货商未发货，暂不可确认取货。",
        to_delivery=True,
    )


async def _demo_allocate_orders(db: AsyncSession, orders: list[Order], now: datetime) -> dict:
    """演示一键配货：对「下单/配货」且尚无分单的订单建分单行（状态已分配）、订单→配货。

    复用 demo_prepare_dispatch 的分单口径（供货商轮询、报价成本价），但不涉及车辆/排线/分检。
    不同订单可能挂不同配送商，按 delivery_id 分组各自取演示供货商池。
    """
    from collections import defaultdict

    by_delivery: dict[int, list[Order]] = defaultdict(list)
    for o in orders:
        by_delivery[int(o.delivery_id)].append(o)

    allocated_order_ids: list[int] = []
    created_allocations = 0
    skipped: list[dict] = []

    for delivery_id, group in by_delivery.items():
        suppliers = await _dispatch_demo_suppliers(db, delivery_id)
        supplier_ids = [int(s.id) for s in suppliers]
        if not supplier_ids:
            for o in group:
                skipped.append({"order_id": int(o.id), "reason": "无可用演示供货商"})
            continue
        product_ids = sorted(
            {
                int(it.get("product_id") or 0)
                for o in group
                for it in (o.items_json or [])
                if int(it.get("product_id") or 0) > 0
            }
        )
        product_map = {
            int(p.id): p
            for p in (await db.scalars(select(Product).where(Product.id.in_(product_ids)))).all()
        } if product_ids else {}
        demo_quote_map: dict[tuple[int, int], float] = {}
        if supplier_ids and product_ids:
            for q in (
                await db.scalars(
                    select(SupplierProductQuote).where(
                        SupplierProductQuote.supplier_id.in_(supplier_ids),
                        SupplierProductQuote.product_id.in_(product_ids),
                    )
                )
            ).all():
                demo_quote_map[(int(q.supplier_id), int(q.product_id))] = float(q.quote_price or 0)
        # 每个商品仅可分给「对其有报价」的供货商，否则收货生成账单会被「未对该商品报价」拦截
        quoted_suppliers_by_pid: dict[int, list[int]] = defaultdict(list)
        for (sid, qpid) in demo_quote_map:
            quoted_suppliers_by_pid[qpid].append(sid)

        for order_idx, order in enumerate(group):
            if str(order.status) not in {"下单", "配货"}:
                skipped.append({"order_id": int(order.id), "reason": f"状态为{order.status}"})
                continue
            existing = await db.scalar(
                select(OrderItemAllocation.id).where(OrderItemAllocation.order_id == int(order.id)).limit(1)
            )
            if existing:
                skipped.append({"order_id": int(order.id), "reason": "已存在分单"})
                continue
            old_status = str(order.status)
            if old_status != "配货":
                order.status = "配货"
                order.version += 1
            order.updated_at = now
            order_supplier_ids: set[int] = set()
            batch_no = f"demo-allocate-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
            for line_no, item in enumerate(order.items_json or [], 1):
                pid = int(item.get("product_id") or 0)
                if pid <= 0:
                    continue
                product = product_map.get(pid)
                ref_price = float(getattr(product, "reference_price", None) or 10)
                # 指定厂家商品必须分给其对应厂家（否则收货生成账单时会被「指定厂家只能与对应厂家结算」拦截）
                designated_fid = (
                    int(getattr(product, "designated_factory_id", 0) or 0)
                    if product is not None and bool(getattr(product, "is_designated_factory", False))
                    else 0
                )
                if designated_fid > 0:
                    supplier_id = designated_fid
                    cost_price = ref_price
                else:
                    candidates = quoted_suppliers_by_pid.get(pid) or supplier_ids
                    supplier_id = candidates[(order_idx + line_no - 1) % len(candidates)]
                    cost_price = demo_quote_map.get((supplier_id, pid)) or ref_price
                allocation = OrderItemAllocation(
                    order_id=int(order.id),
                    delivery_id=delivery_id,
                    supplier_id=supplier_id,
                    line_no=line_no,
                    product_id=pid,
                    quantity=round(float(item.get("quantity") or 1), 3),
                    unit_price=round(float(cost_price), 2),
                    allocation_batch_no=batch_no,
                    status="已分配",
                    created_by=delivery_id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(allocation)
                await db.flush()
                order_supplier_ids.add(int(supplier_id))
                db.add(
                    OrderItemStatusLog(
                        allocation_id=int(allocation.id),
                        old_status="待确认",
                        new_status="已分配",
                        operator_id=delivery_id,
                        note="演示一键配货",
                    )
                )
                created_allocations += 1
            # 副作用（= smart_split_commit）：状态日志/审计/outbox + 监管事件 + 通知被分到的供货商
            if old_status != "配货":
                await _demo_log_transition(db, order, old_status, "配货", delivery_id)
                await _demo_emit_status_change(db, order, old_status, "配货")
            if order_supplier_ids:
                users = (await db.scalars(select(User).where(User.id.in_(list(order_supplier_ids))))).all()
                role_groups: dict[str, list[int]] = {}
                for u in users:
                    role_groups.setdefault(str(u.role or "supplier"), []).append(int(u.id))
                for role, ids in role_groups.items():
                    await push_notification(
                        db=db, role=role, event_type="order_split", title="新的供货分单",
                        content=f"订单 {order.order_no} 已分单，请及时备货发货。",
                        route=f"/{role}/orders/{int(order.id)}", object_type="order", object_id=int(order.id),
                        target_user_ids=ids,
                    )
            allocated_order_ids.append(int(order.id))

    return {
        "allocated_order_ids": allocated_order_ids,
        "allocations_created": created_allocations,
        "skipped": skipped,
    }


@router.post("/orders/allocate")
async def demo_allocate_orders(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """演示：对一批订单一键配货（智能分单的简化版），建分单行并将订单推进到「配货」。"""
    _ensure_demo_mode()
    ids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not ids:
        raise HTTPException(400, "order_ids 非法")
    orders = (await db.scalars(select(Order).where(Order.id.in_(ids)))).all()
    now = datetime.utcnow()
    result = await _demo_allocate_orders(db, orders, now)
    await db.commit()
    return {"message": "ok", "orders_allocated": len(result["allocated_order_ids"]), **result}


@router.post("/orders/pickup")
async def demo_pickup_orders(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """演示：配送商一键取货（跳过分检/排线发车门禁）。配货且分单全部已出库 → 发货，并写运输中的配送记录。"""
    _ensure_demo_mode()
    ids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not ids:
        raise HTTPException(400, "order_ids 非法")
    orders = (await db.scalars(select(Order).where(Order.id.in_(ids)))).all()
    now = datetime.utcnow()
    advanced: list[int] = []
    skipped: list[dict] = []
    for order in orders:
        if str(order.status) != "配货":
            skipped.append({"order_id": int(order.id), "reason": f"状态为{order.status}"})
            continue
        allocs = (
            await db.scalars(select(OrderItemAllocation).where(OrderItemAllocation.order_id == int(order.id)))
        ).all()
        if allocs and not all(str(a.status) == "已出库" for a in allocs):
            skipped.append({"order_id": int(order.id), "reason": "仍有分单未发货（已出库）"})
            continue
        old_status = str(order.status)
        order.status = "发货"
        order.version += 1
        order.updated_at = now
        await _demo_log_transition(db, order, old_status, "发货", int(order.delivery_id))
        delivery = await db.scalar(select(Delivery).where(Delivery.order_id == int(order.id)))
        if not delivery:
            db.add(
                Delivery(
                    order_id=int(order.id),
                    driver_name="演示司机",
                    vehicle_no="演示车",
                    route_json=[],
                    departed_at=now,
                    status="运输中",
                )
            )
        else:
            delivery.departed_at = now
            delivery.status = "运输中"
        # 副作用（= pickup_order）：取货审计 + 监管事件 + 质检缺失 + 配送中通知
        await write_audit_log(
            db=db, actor_user_id=int(order.delivery_id), action="order_pickup_confirm",
            category="order", object_type="order", object_id=int(order.id),
            detail=f"确认取货 {order.order_no}",
        )
        await _demo_emit_status_change(db, order, old_status, "发货")
        await _demo_mark_abnormal(db, order, int(order.delivery_id), "发货")
        await _demo_notify(
            db, order, title=f"订单 {order.order_no} 配送中",
            content="配送商已确认取货，订单进入配送中。",
            to_client=True, to_delivery=True, to_suppliers=True,
        )
        advanced.append(int(order.id))
    await db.commit()
    return {"message": "ok", "advanced": advanced, "skipped": skipped}


@router.post("/orders/deliver")
async def demo_deliver_orders(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """演示：配送商一键送达。发货 → 收货，并把配送记录置「已送达」。"""
    _ensure_demo_mode()
    ids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not ids:
        raise HTTPException(400, "order_ids 非法")
    orders = (await db.scalars(select(Order).where(Order.id.in_(ids)))).all()
    now = datetime.utcnow()
    advanced: list[int] = []
    skipped: list[dict] = []
    for order in orders:
        if str(order.status) != "发货":
            skipped.append({"order_id": int(order.id), "reason": f"状态为{order.status}"})
            continue
        old_status = str(order.status)
        order.status = "收货"
        order.version += 1
        order.updated_at = now
        await _demo_log_transition(db, order, old_status, "收货", int(order.delivery_id))
        delivery = await db.scalar(select(Delivery).where(Delivery.order_id == int(order.id)))
        if delivery:
            delivery.arrived_at = now
            delivery.status = "已送达"
        # 副作用（= deliver_order）：监管事件 + 质检缺失 + 关闭配送超时工单/预警 + 已送达通知
        await _demo_emit_status_change(db, order, old_status, "收货")
        await _demo_mark_abnormal(db, order, int(order.delivery_id), "收货")
        await close_delivery_overdue_ticket_if_delivered(db, order)
        await close_delivery_overdue_alert_if_delivered(db, order)
        await _demo_notify(
            db, order, title=f"订单 {order.order_no} 已送达",
            content="订单已送达，等待客户端确认收货。",
            to_client=True, to_delivery=True, to_suppliers=True,
        )
        advanced.append(int(order.id))
    await db.commit()
    return {"message": "ok", "advanced": advanced, "skipped": skipped}


@router.post("/orders/receive")
async def demo_receive_orders(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """演示：客户一键收货确认（跳过称重/双签门禁）。收货 → 收货确认，并生成客户/配送/供货账单。"""
    _ensure_demo_mode()
    ids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not ids:
        raise HTTPException(400, "order_ids 非法")
    orders = (await db.scalars(select(Order).where(Order.id.in_(ids)))).all()
    now = datetime.utcnow()
    advanced: list[int] = []
    skipped: list[dict] = []
    bills_created = 0
    for order in orders:
        if str(order.status) != "收货":
            skipped.append({"order_id": int(order.id), "reason": f"状态为{order.status}"})
            continue
        old_status = str(order.status)
        order.status = "收货确认"
        order.version += 1
        order.updated_at = now
        # IoT 称重快照（= receive_order，演示按下单数量）
        iot_weight = sum(float(i.get("quantity", 0)) for i in (order.items_json or []))
        db.add(
            IoTData(
                device_type="scale",
                device_id=f"SCALE-{int(order.id)}",
                payload_json={"weight": iot_weight, "product_name": "混合物资", "unit": "kg", "receiving_snapshot": False},
                recorded_at=now,
            )
        )
        await create_returns_after_receive(db, order, int(order.client_id), None)
        await create_receive_bills(db, order)
        await create_receive_billing_statements(db, order)
        bills_created += len(
            (await db.scalars(select(Bill.id).where(Bill.order_id == int(order.id)))).all()
        )
        # 副作用（= receive_order）：状态日志/审计/outbox + 账单审计 + 监管事件 + 质检缺失 + 账单已生成通知
        await _demo_log_transition(db, order, old_status, "收货确认", int(order.client_id))
        await write_audit_log(
            db=db, actor_user_id=int(order.client_id), action="bill_create_on_receive", category="bill",
            object_type="order", object_id=int(order.id),
            detail="收货后自动生成客户（食堂）与配送商、配送商与供货商/厂家账单",
        )
        await _demo_emit_status_change(db, order, old_status, "收货确认")
        await _demo_mark_abnormal(db, order, int(order.client_id), "收货确认")
        await _demo_notify(
            db, order, title="账单已生成（客户（食堂）-配送商）",
            content=f"订单 {order.order_no} 已生成客户（食堂）与配送商账单，请及时对账。",
            to_client=True, to_delivery=True, event_type="bill_created",
            client_route="/client/bills", delivery_route="/delivery/bills",
        )
        await _demo_notify(
            db, order, title="供货商/厂家应收已入账",
            content=f"订单 {order.order_no} 已生成账单（客户（食堂）应付配送商；配送商应付供货商/厂家）。",
            to_delivery=True, to_suppliers=True, event_type="bill_created",
            delivery_route="/delivery/bills", supplier_route="/supplier/bills", factory_route="/factory/bills",
        )
        advanced.append(int(order.id))
    await db.commit()
    return {"message": "ok", "advanced": advanced, "bills_created": bills_created, "skipped": skipped}


@router.post("/orders/settle")
async def demo_settle_orders(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """演示：客户一键结算。收货确认 → 已结算，并把订单账单与相关账期对账单标记结清。"""
    _ensure_demo_mode()
    ids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not ids:
        raise HTTPException(400, "order_ids 非法")
    orders = (await db.scalars(select(Order).where(Order.id.in_(ids)))).all()
    now = datetime.utcnow()
    advanced: list[int] = []
    skipped: list[dict] = []
    bills_settled = 0
    statements_settled = 0
    for order in orders:
        if str(order.status) != "收货确认":
            skipped.append({"order_id": int(order.id), "reason": f"状态为{order.status}"})
            continue
        old_status = str(order.status)
        order.status = "已结算"
        order.version += 1
        order.updated_at = now
        await _demo_log_transition(db, order, old_status, "已结算", int(order.client_id))
        bills = (await db.scalars(select(Bill).where(Bill.order_id == int(order.id)))).all()
        for bill in bills:
            bill.status = "已结算"
            bills_settled += 1
        statements = (
            await db.scalars(
                select(BillingStatement).where(
                    BillingStatement.owner_user_id.in_([order.client_id, order.delivery_id]),
                    BillingStatement.counterparty_user_id.in_([order.client_id, order.delivery_id]),
                )
            )
        ).all()
        for statement in statements:
            if int(order.id) not in _json_order_ids(statement.source_snapshot_json or {}):
                continue
            statement.settled_amount = statement.amount
            statement.confirmed_amount = statement.amount
            statement.status = "已结清"
            statement.confirmed_at = statement.confirmed_at or now
            statements_settled += 1
        # 副作用（= settle_order）：结算审计 + 监管事件 + 质检缺失 + 账单已结算通知
        await write_audit_log(
            db=db, actor_user_id=int(order.client_id), action="bill_settle", category="bill",
            object_type="order", object_id=int(order.id),
            detail=f"订单账单结算条数={len(bills)}",
        )
        await _demo_emit_status_change(db, order, old_status, "已结算")
        await _demo_mark_abnormal(db, order, int(order.client_id), "已结算")
        await _demo_notify(
            db, order, title="账单已结算（客户（食堂）-配送商）",
            content=f"订单 {order.order_no} 客户（食堂）与配送商账单已结算。",
            to_client=True, to_delivery=True, event_type="bill_settled",
            client_route="/client/bills", delivery_route="/delivery/bills",
        )
        advanced.append(int(order.id))
    await db.commit()
    return {
        "message": "ok",
        "advanced": advanced,
        "bills_settled": bills_settled,
        "statements_settled": statements_settled,
        "skipped": skipped,
    }


@router.post("/orders/delete")
async def demo_delete_orders(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """按 order_ids 删除订单履约链路数据（仅演示模式）。"""
    _ensure_demo_mode()
    summary = await _delete_orders_cascade(db, payload.order_ids)
    await db.commit()
    return {"message": "ok", **summary}


@router.post("/orders/clear-all")
async def demo_clear_all_orders(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """删除库中全部订单履约链路数据（仅演示模式，用于一键清开发验收数据）。"""
    _ensure_demo_mode()
    r = await db.execute(select(Order.id))
    ids = [int(row[0]) for row in r.all()]
    if not ids:
        return {"message": "ok", **_empty_delete_summary(0)}
    summary = await _delete_orders_cascade(db, ids)
    await db.commit()
    return {"message": "ok", **summary}


@router.post("/orders/mark-allocations-shipped")
async def demo_mark_allocations_shipped(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """将所列订单下全部分单行 status 置为「已出库」（仅演示模式）。"""
    _ensure_demo_mode()
    ids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not ids:
        raise HTTPException(400, "order_ids 非法")
    now = datetime.utcnow()
    res = await db.execute(
        update(OrderItemAllocation)
        .where(OrderItemAllocation.order_id.in_(ids))
        .values(status="已出库", updated_at=now)
    )
    # 发货副作用（= ship_order）：对有分单的订单同步质检缺失异常/预警 + 通知配送商
    orders = (
        await db.scalars(
            select(Order).where(
                Order.id.in_(ids),
                Order.id.in_(select(OrderItemAllocation.order_id).where(OrderItemAllocation.order_id.in_(ids))),
            )
        )
    ).all()
    for order in orders:
        await _demo_after_ship(db, order, int(order.delivery_id))
    await db.commit()
    return {"message": "ok", "rows_updated": int(res.rowcount or 0)}


@router.post("/dispatch/prepare")
async def demo_prepare_dispatch(
    payload: DispatchDemoPrepareIn | None = None,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """一键准备智能排线演示数据：车辆、配货订单、分单、出库、分检记录。"""
    _ensure_demo_mode()
    payload = payload or DispatchDemoPrepareIn()
    planning_date = payload.planning_date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    delivery = await db.scalar(
        select(User).where(User.username == payload.delivery_username, User.role == "delivery")
    )
    if not delivery:
        raise HTTPException(400, f"配送商账号 {payload.delivery_username} 不存在")
    delivery_id = int(delivery.id)

    vehicles = await _ensure_dispatch_demo_vehicles(db, delivery_id)
    suppliers = await _dispatch_demo_suppliers(db, delivery_id)
    products = await _dispatch_demo_product_pool(db)
    active_dispatch_order_ids = {
        int(x)
        for x in (
            await db.scalars(
                select(DeliveryDispatchStop.order_id)
                .join(DeliveryDispatchTrip, DeliveryDispatchTrip.id == DeliveryDispatchStop.trip_id)
                .where(
                    DeliveryDispatchTrip.delivery_id == delivery_id,
                    DeliveryDispatchTrip.status.in_(["待发车", "有阻塞", "运输中"]),
                )
            )
        ).all()
    }

    selected_orders: list[Order] = []
    requested_ids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if requested_ids:
        blocked_requested = [i for i in requested_ids if i in active_dispatch_order_ids]
        if blocked_requested:
            raise HTTPException(400, f"订单已在未完成车次中，请先取消旧车次：{blocked_requested[:10]}")
        selected_orders = (
            await db.scalars(
                select(Order)
                .where(Order.id.in_(requested_ids), Order.delivery_id == delivery_id)
                .order_by(Order.id.asc())
            )
        ).all()
        if len(selected_orders) != len(requested_ids):
            raise HTTPException(400, "部分 order_ids 不属于当前配送商或不存在")
    else:
        stmt = (
            select(Order)
            .where(
                Order.delivery_id == delivery_id,
                Order.status.in_(["下单", "配货"]),
                Order.expected_delivery_date == planning_date,
            )
            .order_by(Order.id.desc())
            .limit(payload.target_order_count)
        )
        if active_dispatch_order_ids:
            stmt = stmt.where(~Order.id.in_(active_dispatch_order_ids))
        selected_orders = (await db.scalars(stmt)).all()
        if payload.create_if_missing and len(selected_orders) < payload.target_order_count:
            need = payload.target_order_count - len(selected_orders)
            created = await _create_dispatch_demo_orders(
                db,
                delivery_id=delivery_id,
                planning_date=planning_date,
                count=need,
                products=products,
            )
            selected_orders = created + selected_orders
    if not selected_orders:
        raise HTTPException(400, "没有可准备的演示订单，请允许 create_if_missing 或传入有效 order_ids")

    now = datetime.utcnow()
    supplier_ids = [int(s.id) for s in suppliers]
    product_ids = sorted(
        {
            int(item.get("product_id") or 0)
            for order in selected_orders
            for item in (order.items_json or [])
            if int(item.get("product_id") or 0) > 0
        }
    )
    product_map = {
        int(p.id): p
        for p in (
            await db.scalars(select(Product).where(Product.id.in_(product_ids)))
        ).all()
    } if product_ids else {}
    # 分单成本价表：(供货商, 商品) -> 报价；与真实分单口径一致，缺报价/指定厂兜底指导价
    demo_quote_map: dict[tuple[int, int], float] = {}
    if supplier_ids and product_ids:
        for q in (
            await db.scalars(
                select(SupplierProductQuote).where(
                    SupplierProductQuote.supplier_id.in_(supplier_ids),
                    SupplierProductQuote.product_id.in_(product_ids),
                )
            )
        ).all():
            demo_quote_map[(int(q.supplier_id), int(q.product_id))] = float(q.quote_price or 0)

    prepared_order_ids: list[int] = []
    created_allocations = 0
    shipped_allocations = 0
    scanned_allocations = 0
    skipped_orders: list[dict] = []

    for order_idx, order in enumerate(selected_orders):
        if str(order.status) not in {"下单", "配货"}:
            skipped_orders.append({"order_id": int(order.id), "order_no": order.order_no, "reason": f"状态为{order.status}"})
            continue
        if order.expected_delivery_date != planning_date:
            order.expected_delivery_date = planning_date
        if not order.expected_delivery_slot:
            order.expected_delivery_slot = "08:00-09:00"
        if not order.delivery_address:
            client = await db.scalar(select(User).where(User.id == int(order.client_id)))
            order.delivery_address = (client.address if client else "") or "北京市朝阳区演示配送点"
            order.delivery_lng = getattr(client, "lng", None) if client else None
            order.delivery_lat = getattr(client, "lat", None) if client else None
        old_status = str(order.status)
        if old_status != "配货":
            order.status = "配货"
            order.version += 1
            db.add(
                OrderStatusLog(
                    order_id=int(order.id),
                    old_status=old_status,
                    new_status="配货",
                    actor_user_id=delivery_id,
                )
            )
        order.updated_at = now

        allocations = (
            await db.scalars(
                select(OrderItemAllocation)
                .where(OrderItemAllocation.order_id == int(order.id), OrderItemAllocation.delivery_id == delivery_id)
                .order_by(OrderItemAllocation.line_no.asc(), OrderItemAllocation.id.asc())
            )
        ).all()
        if not allocations:
            batch_no = f"demo-dispatch-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
            for line_no, item in enumerate(order.items_json or [], 1):
                pid = int(item.get("product_id") or 0)
                if pid <= 0:
                    continue
                supplier_id = supplier_ids[(order_idx + line_no - 1) % len(supplier_ids)]
                product = product_map.get(pid)
                ref_price = float(getattr(product, "reference_price", None) or 10)
                # 分单单价 = 供货商成本价（报价），而非客户价；指定厂/缺报价兜底指导价
                if product is not None and bool(getattr(product, "is_designated_factory", False)):
                    cost_price = ref_price
                else:
                    cost_price = demo_quote_map.get((supplier_id, pid)) or ref_price
                allocation = OrderItemAllocation(
                    order_id=int(order.id),
                    delivery_id=delivery_id,
                    supplier_id=supplier_id,
                    line_no=line_no,
                    product_id=pid,
                    quantity=round(float(item.get("quantity") or 1), 3),
                    unit_price=round(float(cost_price), 2),
                    allocation_batch_no=batch_no,
                    status="已分配",
                    created_by=delivery_id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(allocation)
                await db.flush()
                db.add(
                    OrderItemStatusLog(
                        allocation_id=int(allocation.id),
                        old_status="待确认",
                        new_status="已分配",
                        operator_id=delivery_id,
                        note="演示联调自动分单",
                    )
                )
                allocations.append(allocation)
                created_allocations += 1

        for allocation in allocations:
            if payload.mark_shipped and str(allocation.status) != "已出库":
                old_alloc_status = str(allocation.status)
                allocation.status = "已出库"
                allocation.label_print_count = max(int(allocation.label_print_count or 0), 1)
                allocation.updated_at = now
                db.add(
                    OrderItemStatusLog(
                        allocation_id=int(allocation.id),
                        old_status=old_alloc_status,
                        new_status="已出库",
                        operator_id=delivery_id,
                        note="演示联调自动出库",
                    )
                )
                shipped_allocations += 1
            if payload.mark_sorted:
                existed = await db.scalar(
                    select(DeliverySortScanRecord.id).where(
                        DeliverySortScanRecord.allocation_id == int(allocation.id)
                    )
                )
                if not existed:
                    db.add(
                        DeliverySortScanRecord(
                            allocation_id=int(allocation.id),
                            order_id=int(order.id),
                            delivery_id=delivery_id,
                            operator_id=delivery_id,
                            barcode_value=str(allocation.id),
                            device_code="demo-dispatch-prepare",
                            scanned_at=now,
                            created_at=now,
                        )
                    )
                    scanned_allocations += 1
        prepared_order_ids.append(int(order.id))

    await db.commit()
    return {
        "message": "智能排线演示数据已准备",
        "planning_date": planning_date.isoformat(),
        "delivery_username": payload.delivery_username,
        "delivery_name": delivery.company_name or delivery.username,
        "orders": {
            "prepared_count": len(prepared_order_ids),
            "order_ids": prepared_order_ids,
            "skipped": skipped_orders,
        },
        "allocations": {
            "created": created_allocations,
            "marked_shipped": shipped_allocations,
            "scan_records_created": scanned_allocations,
        },
        "vehicles": [
            {
                "vehicle_id": int(v.id),
                "vehicle_no": v.vehicle_no,
                "driver_name": v.driver_name,
                "driver_login_password": "demo123",
                "beidou_device_code": f"BD-DEMO-{delivery_id}-{v.vehicle_no}",
                "beidou_position": "已写入演示坐标",
            }
            for v in vehicles
        ],
        "next_steps": [
            "配送商登录后进入：智能排线",
            f"选择配送日期 {planning_date.isoformat()}，勾选这些订单并生成智能路线",
            "保存为发车计划后，司机端使用车牌号 + demo123 登录",
        ],
    }


@router.post("/orders/supplier-ship-bulk")
async def demo_supplier_ship_bulk(
    payload: SupplierShipBulkIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """演示：指定供货商对一批订单中「属于自己的分单行」一键发货（已出库），不校验标签打印。"""
    _ensure_demo_mode()
    uname = (payload.supplier_username or "").strip()
    sup = await db.scalar(select(User).where(User.username == uname, User.role == "supplier"))
    if not sup:
        raise HTTPException(400, f"供货商「{uname}」不存在")
    sid = int(sup.id)
    oids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not oids:
        raise HTTPException(400, "order_ids 非法")
    now = datetime.utcnow()
    touched = 0
    alloc_updated = 0
    touched_orders: list[Order] = []
    for oid in oids:
        order = await db.scalar(select(Order).where(Order.id == oid))
        if not order:
            continue
        if str(order.status) not in {"下单", "配货"}:
            continue
        allocs = (
            await db.scalars(
                select(OrderItemAllocation).where(
                    OrderItemAllocation.order_id == oid,
                    OrderItemAllocation.supplier_id == sid,
                )
            )
        ).all()
        if not allocs:
            continue
        touched += 1
        touched_orders.append(order)
        for a in allocs:
            a.status = "已出库"
            a.updated_at = now
            alloc_updated += 1
    # 发货副作用（= ship_order）：质检缺失同步 + 通知配送商
    for order in touched_orders:
        await _demo_after_ship(db, order, int(order.delivery_id))
    await db.commit()
    return {
        "message": "ok",
        "orders_with_lines": touched,
        "allocation_rows_updated": alloc_updated,
        "supplier_username": uname,
    }


@router.post("/orders/supplier-ship-all")
async def demo_supplier_ship_all(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """对订单列表中、绑定到订单所属配送商的全部演示供货商，各自一键将名下分单行标为已出库（跳过打印门禁）。"""
    _ensure_demo_mode()
    oids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not oids:
        raise HTTPException(400, "order_ids 非法")
    orders = (await db.scalars(select(Order).where(Order.id.in_(oids)))).all()
    if not orders:
        return {
            "message": "ok",
            "allocation_rows_updated": 0,
            "suppliers_touched": 0,
            "details": [],
        }
    delivery_ids = {int(o.delivery_id) for o in orders}
    supplier_users = (
        await db.scalars(
            select(User).where(
                User.role == "supplier",
                User.status == "active",
                User.supplier_delivery_id.in_(delivery_ids),
            )
        )
    ).all()
    now = datetime.utcnow()
    total_alloc = 0
    details: list[dict] = []
    all_touched_oids: set[int] = set()
    for sup in supplier_users:
        sid = int(sup.id)
        did = int(sup.supplier_delivery_id or 0)
        allocs = (
            await db.scalars(
                select(OrderItemAllocation)
                .join(Order, Order.id == OrderItemAllocation.order_id)
                .where(
                    OrderItemAllocation.order_id.in_(oids),
                    OrderItemAllocation.supplier_id == sid,
                    Order.delivery_id == did,
                    Order.status.in_(["下单", "配货"]),
                )
            )
        ).all()
        if not allocs:
            continue
        touched_orders = len({int(a.order_id) for a in allocs})
        for a in allocs:
            a.status = "已出库"
            a.updated_at = now
        n = len(allocs)
        total_alloc += n
        all_touched_oids.update(int(a.order_id) for a in allocs)
        details.append(
            {
                "supplier_username": sup.username,
                "allocation_rows_updated": n,
                "orders_with_lines": touched_orders,
            }
        )
    # 发货副作用（= ship_order）：质检缺失同步 + 通知配送商
    if all_touched_oids:
        touched = (await db.scalars(select(Order).where(Order.id.in_(all_touched_oids)))).all()
        for order in touched:
            await _demo_after_ship(db, order, int(order.delivery_id))
    await db.commit()
    return {
        "message": "ok",
        "allocation_rows_updated": total_alloc,
        "suppliers_touched": len(details),
        "details": details,
    }


@router.post("/orders/mock-print-allocation-labels")
async def demo_mock_print_allocation_labels(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """为所列订单下每条分单行写入与供货商端一致的行级标签打印审计（演示用，不校验真实打印）。"""
    _ensure_demo_mode()
    oids = sorted({int(i) for i in payload.order_ids if int(i) > 0})
    if not oids:
        raise HTTPException(400, "order_ids 非法")
    allocs = (
        await db.scalars(select(OrderItemAllocation).where(OrderItemAllocation.order_id.in_(oids)))
    ).all()
    n = 0
    for alloc in allocs:
        order = await db.scalar(select(Order).where(Order.id == alloc.order_id))
        if not order:
            continue
        await write_audit_log(
            db=db,
            actor_user_id=int(alloc.supplier_id),
            action="supplier_print_allocation_label",
            category="order",
            object_type="order",
            object_id=int(order.id),
            detail=f"演示模拟行级标签 allocation={alloc.id} order={order.order_no}",
            after_json={
                "allocation_id": int(alloc.id),
                "line_no": int(alloc.line_no),
                "product_id": int(alloc.product_id),
            },
        )
        n += 1
    await db.commit()
    return {"message": "ok", "audit_rows_added": n}


@router.post("/new-order")
async def simulate_new_order(
    _=Depends(require_role("monitor")), db: AsyncSession = Depends(get_db)
):
    _ensure_demo_mode()
    client = await db.scalar(select(User).where(User.username == "client001"))
    delivery = await db.scalar(select(User).where(User.username == "delivery001"))
    if not client or not delivery:
        raise HTTPException(500, "演示账号 client001/delivery001 不完整，请先种子初始化")
    cc = await db.scalar(
        select(ClientCanteen.id)
        .where(ClientCanteen.school_client_id == int(client.id), ClientCanteen.status == "active")
        .order_by(ClientCanteen.sort_order.asc(), ClientCanteen.id.asc())
        .limit(1)
    )
    if not cc:
        raise HTTPException(500, "演示客户缺少食堂数据，请重启后端以执行种子")
    row = Order(
        order_no="ODDEMO" + datetime.utcnow().strftime("%H%M%S"),
        client_id=int(client.id),
        canteen_id=int(cc),
        delivery_id=int(delivery.id),
        supplier_id=None,
        items_json=[{"product_id": 1, "quantity": 10, "unit_price": 6.8}],
        items_snapshot_json=[],
        total_amount=68,
        status="下单",
        has_abnormal=False,
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await publish_monitor_event(
        "order_status_change",
        {
            "order_id": row.id,
            "order_no": row.order_no,
            "old_status": "N/A",
            "new_status": "下单",
        },
    )
    return row


@router.post("/trigger-temperature-alert")
async def trigger_temperature_alert(
    _=Depends(require_role("monitor")), db: AsyncSession = Depends(get_db)
):
    _ensure_demo_mode()
    iot = IoTData(
        device_type="sensor",
        device_id="WH-001",
        payload_json={"temperature": 12.8, "humidity": 80},
        recorded_at=datetime.utcnow(),
    )
    db.add(iot)
    alert = Alert(
        level="high",
        type="sensor",
        description="手动触发温湿度预警",
        status="open",
        payload_json={"device_id": "WH-001", "temperature": 12.8, "humidity": 80},
        created_at=datetime.utcnow(),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    await publish_monitor_event(
        "new_alert",
        {
            "id": alert.id,
            "level": alert.level,
            "type": alert.type,
            "description": alert.description,
            "created_at": alert.created_at.isoformat(),
        },
    )
    await publish_monitor_event(
        "sensor_warning",
        {"device_id": "WH-001", "temperature": 12.8, "humidity": 80},
    )
    return {"message": "ok", "alert_id": alert.id}


@router.post("/simulate-delivery")
async def simulate_delivery(
    _=Depends(require_role("monitor")), db: AsyncSession = Depends(get_db)
):
    _ensure_demo_mode()
    base_lat, base_lng = 39.90, 116.40
    for i in range(10):
        db.add(
            IoTData(
                device_type="gps",
                device_id="京A12345",
                payload_json={
                    "lat": base_lat + i * 0.002,
                    "lng": base_lng + i * 0.0015,
                    "speed": 35 + i,
                    "direction": 90,
                    "order_id": 1,
                    "driver": "张师傅",
                },
                recorded_at=datetime.utcnow(),
            )
        )
    await db.commit()
    return {"message": "ok", "steps": 10}


@router.post("/reset")
async def reset_demo_data(
    _=Depends(require_role("monitor")), db: AsyncSession = Depends(get_db)
):
    _ensure_demo_mode()
    for model in [
        TenderBid,
        Tender,
        OrderReview,
        OrderAbnormal,
        SortRecord,
        Delivery,
        Bill,
        QualityReport,
        Ticket,
        Contract,
        Order,
        Alert,
        IoTData,
    ]:
        await db.execute(delete(model))
    await db.commit()
    await seed_data(db)
    return {"message": "reset done"}
