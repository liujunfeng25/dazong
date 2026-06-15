"""未发车车次编辑：追加站点、调序、换车、移除站点及 ETA 重算。"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    ClientCanteen,
    DeliveryDispatchItem,
    DeliveryDispatchStop,
    DeliveryDispatchTrip,
    Order,
    OrderItemAllocation,
    User,
)
from services.delivery_slot import parse_delivery_slot_hours
from services.dispatch_occupancy import ACTIVE_DISPATCH_TRIP_STATUSES, active_dispatch_trip_filters

EDITABLE_TRIP_STATUSES = frozenset({"待发车", "有阻塞"})
DEFAULT_SERVICE_MINUTES = 30
SH_TZ = ZoneInfo("Asia/Shanghai")


def validate_stop_removal(current_order_ids: list[int], remove_order_ids: list[int]) -> set[int]:
    current = {int(x) for x in current_order_ids}
    to_remove = {int(x) for x in remove_order_ids if int(x) in current}
    if to_remove and len(current - to_remove) == 0:
        raise ValueError("车次必须保留至少一个站点；如不再执行，请取消车次")
    return to_remove


def _haversine_km(a_lng: float, a_lat: float, b_lng: float, b_lat: float) -> float:
    rad = math.pi / 180
    lat1 = a_lat * rad
    lat2 = b_lat * rad
    dlat = lat2 - lat1
    dlng = (b_lng - a_lng) * rad
    x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(max(x, 0)))


def _order_coords(order: Order, client: User | None, base_lng: float, base_lat: float, idx: int) -> tuple[float, float]:
    if order.delivery_lng is not None and order.delivery_lat is not None:
        return float(order.delivery_lng), float(order.delivery_lat)
    if client and client.lng is not None and client.lat is not None:
        return float(client.lng), float(client.lat)
    return round(base_lng + idx * 0.009, 6), round(base_lat + idx * 0.006, 6)


def _parse_departure_sh(plan_date: date, departure_time: str) -> datetime:
    raw = (departure_time or "06:00").strip().replace("：", ":")
    parts = raw.split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    return datetime.combine(plan_date, time(hh, mm), tzinfo=SH_TZ)


def _order_window_sh(order: Order, plan_date: date) -> tuple[datetime, datetime]:
    d = order.expected_delivery_date or plan_date
    parsed = parse_delivery_slot_hours(order.expected_delivery_slot)
    ha, hb = parsed if parsed else (9, 10)
    start = datetime.combine(d, time(ha, 0), tzinfo=SH_TZ)
    if hb >= 24:
        end = datetime.combine(d, time(23, 59, 59), tzinfo=SH_TZ)
    else:
        end = datetime.combine(d, time(hb, 0), tzinfo=SH_TZ)
    return start, end


def _clamp_arrive(arrive_utc: datetime, window_start_sh: datetime) -> datetime:
    ws_utc = window_start_sh.astimezone(timezone.utc)
    return arrive_utc if arrive_utc >= ws_utc else ws_utc


async def recalculate_trip_stop_etas(
    db: AsyncSession,
    trip: DeliveryDispatchTrip,
    *,
    driver: User | None,
    service_minutes: int = DEFAULT_SERVICE_MINUTES,
) -> None:
    stops = (
        await db.scalars(
            select(DeliveryDispatchStop)
            .where(DeliveryDispatchStop.trip_id == int(trip.id))
            .order_by(DeliveryDispatchStop.sequence.asc(), DeliveryDispatchStop.id.asc())
        )
    ).all()
    if not stops:
        trip.total_orders = 0
        trip.distance_km = 0.0
        trip.duration_minutes = 0
        return

    order_ids = [int(s.order_id) for s in stops]
    orders = (await db.scalars(select(Order).where(Order.id.in_(order_ids)))).all()
    order_map = {int(o.id): o for o in orders}
    client_ids = sorted({int(o.client_id) for o in orders if o.client_id})
    clients = (
        await db.scalars(select(User).where(User.id.in_(client_ids), User.role == "client"))
    ).all() if client_ids else []
    client_map = {int(c.id): c for c in clients}

    base_lng = float(driver.lng) if driver and driver.lng is not None else 116.397
    base_lat = float(driver.lat) if driver and driver.lat is not None else 39.908
    cur_lng, cur_lat = base_lng, base_lat
    planned = _parse_departure_sh(trip.planning_date, trip.departure_time).astimezone(timezone.utc)
    total_km = 0.0
    total_min = 0

    for idx, stop in enumerate(stops, 1):
        order = order_map.get(int(stop.order_id))
        if not order:
            continue
        client = client_map.get(int(order.client_id)) if order.client_id else None
        tgt_lng, tgt_lat = _order_coords(order, client, base_lng, base_lat, idx)
        dist = round(_haversine_km(cur_lng, cur_lat, tgt_lng, tgt_lat), 2)
        drive_min = max(8, int(round(dist * 3.2)))
        win_start, _win_end = _order_window_sh(order, trip.planning_date)
        arrive = _clamp_arrive(planned + timedelta(minutes=drive_min), win_start)
        leave = arrive + timedelta(minutes=service_minutes)
        arr_sh = arrive.astimezone(SH_TZ)
        leave_sh = leave.astimezone(SH_TZ)
        stop.sequence = idx
        stop.planned_arrive_time = arr_sh.strftime("%H:%M")
        stop.planned_leave_time = leave_sh.strftime("%H:%M")
        stop.updated_at = datetime.utcnow()
        total_km += dist
        total_min += drive_min + service_minutes
        planned = leave
        cur_lng, cur_lat = tgt_lng, tgt_lat

    trip.total_orders = len(stops)
    trip.distance_km = round(total_km, 2)
    trip.duration_minutes = int(total_min)
    trip.updated_at = datetime.utcnow()


async def validate_orders_for_trip_append(
    db: AsyncSession,
    *,
    trip: DeliveryDispatchTrip,
    delivery_id: int,
    order_ids: list[int],
) -> list[Order]:
    if not order_ids:
        return []
    orders = (
        await db.scalars(select(Order).where(Order.id.in_(order_ids)).order_by(Order.id.asc()))
    ).all()
    order_map = {int(o.id): o for o in orders}
    if len(order_map) != len(set(order_ids)):
        raise ValueError("部分订单不存在")
    for oid in order_ids:
        order = order_map.get(int(oid))
        if not order:
            raise ValueError(f"订单 #{oid} 不存在")
        if int(order.delivery_id) != int(delivery_id):
            raise ValueError(f"订单 {order.order_no} 不属于当前配送商")
        if str(order.status) != "配货":
            raise ValueError(f"订单 {order.order_no} 须为配货状态")
        if order.expected_delivery_date != trip.planning_date:
            raise ValueError(
                f"订单 {order.order_no} 配送日为 {order.expected_delivery_date}，与车次计划日 {trip.planning_date} 不一致"
            )
    active_rows = (
        await db.execute(
            select(DeliveryDispatchStop.order_id, DeliveryDispatchTrip.route_no)
            .join(DeliveryDispatchTrip, DeliveryDispatchTrip.id == DeliveryDispatchStop.trip_id)
            .where(
                DeliveryDispatchStop.order_id.in_(order_ids),
                *active_dispatch_trip_filters(
                    delivery_id=int(delivery_id),
                    planning_date=trip.planning_date,
                ),
                DeliveryDispatchTrip.id != int(trip.id),
            )
        )
    ).all()
    if active_rows:
        oid, route_no = active_rows[0]
        raise ValueError(f"订单 #{int(oid)} 已在 {trip.planning_date} 的未完成车次 {route_no} 中")
    existing = (
        await db.scalars(
            select(DeliveryDispatchStop.order_id).where(
                DeliveryDispatchStop.trip_id == int(trip.id),
                DeliveryDispatchStop.order_id.in_(order_ids),
            )
        )
    ).all()
    if existing:
        raise ValueError(f"订单 #{int(existing[0])} 已在当前车次中")
    return [order_map[int(i)] for i in order_ids if int(i) in order_map]


async def append_orders_to_trip(
    db: AsyncSession,
    *,
    trip: DeliveryDispatchTrip,
    delivery_id: int,
    order_ids: list[int],
    driver: User | None,
    item_status_fn,
    scanned_ids: set[int],
) -> list[DeliveryDispatchStop]:
    if str(trip.status) not in EDITABLE_TRIP_STATUSES:
        raise ValueError("仅待发车或有阻塞车次可追加站点")
    orders = await validate_orders_for_trip_append(
        db, trip=trip, delivery_id=delivery_id, order_ids=order_ids
    )
    if not orders:
        return []

    max_seq = await db.scalar(
        select(DeliveryDispatchStop.sequence)
        .where(DeliveryDispatchStop.trip_id == int(trip.id))
        .order_by(DeliveryDispatchStop.sequence.desc())
    )
    seq_base = int(max_seq or 0)

    client_ids = sorted({int(o.client_id) for o in orders if o.client_id})
    canteen_ids = sorted({int(o.canteen_id) for o in orders if o.canteen_id})
    clients = (await db.scalars(select(User).where(User.id.in_(client_ids)))).all() if client_ids else []
    canteens = (
        await db.scalars(select(ClientCanteen).where(ClientCanteen.id.in_(canteen_ids)))
    ).all() if canteen_ids else []
    client_map = {int(c.id): c for c in clients}
    canteen_map = {int(c.id): c for c in canteens}

    allocs = (
        await db.scalars(
            select(OrderItemAllocation).where(
                OrderItemAllocation.order_id.in_([int(o.id) for o in orders])
            )
        )
    ).all()
    allocs_by_order: dict[int, list] = {}
    for a in allocs:
        allocs_by_order.setdefault(int(a.order_id), []).append(a)
    for order in orders:
        if not allocs_by_order.get(int(order.id)):
            raise ValueError(f"订单 {order.order_no} 尚未生成分单")

    product_ids = sorted({int(a.product_id) for a in allocs})
    supplier_ids = sorted({int(a.supplier_id) for a in allocs})
    from models import Product

    products = (await db.scalars(select(Product).where(Product.id.in_(product_ids)))).all() if product_ids else []
    suppliers = (await db.scalars(select(User).where(User.id.in_(supplier_ids)))).all() if supplier_ids else []
    product_map = {int(p.id): p for p in products}
    supplier_map = {int(s.id): s for s in suppliers}

    now = datetime.utcnow()
    created_stops: list[DeliveryDispatchStop] = []
    for i, order in enumerate(orders, 1):
        client = client_map.get(int(order.client_id)) if order.client_id else None
        canteen = canteen_map.get(int(order.canteen_id)) if order.canteen_id else None
        stop = DeliveryDispatchStop(
            trip_id=int(trip.id),
            order_id=int(order.id),
            sequence=seq_base + i,
            order_no=order.order_no,
            client_name=(client.company_name or client.username if client else "") or f"客户#{order.client_id}",
            canteen_name=str(canteen.name if canteen else ""),
            address=str(order.delivery_address or ""),
            expected_delivery_date=order.expected_delivery_date,
            expected_delivery_slot=order.expected_delivery_slot or "",
            status="待发车",
            created_at=now,
            updated_at=now,
        )
        db.add(stop)
        await db.flush()
        created_stops.append(stop)
        for alloc in allocs_by_order.get(int(order.id), []):
            product = product_map.get(int(alloc.product_id))
            supplier = supplier_map.get(int(alloc.supplier_id))
            spec = str(getattr(product, "spec", "") or "")
            unit = str(getattr(product, "unit", "") or "")
            db.add(
                DeliveryDispatchItem(
                    trip_id=int(trip.id),
                    stop_id=int(stop.id),
                    allocation_id=int(alloc.id),
                    order_id=int(alloc.order_id),
                    supplier_id=int(alloc.supplier_id),
                    product_id=int(alloc.product_id),
                    product_name=str(getattr(product, "name", "") or f"商品#{int(alloc.product_id)}"),
                    spec_unit=" / ".join([x for x in [spec, unit] if x]),
                    quantity=float(alloc.quantity),
                    unit=unit,
                    supplier_name=str(
                        (supplier.company_name or supplier.username) if supplier else f"供货商#{int(alloc.supplier_id)}"
                    ),
                    status=item_status_fn(alloc, scanned_ids),
                    created_at=now,
                    updated_at=now,
                )
            )

    await recalculate_trip_stop_etas(db, trip, driver=driver)
    return created_stops


async def update_editable_trip(
    db: AsyncSession,
    *,
    trip: DeliveryDispatchTrip,
    delivery_id: int,
    driver: User | None,
    vehicle_id: int | None = None,
    stop_order_ids: list[int] | None = None,
    remove_order_ids: list[int] | None = None,
    item_status_fn=None,
    scanned_ids: set[int] | None = None,
) -> dict[str, Any]:
    if str(trip.status) not in EDITABLE_TRIP_STATUSES:
        raise ValueError("仅待发车或有阻塞车次可编辑")

    changes: dict[str, Any] = {}

    if vehicle_id is not None:
        from models import DeliveryVehicle

        vehicle = await db.scalar(
            select(DeliveryVehicle).where(
                DeliveryVehicle.id == int(vehicle_id),
                DeliveryVehicle.delivery_id == int(delivery_id),
                DeliveryVehicle.status == "active",
            )
        )
        if not vehicle:
            raise ValueError("目标车辆不存在或已停用")
        conflict = await db.scalar(
            select(DeliveryDispatchTrip)
            .where(
                *active_dispatch_trip_filters(
                    delivery_id=int(delivery_id),
                    planning_date=trip.planning_date,
                ),
                DeliveryDispatchTrip.id != int(trip.id),
                (
                    (DeliveryDispatchTrip.vehicle_id == int(vehicle.id))
                    | (DeliveryDispatchTrip.vehicle_no == vehicle.vehicle_no)
                ),
            )
        )
        if conflict:
            raise ValueError(
                f"车辆 {vehicle.vehicle_no} 已被 {trip.planning_date} 的未完成车次 {conflict.route_no} 占用"
            )
        trip.vehicle_id = int(vehicle.id)
        trip.vehicle_no = vehicle.vehicle_no
        trip.driver_name = str(vehicle.driver_name or trip.driver_name or "")
        changes["vehicle_no"] = vehicle.vehicle_no

    stops = (
        await db.scalars(
            select(DeliveryDispatchStop)
            .where(DeliveryDispatchStop.trip_id == int(trip.id))
            .order_by(DeliveryDispatchStop.sequence.asc(), DeliveryDispatchStop.id.asc())
        )
    ).all()
    stop_by_order = {int(s.order_id): s for s in stops}

    if remove_order_ids:
        to_remove = validate_stop_removal(
            [int(s.order_id) for s in stops],
            remove_order_ids,
        )
        for oid in to_remove:
            stop = stop_by_order.get(oid)
            if not stop:
                continue
            items = (
                await db.scalars(
                    select(DeliveryDispatchItem).where(DeliveryDispatchItem.stop_id == int(stop.id))
                )
            ).all()
            for item in items:
                await db.delete(item)
            await db.delete(stop)
        changes["removed_orders"] = sorted(to_remove)
        stops = (
            await db.scalars(
                select(DeliveryDispatchStop)
                .where(DeliveryDispatchStop.trip_id == int(trip.id))
                .order_by(DeliveryDispatchStop.sequence.asc(), DeliveryDispatchStop.id.asc())
            )
        ).all()
        stop_by_order = {int(s.order_id): s for s in stops}

    if stop_order_ids is not None:
        desired = [int(x) for x in stop_order_ids]
        current_ids = [int(s.order_id) for s in stops]
        if len(desired) != len(set(desired)) or len(desired) != len(current_ids) or set(desired) != set(current_ids):
            raise ValueError("调序订单列表须与当前车次站点完全一致")
        for seq, oid in enumerate(desired, 1):
            stop_by_order[int(oid)].sequence = seq
        changes["reordered"] = True

    await recalculate_trip_stop_etas(db, trip, driver=driver)
    return changes
