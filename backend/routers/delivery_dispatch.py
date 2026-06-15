from datetime import date, datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models import (
    ClientCanteen,
    Delivery,
    DeliveryDevice,
    DeliveryDispatchItem,
    DeliveryDispatchStop,
    DeliveryDispatchTrip,
    DeliverySortScanRecord,
    DeliveryVehicle,
    DeliveryVehicleDeviceBinding,
    Order,
    OrderItemAllocation,
    OrderStatusLog,
    Product,
    Ticket,
    User,
)
from services.audit_service import write_audit_log
from services.beidou_client import (
    beidou_location_for_amap,
    beidou_online_status_from_raw,
    beidou_reported_at_display,
    enrich_beidou_devices_live,
)
from services.order_state_machine import ensure_order_transition
from services.outbox_service import add_outbox_event
from services.dispatch_occupancy import (
    ACTIVE_DISPATCH_TRIP_STATUSES,
    active_dispatch_trip_filters,
    cross_day_in_transit_warnings,
    trip_occupancy_label,
)
from services.dispatch_trip_edit import append_orders_to_trip, update_editable_trip
from services.storage.minio_client import upload_dispatch_exception_photo

router = APIRouter(prefix="/delivery", tags=["delivery-dispatch"])

ACTIVE_TRIP_STATUSES = set(ACTIVE_DISPATCH_TRIP_STATUSES)
TERMINAL_TRIP_STATUSES = {"已完成", "已取消"}
READY_ITEM_STATUSES = {"待装车", "已装车"}
FINAL_ITEM_STATUSES = {"已装车", "滞留未装", "取消随车", "供应商迟到", "质量问题", "现场缺货"}
REASON_STATUS_MAP = {
    "supplier_late": "供应商迟到",
    "not_shipped": "未出库",
    "quality": "质量问题",
    "missing": "现场缺货",
    "cancelled": "取消随车",
    "other": "滞留未装",
}
EDITABLE_TRIP_STATUSES = frozenset({"待发车", "有阻塞"})


class RoutePlanCommitIn(BaseModel):
    planning_date: date
    source: Literal["smart_route", "manual"] = "smart_route"
    vehicle_routes: list[dict[str, Any]] = Field(default_factory=list)
    risk_alerts: list[str] = Field(default_factory=list)
    planning_inputs_echo: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class ExceptionDepartItemIn(BaseModel):
    allocation_id: int
    reason_code: Literal["supplier_late", "not_shipped", "quality", "missing", "cancelled", "other"]
    reason_detail: str = ""
    attachments_json: list[str] = Field(default_factory=list)


class ExceptionDepartIn(BaseModel):
    reason_detail: str = Field(..., min_length=1)
    notify_customer: bool = True
    include_supplier_score: bool = True
    items: list[ExceptionDepartItemIn]


class CancelTripIn(BaseModel):
    reason: str = Field(..., min_length=1)


class AppendTripStopsIn(BaseModel):
    order_ids: list[int] = Field(..., min_length=1)


class UpdateDispatchTripIn(BaseModel):
    vehicle_id: Optional[int] = None
    stop_order_ids: Optional[list[int]] = None
    remove_order_ids: Optional[list[int]] = None


class DispatchItemLoadIn(BaseModel):
    loaded: bool = True


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_trip_action_status(status: str, action: str) -> None:
    current = str(status or "")
    if current in TERMINAL_TRIP_STATUSES:
        raise HTTPException(400, f"车次已{current.removeprefix('已')}，不能{action}")
    if current not in EDITABLE_TRIP_STATUSES:
        raise HTTPException(400, f"当前车次状态为{current or '未知'}，不能{action}")


def _collect_commit_order_ids(vehicle_routes: list[dict[str, Any]]) -> list[int]:
    order_ids: list[int] = []
    seen: set[int] = set()
    for vr in vehicle_routes:
        for stop in vr.get("stops") or []:
            oid = _safe_int(stop.get("order_id"))
            if not oid:
                continue
            if oid in seen:
                raise HTTPException(400, f"订单 #{oid} 在本次排线中重复出现，请重新生成路线")
            seen.add(oid)
            order_ids.append(oid)
    return sorted(order_ids)


def _validate_order_planning_date(order: Order, planning_date: date) -> None:
    if order.expected_delivery_date != planning_date:
        raise HTTPException(
            400,
            f"订单 {order.order_no} 配送日为 {order.expected_delivery_date or '未设置'}，"
            f"与计划日 {planning_date.isoformat()} 不一致",
        )


def _register_commit_vehicle(used_vehicle_ids: set[int], vehicle_id: int, vehicle_no: str) -> None:
    if vehicle_id in used_vehicle_ids:
        raise HTTPException(400, f"车辆 {vehicle_no} 在本次计划中被重复使用，请拆成不同车辆或取消重复车次")
    used_vehicle_ids.add(vehicle_id)


