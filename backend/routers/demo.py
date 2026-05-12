from datetime import datetime

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
    ClientCanteen,
    Contract,
    Delivery,
    IdempotencyKey,
    IoTData,
    Notification,
    Order,
    OrderAbnormal,
    OrderItemAllocation,
    OrderItemStatusLog,
    OrderReceivingLine,
    OrderReview,
    OrderStatusLog,
    QualityReport,
    SortRecord,
    Tender,
    TenderBid,
    Ticket,
    User,
)
from services.audit_service import write_audit_log
from services.event_bus import publish_monitor_event

router = APIRouter(prefix="/demo", tags=["demo"])


def _ensure_demo_mode():
    if not settings.demo_mode:
        raise HTTPException(403, "仅演示模式可用")


@router.get("/client-accounts")
async def demo_client_accounts(
    db: AsyncSession = Depends(get_db),
):
    """演示控制台用：返回库中全部启用状态的采购方账号（无需登录；仅 demo_mode 放行）。"""
    _ensure_demo_mode()
    rows = (
        await db.scalars(
            select(User)
            .where(User.role == "client", User.status == "active")
            .order_by(User.username.asc())
        )
    ).all()
    out = []
    for r in rows:
        lng = float(r.lng) if r.lng is not None else None
        lat = float(r.lat) if r.lat is not None else None
        out.append(
            {
                "username": r.username,
                "company_name": (r.company_name or "").strip(),
                "address": (r.address or "").strip(),
                "lng": lng,
                "lat": lat,
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


async def _delete_orders_cascade(db: AsyncSession, order_ids: list[int]) -> int:
    ids = sorted({int(i) for i in order_ids if int(i) > 0})
    if not ids:
        raise HTTPException(400, "order_ids 非法")
    await db.execute(delete(OrderReceivingLine).where(OrderReceivingLine.order_id.in_(ids)))
    alloc_ids = (
        await db.scalars(select(OrderItemAllocation.id).where(OrderItemAllocation.order_id.in_(ids)))
    ).all()
    alloc_ids_i = [int(a) for a in alloc_ids]
    if alloc_ids_i:
        await db.execute(delete(OrderItemStatusLog).where(OrderItemStatusLog.allocation_id.in_(alloc_ids_i)))
    await db.execute(delete(OrderItemAllocation).where(OrderItemAllocation.order_id.in_(ids)))
    await db.execute(delete(OrderStatusLog).where(OrderStatusLog.order_id.in_(ids)))
    await db.execute(delete(OrderReview).where(OrderReview.order_id.in_(ids)))
    await db.execute(delete(Ticket).where(Ticket.order_id.in_(ids)))
    await db.execute(delete(SortRecord).where(SortRecord.order_id.in_(ids)))
    await db.execute(delete(QualityReport).where(QualityReport.order_id.in_(ids)))
    await db.execute(delete(Bill).where(Bill.order_id.in_(ids)))
    await db.execute(delete(Delivery).where(Delivery.order_id.in_(ids)))
    await db.execute(delete(OrderAbnormal).where(OrderAbnormal.order_id.in_(ids)))
    await db.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.resource_id.in_(ids),
            IdempotencyKey.scope.in_(["order_receive", "order_settle"]),
        )
    )
    await db.execute(delete(AuditLog).where(AuditLog.object_type == "order", AuditLog.object_id.in_(ids)))
    await db.execute(
        delete(Notification).where(Notification.object_type == "order", Notification.object_id.in_(ids))
    )
    await db.execute(delete(Order).where(Order.id.in_(ids)))
    return len(ids)


@router.post("/orders/delete")
async def demo_delete_orders(
    payload: OrderIdsIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """按 order_ids 级联删除订单及常见子表（仅演示模式）。"""
    _ensure_demo_mode()
    n = await _delete_orders_cascade(db, payload.order_ids)
    await db.commit()
    return {"message": "ok", "deleted_orders": n}


@router.post("/orders/clear-all")
async def demo_clear_all_orders(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """删除库中全部订单及关联分单、收货行、账单等（仅演示模式，用于一键清测试数据）。"""
    _ensure_demo_mode()
    r = await db.execute(select(Order.id))
    ids = [int(row[0]) for row in r.all()]
    if not ids:
        return {"message": "ok", "deleted_orders": 0}
    n = await _delete_orders_cascade(db, ids)
    await db.commit()
    return {"message": "ok", "deleted_orders": n}


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
    await db.commit()
    return {"message": "ok", "rows_updated": int(res.rowcount or 0)}


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
        for a in allocs:
            a.status = "已出库"
            a.updated_at = now
            alloc_updated += 1
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
        details.append(
            {
                "supplier_username": sup.username,
                "allocation_rows_updated": n,
                "orders_with_lines": touched_orders,
            }
        )
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