def _build_route_numbers(existing_route_nos: list[str], planning_date: date, count: int) -> list[str]:
    prefix = f"TR{planning_date.strftime('%Y%m%d')}-"
    max_sequence = 0
    for route_no in existing_route_nos:
        raw = str(route_no or "")
        if not raw.startswith(prefix):
            continue
        suffix = raw[len(prefix):]
        if suffix.isdigit():
            max_sequence = max(max_sequence, int(suffix))
    return [f"{prefix}{max_sequence + offset:02d}" for offset in range(1, count + 1)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _device_location(raw_payload: Any, vendor: str) -> tuple[Optional[float], Optional[float]]:
    raw = _as_dict(raw_payload)
    if str(vendor or "").lower() == "beidou":
        lng, lat, _stale = beidou_location_for_amap(raw)
        return lng, lat
    camera = _as_dict(raw.get("camera"))
    device = _as_dict(raw.get("device"))
    lng = (
        _safe_float(raw.get("lng"))
        or _safe_float(raw.get("longitude"))
        or _safe_float(camera.get("lng"))
        or _safe_float(camera.get("longitude"))
        or _safe_float(device.get("lng"))
        or _safe_float(device.get("longitude"))
    )
    lat = (
        _safe_float(raw.get("lat"))
        or _safe_float(raw.get("latitude"))
        or _safe_float(camera.get("lat"))
        or _safe_float(camera.get("latitude"))
        or _safe_float(device.get("lat"))
        or _safe_float(device.get("latitude"))
    )
    return lng, lat


def _device_reported_at(raw_payload: Any) -> str:
    raw = _as_dict(raw_payload)
    for key in ("reported_at", "updatetime", "update_time", "datetime", "server_time", "heart_time", "sys_time"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _device_online_status(device: DeliveryDevice) -> str:
    raw = _as_dict(device.raw_payload_json)
    for key in ("online", "is_online", "isOnline", "onlineStatus", "status"):
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip().lower()
        if text in {"1", "true", "online", "on"}:
            return "online"
        if text in {"0", "false", "offline", "off"}:
            return "offline"
    return "online" if str(device.status or "").lower() in {"active", "online"} else "offline"


def _first_route_point(route_path: Any) -> tuple[Optional[float], Optional[float]]:
    if not isinstance(route_path, list) or not route_path:
        return None, None
    first = route_path[0]
    if isinstance(first, (list, tuple)) and len(first) >= 2:
        return _safe_float(first[0]), _safe_float(first[1])
    if isinstance(first, dict):
        return _safe_float(first.get("lng") or first.get("longitude")), _safe_float(first.get("lat") or first.get("latitude"))
    return None, None


async def _vehicle_location_payload(db: AsyncSession, trip: DeliveryDispatchTrip) -> Optional[dict[str, Any]]:
    if trip.vehicle_id is None:
        return None
    devices = (
        await db.scalars(
            select(DeliveryDevice)
            .join(DeliveryVehicleDeviceBinding, DeliveryVehicleDeviceBinding.device_id == DeliveryDevice.id)
            .where(
                DeliveryVehicleDeviceBinding.vehicle_id == int(trip.vehicle_id),
                DeliveryVehicleDeviceBinding.delivery_id == int(trip.delivery_id),
            )
        )
    ).all()
    devices = sorted(devices, key=lambda d: 0 if str(d.vendor or "").lower() == "beidou" else 1)
    if devices:
        await enrich_beidou_devices_live(list(devices), db=db, persist=True)
    for device in devices:
        raw = _as_dict(device.raw_payload_json)
        lng, lat = _device_location(raw, str(device.vendor or ""))
        if lng is None or lat is None:
            continue
        vendor = str(device.vendor or "").lower()
        return {
            "lng": lng,
            "lat": lat,
            "label": trip.vehicle_no or device.device_name or "配送车辆",
            "source": str(device.vendor or ""),
            "online_status": beidou_online_status_from_raw(raw)
            if vendor == "beidou"
            else _device_online_status(device),
            "reported_at": beidou_reported_at_display(raw)
            if vendor == "beidou"
            else _device_reported_at(raw),
            "speed": raw.get("speed") or raw.get("velocity") or "",
            "course": raw.get("course") or raw.get("direction") or raw.get("angle") or "",
        }
    return None


async def _delivery_origin_payload(db: AsyncSession, trip: DeliveryDispatchTrip) -> dict[str, Any]:
    delivery = await db.scalar(select(User).where(User.id == int(trip.delivery_id)))
    if not delivery:
        return {"lng": None, "lat": None, "label": "配送商", "address": "", "type": "origin"}
    lng = _safe_float(delivery.lng)
    lat = _safe_float(delivery.lat)
    source = "delivery_profile"
    if lng is None or lat is None:
        lng, lat = _first_route_point(trip.route_path_json)
        source = "route_path"
    return {
        "lng": lng,
        "lat": lat,
        "label": delivery.company_name or delivery.username or "配送商",
        "address": delivery.address or "",
        "type": "origin",
        "geo_source": source if lng is not None and lat is not None else "missing",
    }


async def _stop_geo_maps(db: AsyncSession, stops: list[DeliveryDispatchStop]) -> dict[int, dict[str, Any]]:
    order_ids = [int(stop.order_id) for stop in stops if stop.order_id is not None]
    if not order_ids:
        return {}
    orders = (await db.scalars(select(Order).where(Order.id.in_(order_ids)))).all()
    order_by_id = {int(order.id): order for order in orders}
    canteen_ids = [int(order.canteen_id) for order in orders if order.canteen_id is not None]
    client_ids = [int(order.client_id) for order in orders if order.client_id is not None]
    canteens = (
        await db.scalars(select(ClientCanteen).where(ClientCanteen.id.in_(canteen_ids)))
        if canteen_ids
        else []
    )
    clients = (
        await db.scalars(select(User).where(User.id.in_(client_ids)))
        if client_ids
        else []
    )
    canteen_by_id = {int(canteen.id): canteen for canteen in canteens}
    client_by_id = {int(client.id): client for client in clients}
    result: dict[int, dict[str, Any]] = {}
    for stop in stops:
        order = order_by_id.get(int(stop.order_id))
        lng: Optional[float] = None
        lat: Optional[float] = None
        source = "missing"
        if order:
            lng = _safe_float(order.delivery_lng)
            lat = _safe_float(order.delivery_lat)
            if lng is not None and lat is not None:
                source = "order"
            else:
                canteen = canteen_by_id.get(int(order.canteen_id or 0))
                lng = _safe_float(canteen.lng if canteen else None)
                lat = _safe_float(canteen.lat if canteen else None)
                if lng is not None and lat is not None:
                    source = "canteen"
                else:
                    client = client_by_id.get(int(order.client_id or 0))
                    lng = _safe_float(client.lng if client else None)
                    lat = _safe_float(client.lat if client else None)
                    if lng is not None and lat is not None:
                        source = "client"
        result[int(stop.id)] = {"lng": lng, "lat": lat, "geo_source": source}
    return result


def _item_status_for_allocation(alloc: OrderItemAllocation, scanned_ids: set[int]) -> str:
    if str(alloc.status) != "已出库":
        return "未出库"
    if int(alloc.id) not in scanned_ids:
        return "未分检"
    return "待装车"


async def _trip_or_404(db: AsyncSession, trip_id: int, delivery_id: int) -> DeliveryDispatchTrip:
    trip = await db.scalar(
        select(DeliveryDispatchTrip).where(
            DeliveryDispatchTrip.id == trip_id,
            DeliveryDispatchTrip.delivery_id == delivery_id,
        )
    )
    if not trip:
        raise HTTPException(404, "车次不存在")
    return trip


async def _recompute_trip_counts(db: AsyncSession, trip: DeliveryDispatchTrip) -> None:
    items = (
        await db.scalars(
            select(DeliveryDispatchItem).where(DeliveryDispatchItem.trip_id == int(trip.id))
        )
    ).all()
    trip.total_allocations = len(items)
    trip.ready_count = len([i for i in items if str(i.status) in READY_ITEM_STATUSES])
    trip.blocked_count = len([i for i in items if str(i.status) not in READY_ITEM_STATUSES])
    trip.not_loaded_count = len([i for i in items if str(i.status) in FINAL_ITEM_STATUSES and str(i.status) != "已装车"])

    stop_ids = sorted({int(i.stop_id) for i in items})
    if stop_ids:
        stops = (
            await db.scalars(select(DeliveryDispatchStop).where(DeliveryDispatchStop.id.in_(stop_ids)))
        ).all()
        if stops and all(str(stop.status) == "已送达" for stop in stops):
            trip.status = "已完成"
            if trip.completed_at is None:
                trip.completed_at = datetime.utcnow()
            trip.updated_at = datetime.utcnow()
            return
        item_by_stop: dict[int, list[DeliveryDispatchItem]] = {}
        for item in items:
            item_by_stop.setdefault(int(item.stop_id), []).append(item)
        for stop in stops:
            if str(stop.status) == "已送达":
                continue
            related = item_by_stop.get(int(stop.id), [])
            blocked = any(str(i.status) not in READY_ITEM_STATUSES for i in related)
            not_loaded = any(str(i.status) in FINAL_ITEM_STATUSES and str(i.status) != "已装车" for i in related)
            stop.affected = bool(blocked or not_loaded)
            if str(trip.status) == "运输中":
                stop.status = "已发车" if any(str(i.status) == "已装车" for i in related) else "未随车"
            elif blocked:
                stop.status = "有阻塞"
            else:
                stop.status = "待发车"

    if str(trip.status) not in {"运输中", *TERMINAL_TRIP_STATUSES}:
        trip.status = "有阻塞" if trip.blocked_count > 0 else "待发车"
    trip.updated_at = datetime.utcnow()


async def _refresh_item_readiness(db: AsyncSession, trip: DeliveryDispatchTrip) -> list[DeliveryDispatchItem]:
    items = (
        await db.scalars(
            select(DeliveryDispatchItem).where(DeliveryDispatchItem.trip_id == int(trip.id))
        )
    ).all()
    if not items:
        return []
    allocation_ids = [int(i.allocation_id) for i in items]
    allocs = (
        await db.scalars(
            select(OrderItemAllocation).where(OrderItemAllocation.id.in_(allocation_ids))
        )
    ).all()
    alloc_map = {int(a.id): a for a in allocs}
    scanned_ids = set(
        (
            await db.scalars(
                select(DeliverySortScanRecord.allocation_id).where(
                    DeliverySortScanRecord.allocation_id.in_(allocation_ids)
                )
            )
        ).all()
    )
    for item in items:
        if str(item.status) in FINAL_ITEM_STATUSES:
            continue
        alloc = alloc_map.get(int(item.allocation_id))
        if not alloc:
            item.status = "滞留未装"
            item.reason_code = "missing_allocation"
            item.reason_detail = "分单不存在或已被删除"
            continue
        item.status = _item_status_for_allocation(alloc, scanned_ids)
        item.updated_at = datetime.utcnow()
    await _recompute_trip_counts(db, trip)
    return items


async def _load_trip_payload(db: AsyncSession, trip: DeliveryDispatchTrip) -> dict[str, Any]:
    stops = (
        await db.scalars(
            select(DeliveryDispatchStop)
            .where(DeliveryDispatchStop.trip_id == int(trip.id))
            .order_by(DeliveryDispatchStop.sequence.asc(), DeliveryDispatchStop.id.asc())
        )
    ).all()
    items = (
        await db.scalars(
            select(DeliveryDispatchItem)
            .where(DeliveryDispatchItem.trip_id == int(trip.id))
            .order_by(DeliveryDispatchItem.supplier_name.asc(), DeliveryDispatchItem.id.asc())
        )
    ).all()
    item_by_stop: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        item_by_stop.setdefault(int(item.stop_id), []).append(_serialize_item(item))
    stop_geo = await _stop_geo_maps(db, stops)
    vehicle_location = await _vehicle_location_payload(db, trip)
    delivery_origin = await _delivery_origin_payload(db, trip)
    return {
        **_serialize_trip(trip),
        "delivery_origin": delivery_origin,
        "route_path": trip.route_path_json or [],
        "vehicle_location": vehicle_location,
        "stops": [
            {
                **_serialize_stop(stop),
                **stop_geo.get(int(stop.id), {"lng": None, "lat": None, "geo_source": "missing"}),
                "items": item_by_stop.get(int(stop.id), []),
            }
            for stop in stops
        ],
        "items": [_serialize_item(item) for item in items],
        "supplier_groups": _supplier_groups(items),
    }


def _serialize_trip(trip: DeliveryDispatchTrip) -> dict[str, Any]:
    return {
        "id": int(trip.id),
        "route_no": trip.route_no,
        "delivery_id": int(trip.delivery_id),
        "planning_date": trip.planning_date.isoformat() if trip.planning_date else None,
        "source": trip.source,
        "status": trip.status,
        "depart_mode": trip.depart_mode,
        "vehicle_id": int(trip.vehicle_id) if trip.vehicle_id is not None else None,
        "vehicle_no": trip.vehicle_no,
        "driver_name": trip.driver_name,
        "departure_time": trip.departure_time,
        "total_orders": int(trip.total_orders or 0),
        "total_allocations": int(trip.total_allocations or 0),
        "ready_count": int(trip.ready_count or 0),
        "blocked_count": int(trip.blocked_count or 0),
        "not_loaded_count": int(trip.not_loaded_count or 0),
        "distance_km": trip.distance_km,
        "duration_minutes": trip.duration_minutes,
        "load_weight_kg": trip.load_weight_kg,
        "load_volume_m3": trip.load_volume_m3,
        "risk_alerts": trip.risk_alerts_json or [],
        "exception_summary": trip.exception_summary_json or {},
        "driver_app": {
            "visible": bool((trip.vehicle_no or "").strip()),
            "login_vehicle_no": trip.vehicle_no,
            "login_password_hint": "demo123",
            "can_start": str(trip.status) == "运输中",
            "hint": (
                "司机端可开始配送并确认送达"
                if str(trip.status) == "运输中"
                else "司机端可查看车次，调度端发车后才能开始配送"
                if (trip.vehicle_no or "").strip()
                else "当前车次未绑定车牌，司机端不可见"
            ),
        },
        "departed_at": trip.departed_at.isoformat() if trip.departed_at else None,
        "created_at": trip.created_at.isoformat() if trip.created_at else None,
        "updated_at": trip.updated_at.isoformat() if trip.updated_at else None,
        "occupancy_label": trip_occupancy_label(str(trip.status)),
        "occupancy_active": str(trip.status) in ACTIVE_DISPATCH_TRIP_STATUSES,
    }


def _serialize_stop(stop: DeliveryDispatchStop) -> dict[str, Any]:
    return {
        "id": int(stop.id),
        "trip_id": int(stop.trip_id),
        "order_id": int(stop.order_id),
        "sequence": int(stop.sequence),
        "order_no": stop.order_no,
        "client_name": stop.client_name,
        "canteen_name": stop.canteen_name,
        "address": stop.address,
        "expected_delivery_date": stop.expected_delivery_date.isoformat() if stop.expected_delivery_date else None,
        "expected_delivery_slot": stop.expected_delivery_slot,
        "planned_arrive_time": stop.planned_arrive_time,
        "planned_leave_time": stop.planned_leave_time,
        "status": stop.status,
        "affected": bool(stop.affected),
    }


def _serialize_item(item: DeliveryDispatchItem) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "trip_id": int(item.trip_id),
        "stop_id": int(item.stop_id),
        "allocation_id": int(item.allocation_id),
        "order_id": int(item.order_id),
        "supplier_id": int(item.supplier_id),
        "product_id": int(item.product_id),
        "product_name": item.product_name,
        "spec_unit": item.spec_unit,
        "quantity": float(item.quantity or 0),
        "unit": item.unit,
        "supplier_name": item.supplier_name,
        "status": item.status,
        "reason_code": item.reason_code,
        "reason_detail": item.reason_detail,
        "attachments_json": item.attachments_json or [],
        "loaded_at": item.loaded_at.isoformat() if item.loaded_at else None,
    }


def _supplier_groups(items: list[DeliveryDispatchItem]) -> list[dict[str, Any]]:
    groups: dict[int, dict[str, Any]] = {}
    for item in items:
        g = groups.setdefault(
            int(item.supplier_id),
            {
                "supplier_id": int(item.supplier_id),
                "supplier_name": item.supplier_name,
                "total": 0,
                "loaded": 0,
                "blocked": 0,
                "not_loaded": 0,
            },
        )
        g["total"] += 1
        if str(item.status) == "已装车":
            g["loaded"] += 1
        elif str(item.status) in READY_ITEM_STATUSES:
            pass
        else:
            g["blocked"] += 1
        if str(item.status) in FINAL_ITEM_STATUSES and str(item.status) != "已装车":
            g["not_loaded"] += 1
    return sorted(groups.values(), key=lambda x: (x["blocked"] <= 0, x["supplier_id"]))


async def _trip_route_numbers(
    db: AsyncSession,
    delivery_id: int,
    planning_date: date,
    count: int,
) -> list[str]:
    existing = (
        await db.scalars(
            select(DeliveryDispatchTrip.route_no).where(
                DeliveryDispatchTrip.delivery_id == delivery_id,
                DeliveryDispatchTrip.planning_date == planning_date,
            )
        )
    ).all()
    return _build_route_numbers(list(existing), planning_date, count)


async def _mark_orders_departed(
    db: AsyncSession,
    *,
    trip: DeliveryDispatchTrip,
    order_ids: set[int],
    actor_user_id: int,
) -> None:
    if not order_ids:
        return
    orders = (
        await db.scalars(select(Order).where(Order.id.in_(list(order_ids))))
    ).all()
    for order in orders:
        old_status = str(order.status)
        if old_status != "发货":
            ensure_order_transition(old_status, "发货")
            order.status = "发货"
            order.version += 1
            order.updated_at = datetime.utcnow()
            db.add(
                OrderStatusLog(
                    order_id=int(order.id),
                    old_status=old_status,
                    new_status="发货",
                    actor_user_id=actor_user_id,
                )
            )
            await add_outbox_event(
                db=db,
                event_type="order_status_change",
                payload={
                    "order_id": int(order.id),
                    "order_no": order.order_no,
                    "old_status": old_status,
                    "new_status": "发货",
                },
                channel="monitor",
            )
        delivery = await db.scalar(select(Delivery).where(Delivery.order_id == int(order.id)))
        if not delivery:
            db.add(
                Delivery(
                    order_id=int(order.id),
                    driver_name=trip.driver_name or "待填写",
                    vehicle_no=trip.vehicle_no or "待填写",
                    route_json=trip.route_path_json or [],
                    departed_at=trip.departed_at or datetime.utcnow(),
                    status="运输中",
                )
            )
        else:
            delivery.driver_name = trip.driver_name or delivery.driver_name
            delivery.vehicle_no = trip.vehicle_no or delivery.vehicle_no
            delivery.route_json = trip.route_path_json or delivery.route_json or []
            delivery.departed_at = trip.departed_at or datetime.utcnow()
            delivery.status = "运输中"


@router.post("/route-plan/commit")
async def commit_route_plan(
    payload: RoutePlanCommitIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    if not payload.vehicle_routes:
        raise HTTPException(400, "请先生成智能路线后再保存发车计划")

    order_ids = _collect_commit_order_ids(payload.vehicle_routes)
    if not order_ids:
        raise HTTPException(400, "路线中没有可保存的订单停靠点")
    echo_date = str((payload.planning_inputs_echo or {}).get("planning_date") or "").strip()
    if echo_date and echo_date != payload.planning_date.isoformat():
        raise HTTPException(400, "排线结果的计划日期已变化，请重新生成路线后再保存")

    orders = (
        await db.scalars(
            select(Order).where(Order.id.in_(order_ids)).order_by(Order.id.asc())
        )
    ).all()
    order_map = {int(o.id): o for o in orders}
    if len(order_map) != len(order_ids):
        raise HTTPException(404, "部分订单不存在")
    for order in orders:
        if int(order.delivery_id) != int(user.id):
            raise HTTPException(403, f"订单 {order.order_no} 不属于当前配送商")
        if str(order.status) != "配货":
            raise HTTPException(400, f"订单 {order.order_no} 尚未进入配货状态，请先完成智能分单后再保存发车计划")
        _validate_order_planning_date(order, payload.planning_date)

    active_rows = (
        await db.execute(
            select(DeliveryDispatchStop.order_id, DeliveryDispatchTrip.route_no)
            .join(DeliveryDispatchTrip, DeliveryDispatchTrip.id == DeliveryDispatchStop.trip_id)
            .where(
                DeliveryDispatchStop.order_id.in_(order_ids),
                *active_dispatch_trip_filters(
                    delivery_id=int(user.id),
                    planning_date=payload.planning_date,
                ),
            )
        )
    ).all()
    if active_rows:
        oid, route_no = active_rows[0]
        raise HTTPException(
            400,
            f"订单 #{int(oid)} 已在 {payload.planning_date.isoformat()} 的未完成车次 {route_no} 中，请先取消旧车次",
        )

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
            select(OrderItemAllocation)
            .where(OrderItemAllocation.order_id.in_(order_ids))
            .order_by(OrderItemAllocation.order_id.asc(), OrderItemAllocation.line_no.asc(), OrderItemAllocation.id.asc())
        )
    ).all()
    product_ids = sorted({int(a.product_id) for a in allocs})
    supplier_ids = sorted({int(a.supplier_id) for a in allocs})
    products = (await db.scalars(select(Product).where(Product.id.in_(product_ids)))).all() if product_ids else []
    suppliers = (await db.scalars(select(User).where(User.id.in_(supplier_ids)))).all() if supplier_ids else []
    product_map = {int(p.id): p for p in products}
    supplier_map = {int(s.id): s for s in suppliers}
    allocs_by_order: dict[int, list[OrderItemAllocation]] = {}
    for alloc in allocs:
        allocs_by_order.setdefault(int(alloc.order_id), []).append(alloc)
    for order in orders:
        if not allocs_by_order.get(int(order.id)):
            raise HTTPException(400, f"订单 {order.order_no} 尚未生成分单，不能保存到发车计划")
    scanned_ids = (
        set(
            (
                await db.scalars(
                    select(DeliverySortScanRecord.allocation_id).where(
                        DeliverySortScanRecord.allocation_id.in_([int(a.id) for a in allocs])
                    )
                )
            ).all()
        )
        if allocs
        else set()
    )

    created: list[DeliveryDispatchTrip] = []
    now = datetime.utcnow()
    used_vehicle_ids: set[int] = set()
    route_numbers = await _trip_route_numbers(
        db,
        int(user.id),
        payload.planning_date,
        len(payload.vehicle_routes),
    )
    for idx, vr in enumerate(payload.vehicle_routes, 1):
        stops_raw = [s for s in (vr.get("stops") or []) if _safe_int(s.get("order_id")) in order_map]
        if not stops_raw:
            continue
        vehicle_id = _safe_int(vr.get("vehicle_id"))
        if vehicle_id is not None and vehicle_id <= 0:
            vehicle_id = None
        vehicle_no = str(vr.get("vehicle_no") or "").strip()
        driver_name = str(vr.get("driver_name") or "").strip()
        vehicle: DeliveryVehicle | None = None
        if vehicle_id:
            vehicle = await db.scalar(
                select(DeliveryVehicle).where(
                    DeliveryVehicle.id == vehicle_id,
                    DeliveryVehicle.delivery_id == int(user.id),
                    DeliveryVehicle.status == "active",
                )
            )
            if not vehicle:
                raise HTTPException(400, f"第 {idx} 个车次绑定的车辆不存在或已停用，请重新生成路线")
        elif vehicle_no:
            vehicle = await db.scalar(
                select(DeliveryVehicle).where(
                    DeliveryVehicle.delivery_id == int(user.id),
                    DeliveryVehicle.vehicle_no == vehicle_no,
                    DeliveryVehicle.status == "active",
                )
            )
            if not vehicle:
                raise HTTPException(400, f"车牌 {vehicle_no} 未在车辆管理中登记或已停用，司机端无法登录查看")
        else:
            raise HTTPException(400, f"第 {idx} 个车次未绑定车辆，不能保存为发车计划")
        vehicle_id = int(vehicle.id)
        vehicle_no = vehicle.vehicle_no
        driver_name = driver_name or str(vehicle.driver_name or "")
        _register_commit_vehicle(used_vehicle_ids, vehicle_id, vehicle_no)
        active_vehicle_trip = await db.scalar(
            select(DeliveryDispatchTrip)
            .where(
                *active_dispatch_trip_filters(
                    delivery_id=int(user.id),
                    planning_date=payload.planning_date,
                ),
                (
                    (DeliveryDispatchTrip.vehicle_id == vehicle_id)
                    | (DeliveryDispatchTrip.vehicle_no == vehicle_no)
                ),
            )
            .order_by(DeliveryDispatchTrip.id.desc())
        )
        if active_vehicle_trip:
            raise HTTPException(
                400,
                f"车辆 {vehicle_no} 已被 {payload.planning_date.isoformat()} 的未完成车次 "
                f"{active_vehicle_trip.route_no} 占用，请先完成或取消旧车次",
            )
        route_no = route_numbers[idx - 1]
        departure_time = ""
        effective = (payload.planning_inputs_echo or {}).get("departure_time_by_vehicle_no_effective") or {}
        if vehicle_no and isinstance(effective, dict):
            departure_time = str(effective.get(vehicle_no) or "")
        departure_time = departure_time or str((payload.planning_inputs_echo or {}).get("departure_time_local") or "")
        trip = DeliveryDispatchTrip(
            route_no=route_no,
            delivery_id=int(user.id),
            planning_date=payload.planning_date,
            source=payload.source,
            status="待发车",
            vehicle_id=vehicle_id,
            vehicle_no=vehicle_no,
            driver_name=driver_name,
            departure_time=departure_time,
            total_orders=len({int(s.get("order_id")) for s in stops_raw}),
            distance_km=_safe_float(vr.get("distance_km")),
            duration_minutes=_safe_int(vr.get("duration_minutes")),
            load_weight_kg=_safe_float(vr.get("load_weight_kg")),
            load_volume_m3=_safe_float(vr.get("load_volume_m3")),
            route_path_json=vr.get("route_path") or [],
            risk_alerts_json=payload.risk_alerts or [],
            planning_snapshot_json={"vehicle_route": vr, "inputs": payload.planning_inputs_echo or {}, "note": payload.note},
            created_by=int(user.id),
            created_at=now,
            updated_at=now,
        )
        db.add(trip)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(409, "车次号或发车计划发生并发冲突，请刷新后重新保存") from exc
        created.append(trip)

        stop_by_order: dict[int, DeliveryDispatchStop] = {}
        for fallback_seq, stop_raw in enumerate(stops_raw, 1):
            order = order_map[int(stop_raw.get("order_id"))]
            client = client_map.get(int(order.client_id)) if order.client_id else None
            canteen = canteen_map.get(int(order.canteen_id)) if order.canteen_id else None
            seq = _safe_int(stop_raw.get("sequence")) or fallback_seq
            stop = DeliveryDispatchStop(
                trip_id=int(trip.id),
                order_id=int(order.id),
                sequence=seq,
                order_no=order.order_no,
                client_name=str(stop_raw.get("client_name") or (client.company_name if client else "") or f"客户#{order.client_id}"),
                canteen_name=str(canteen.name if canteen else ""),
                address=str(stop_raw.get("address") or order.delivery_address or ""),
                expected_delivery_date=order.expected_delivery_date,
                expected_delivery_slot=order.expected_delivery_slot or "",
                planned_arrive_time=str(stop_raw.get("planned_arrive_time") or ""),
                planned_leave_time=str(stop_raw.get("planned_leave_time") or ""),
                status="待发车",
                created_at=now,
                updated_at=now,
            )
            db.add(stop)
            await db.flush()
            stop_by_order[int(order.id)] = stop

        for order_id, stop in stop_by_order.items():
            for alloc in allocs_by_order.get(order_id, []):
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
                        supplier_name=str((supplier.company_name or supplier.username) if supplier else f"供货商#{int(alloc.supplier_id)}"),
                        status=_item_status_for_allocation(alloc, scanned_ids),
                        created_at=now,
                        updated_at=now,
                    )
                )
        await db.flush()
        await _recompute_trip_counts(db, trip)

    if not created:
        raise HTTPException(400, "没有生成任何有效车次")
    commit_warnings = await cross_day_in_transit_warnings(
        db,
        delivery_id=int(user.id),
        planning_date=payload.planning_date,
        vehicle_ids=[int(t.vehicle_id) for t in created if t.vehicle_id],
        vehicle_nos=[str(t.vehicle_no) for t in created if t.vehicle_no],
    )
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="delivery_route_plan_commit",
        category="delivery",
        object_type="delivery_dispatch_trip",
        object_id=int(created[0].id),
        detail=(
            f"{'手动调度' if payload.source == 'manual' else '保存智能排线'}为发车计划，"
            f"共 {len(created)} 个车次"
        ),
        after_json={"trip_ids": [int(t.id) for t in created], "route_nos": [t.route_no for t in created]},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "车次号或发车计划发生并发冲突，请刷新后重新保存") from exc
    return {"message": "已保存为发车计划", "trips": [_serialize_trip(t) for t in created], "warnings": commit_warnings}


@router.get("/dispatch-trips")
async def list_dispatch_trips(
    planning_date: Optional[date] = Query(default=None),
    status: Optional[str] = Query(default=None),
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DeliveryDispatchTrip).where(DeliveryDispatchTrip.delivery_id == int(user.id))
    if planning_date:
        stmt = stmt.where(DeliveryDispatchTrip.planning_date == planning_date)
    if status and status.strip():
        stmt = stmt.where(DeliveryDispatchTrip.status == status.strip())
    rows = (
        await db.scalars(
            stmt.order_by(DeliveryDispatchTrip.planning_date.desc(), DeliveryDispatchTrip.id.desc())
        )
    ).all()
    return [_serialize_trip(row) for row in rows]


@router.get("/dispatch-planning/summary")
async def dispatch_planning_summary(
    planning_date: date = Query(..., description="计划日期 YYYY-MM-DD"),
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    """计划日排线概览：未排入车次订单数、可用车辆数、活跃车次。"""
    delivery_id = int(user.id)
    active_trips = (
        await db.scalars(
            select(DeliveryDispatchTrip).where(
                *active_dispatch_trip_filters(
                    delivery_id=delivery_id,
                    planning_date=planning_date,
                ),
            )
        )
    ).all()
    occupied_vehicle_ids: set[int] = set()
    occupied_vehicle_nos: set[str] = set()
    for t in active_trips:
        if t.vehicle_id is not None:
            occupied_vehicle_ids.add(int(t.vehicle_id))
        vn = str(t.vehicle_no or "").strip()
        if vn:
            occupied_vehicle_nos.add(vn)

    from models import DeliveryVehicle

    vehicles = (
        await db.scalars(
            select(DeliveryVehicle).where(
                DeliveryVehicle.delivery_id == delivery_id,
                DeliveryVehicle.status == "active",
            )
        )
    ).all()
    available_vehicles = [
        v
        for v in vehicles
        if int(v.id) not in occupied_vehicle_ids and str(v.vehicle_no or "").strip() not in occupied_vehicle_nos
    ]

    active_order_subq = (
        select(DeliveryDispatchStop.order_id)
        .join(DeliveryDispatchTrip, DeliveryDispatchTrip.id == DeliveryDispatchStop.trip_id)
        .where(
            *active_dispatch_trip_filters(
                delivery_id=delivery_id,
                planning_date=planning_date,
            ),
        )
    )
    unplanned_count = await db.scalar(
        select(func.count(Order.id)).where(
            Order.delivery_id == delivery_id,
            Order.expected_delivery_date == planning_date,
            Order.status.in_(("下单", "配货")),
            Order.id.not_in(active_order_subq),
        )
    )

    return {
        "planning_date": planning_date.isoformat(),
        "unplanned_order_count": int(unplanned_count or 0),
        "active_trip_count": len(active_trips),
        "vehicles_active_total": len(vehicles),
        "vehicles_available_count": len(available_vehicles),
        "vehicles_occupied_count": len(vehicles) - len(available_vehicles),
    }


@router.get("/dispatch-trips/{trip_id}")
async def get_dispatch_trip(
    trip_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    await _refresh_item_readiness(db, trip)
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.post("/dispatch-trips/{trip_id}/exception-photo")
async def upload_dispatch_exception_evidence(
    trip_id: int,
    file: UploadFile = File(...),
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    url = await upload_dispatch_exception_photo(file)
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="delivery_dispatch_exception_photo",
        category="delivery",
        object_type="delivery_dispatch_trip",
        object_id=int(trip.id),
        detail=f"车次 {trip.route_no} 上传异常发车证据照片",
        after_json={"url": url},
    )
    await db.commit()
    return {"message": "ok", "url": url}


@router.get("/driver-trips/today")
async def list_driver_trips_today(
    planning_date: Optional[date] = Query(None),
    driver_name: str = Query(""),
    vehicle_no: str = Query(""),
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    target_date = planning_date or date.today()
    stmt = (
        select(DeliveryDispatchTrip)
        .where(
            DeliveryDispatchTrip.delivery_id == int(user.id),
            DeliveryDispatchTrip.planning_date == target_date,
            DeliveryDispatchTrip.status.in_(["待发车", "有阻塞", "运输中"]),
        )
        .order_by(DeliveryDispatchTrip.departure_time.asc(), DeliveryDispatchTrip.id.asc())
    )
    if driver_name.strip():
        stmt = stmt.where(DeliveryDispatchTrip.driver_name == driver_name.strip())
    if vehicle_no.strip():
        stmt = stmt.where(DeliveryDispatchTrip.vehicle_no == vehicle_no.strip())
    rows = (await db.scalars(stmt)).all()
    for trip in rows:
        await _refresh_item_readiness(db, trip)
    await db.commit()
    return {"date": target_date.isoformat(), "trips": [_serialize_trip(row) for row in rows]}


@router.get("/driver-trips/{trip_id}/loading-list")
async def get_driver_loading_list(
    trip_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    await _refresh_item_readiness(db, trip)
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.post("/dispatch-trips/{trip_id}/items/{item_id}/load")
async def mark_dispatch_item_loaded(
    trip_id: int,
    item_id: int,
    payload: DispatchItemLoadIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    if str(trip.status) == "运输中":
        raise HTTPException(400, "车次已发车，不能修改装车状态")
    await _refresh_item_readiness(db, trip)
    item = await db.scalar(
        select(DeliveryDispatchItem).where(
            DeliveryDispatchItem.id == item_id,
            DeliveryDispatchItem.trip_id == int(trip.id),
        )
    )
    if not item:
        raise HTTPException(404, "装车分单不存在")
    if str(item.status) not in READY_ITEM_STATUSES:
        raise HTTPException(400, f"当前分单状态为 {item.status}，不能标记装车")

    now = datetime.utcnow()
    item.status = "已装车" if payload.loaded else "待装车"
    item.loaded_at = now if payload.loaded else None
    item.updated_at = now
    await _recompute_trip_counts(db, trip)
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.post("/dispatch-trips/{trip_id}/depart")
async def depart_dispatch_trip(
    trip_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    if str(trip.status) == "运输中":
        return await _load_trip_payload(db, trip)
    _validate_trip_action_status(str(trip.status), "发车")
    items = await _refresh_item_readiness(db, trip)
    blockers = [i for i in items if str(i.status) not in READY_ITEM_STATUSES]
    if blockers:
        raise HTTPException(400, f"仍有 {len(blockers)} 个分单未满足发车条件，请处理后再发车或使用异常发车")

    now = datetime.utcnow()
    for item in items:
        if str(item.status) != "已装车":
            item.status = "已装车"
            item.loaded_at = now
            item.updated_at = now
    trip.status = "运输中"
    trip.depart_mode = "normal"
    trip.departed_at = now
    trip.updated_at = now
    await _recompute_trip_counts(db, trip)
    await _mark_orders_departed(
        db,
        trip=trip,
        order_ids={int(i.order_id) for i in items},
        actor_user_id=int(user.id),
    )
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="delivery_dispatch_depart",
        category="delivery",
        object_type="delivery_dispatch_trip",
        object_id=int(trip.id),
        detail=f"车次 {trip.route_no} 整车发车",
    )
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.post("/dispatch-trips/{trip_id}/exception-depart")
async def exception_depart_dispatch_trip(
    trip_id: int,
    payload: ExceptionDepartIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    if str(trip.status) == "运输中":
        raise HTTPException(400, "车次已发车，不能重复异常发车")
    _validate_trip_action_status(str(trip.status), "异常发车")
    items = await _refresh_item_readiness(db, trip)
    reason_by_alloc = {int(i.allocation_id): i for i in payload.items}
    blockers = [i for i in items if str(i.status) not in READY_ITEM_STATUSES]
    missing_reason = [i for i in blockers if int(i.allocation_id) not in reason_by_alloc]
    if missing_reason:
        raise HTTPException(400, f"仍有 {len(missing_reason)} 个阻塞分单未填写异常原因")

    now = datetime.utcnow()
    not_loaded_order_ids: set[int] = set()
    loaded_order_ids: set[int] = set()
    attachments: list[str] = []
    for item in items:
        reason = reason_by_alloc.get(int(item.allocation_id))
        if reason:
            item.status = REASON_STATUS_MAP.get(reason.reason_code, "滞留未装")
            item.reason_code = reason.reason_code
            item.reason_detail = reason.reason_detail or payload.reason_detail
            item.attachments_json = reason.attachments_json or []
            item.updated_at = now
            not_loaded_order_ids.add(int(item.order_id))
            attachments.extend(reason.attachments_json or [])
        elif str(item.status) in READY_ITEM_STATUSES:
            if str(item.status) != "已装车":
                item.status = "已装车"
                item.loaded_at = now
                item.updated_at = now
            loaded_order_ids.add(int(item.order_id))
    if not loaded_order_ids:
        raise HTTPException(400, "当前车次没有可随车发出的分单，请取消车次或重新排线")

    trip.status = "运输中"
    trip.depart_mode = "exception"
    trip.departed_at = now
    trip.exception_summary_json = {
        "reason_detail": payload.reason_detail,
        "notify_customer": payload.notify_customer,
        "include_supplier_score": payload.include_supplier_score,
        "not_loaded_order_ids": sorted(not_loaded_order_ids),
        "not_loaded_count": len(reason_by_alloc),
    }
    trip.updated_at = now
    await _recompute_trip_counts(db, trip)
    await _mark_orders_departed(
        db,
        trip=trip,
        order_ids=loaded_order_ids,
        actor_user_id=int(user.id),
    )

    affected_order_ids = sorted(not_loaded_order_ids | loaded_order_ids)
    for oid in affected_order_ids:
        db.add(
            Ticket(
                order_id=oid,
                type="配送异常",
                description=(
                    f"车次 {trip.route_no} 异常发车：{payload.reason_detail}。"
                    f"未随车分单数 {len(reason_by_alloc)}，已同步调度留痕。"
                ),
                status="待处理",
                attachments_json=attachments[:5] if attachments else None,
                assigned_delivery_id=int(user.id),
                created_by=int(user.id),
                flow_logs_json=[
                    {
                        "action": "exception_depart",
                        "trip_id": int(trip.id),
                        "route_no": trip.route_no,
                        "at": now.isoformat(),
                    }
                ],
            )
        )
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="delivery_dispatch_exception_depart",
        category="delivery",
        object_type="delivery_dispatch_trip",
        object_id=int(trip.id),
        detail=f"车次 {trip.route_no} 异常发车",
        after_json=trip.exception_summary_json,
    )
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.post("/dispatch-trips/{trip_id}/append-stops")
async def append_dispatch_trip_stops(
    trip_id: int,
    payload: AppendTripStopsIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    driver = await db.scalar(select(User).where(User.id == int(user.id)))
    order_ids = sorted({int(x) for x in payload.order_ids if int(x) > 0})
    if not order_ids:
        raise HTTPException(400, "请至少选择一个订单")
    allocs = (
        await db.scalars(select(OrderItemAllocation).where(OrderItemAllocation.order_id.in_(order_ids)))
    ).all()
    scanned_ids = (
        set(
            (
                await db.scalars(
                    select(DeliverySortScanRecord.allocation_id).where(
                        DeliverySortScanRecord.allocation_id.in_([int(a.id) for a in allocs])
                    )
                )
            ).all()
        )
        if allocs
        else set()
    )
    try:
        await append_orders_to_trip(
            db,
            trip=trip,
            delivery_id=int(user.id),
            order_ids=order_ids,
            driver=driver,
            item_status_fn=_item_status_for_allocation,
            scanned_ids=scanned_ids,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await _recompute_trip_counts(db, trip)
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="delivery_dispatch_append_stops",
        category="delivery",
        object_type="delivery_dispatch_trip",
        object_id=int(trip.id),
        detail=f"车次 {trip.route_no} 追加 {len(order_ids)} 个站点",
        after_json={"order_ids": order_ids},
    )
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.patch("/dispatch-trips/{trip_id}")
async def update_dispatch_trip(
    trip_id: int,
    payload: UpdateDispatchTripIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    driver = await db.scalar(select(User).where(User.id == int(user.id)))
    if (
        payload.vehicle_id is None
        and payload.stop_order_ids is None
        and not payload.remove_order_ids
    ):
        raise HTTPException(400, "请至少指定换车、调序或移除站点")
    try:
        changes = await update_editable_trip(
            db,
            trip=trip,
            delivery_id=int(user.id),
            driver=driver,
            vehicle_id=payload.vehicle_id,
            stop_order_ids=payload.stop_order_ids,
            remove_order_ids=payload.remove_order_ids or None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await _recompute_trip_counts(db, trip)
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="delivery_dispatch_update_trip",
        category="delivery",
        object_type="delivery_dispatch_trip",
        object_id=int(trip.id),
        detail=f"编辑车次 {trip.route_no}",
        after_json=changes,
    )
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.post("/dispatch-trips/{trip_id}/cancel")
async def cancel_dispatch_trip(
    trip_id: int,
    payload: CancelTripIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_or_404(db, trip_id, int(user.id))
    _validate_trip_action_status(str(trip.status), "取消")
    trip.status = "已取消"
    trip.exception_summary_json = {"cancel_reason": payload.reason}
    trip.updated_at = datetime.utcnow()
    await write_audit_log(
        db=db,
        actor_user_id=int(user.id),
        action="delivery_dispatch_cancel",
        category="delivery",
        object_type="delivery_dispatch_trip",
        object_id=int(trip.id),
        detail=f"取消车次 {trip.route_no}：{payload.reason}",
    )
    await db.commit()
    return _serialize_trip(trip)
