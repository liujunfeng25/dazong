from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from dependencies import bearer_scheme, decode_access_token
from models import (
    Delivery,
    DeliveryDispatchStop,
    DeliveryDispatchTrip,
    DeliveryVehicle,
    Order,
    OrderStatusLog,
    User,
)
from routers.delivery_dispatch import _load_trip_payload, _refresh_item_readiness, _serialize_trip
from services.audit_service import write_audit_log
from services.event_bus import publish_monitor_event, publish_role_order_update
from services.notification_service import push_notification
from services.order_state_machine import ensure_order_transition
from services.outbox_service import add_outbox_event
from services.ticket_service import close_delivery_overdue_alert_if_delivered, close_delivery_overdue_ticket_if_delivered

router = APIRouter(prefix="/driver", tags=["driver"])


class DriverLoginIn(BaseModel):
    vehicle_no: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=64)


class DriverContext(BaseModel):
    vehicle_id: int
    vehicle_no: str
    driver_name: str = ""
    delivery_id: int
    delivery_name: str = ""


def _create_driver_token(vehicle: DeliveryVehicle, delivery: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": f"vehicle:{int(vehicle.id)}",
        "token_type": "driver",
        "vehicle_id": int(vehicle.id),
        "vehicle_no": vehicle.vehicle_no,
        "driver_name": vehicle.driver_name or "",
        "delivery_id": int(delivery.id),
        "role": "driver",
        "exp": expires,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def _driver_context(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> DriverContext:
    try:
        payload = decode_access_token(credentials.credentials)
        if payload.get("token_type") != "driver":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "司机令牌无效")
        vehicle_id = int(payload.get("vehicle_id") or 0)
    except (JWTError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "司机令牌无效或已过期") from exc
    vehicle = await db.scalar(select(DeliveryVehicle).where(DeliveryVehicle.id == vehicle_id))
    if not vehicle or str(vehicle.status) != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "车辆不存在或已停用")
    delivery = await db.scalar(
        select(User).where(User.id == int(vehicle.delivery_id), User.role == "delivery", User.status == "active")
    )
    if not delivery:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "配送商账号不存在或已停用")
    return DriverContext(
        vehicle_id=int(vehicle.id),
        vehicle_no=vehicle.vehicle_no,
        driver_name=vehicle.driver_name or "",
        delivery_id=int(delivery.id),
        delivery_name=delivery.company_name or delivery.username or "",
    )


async def _trip_for_driver(db: AsyncSession, trip_id: int, ctx: DriverContext) -> DeliveryDispatchTrip:
    trip = await db.scalar(
        select(DeliveryDispatchTrip).where(
            DeliveryDispatchTrip.id == trip_id,
            DeliveryDispatchTrip.delivery_id == ctx.delivery_id,
            or_(
                DeliveryDispatchTrip.vehicle_id == ctx.vehicle_id,
                DeliveryDispatchTrip.vehicle_no == ctx.vehicle_no,
            ),
        )
    )
    if not trip:
        raise HTTPException(404, "车次不存在或不属于当前车辆")
    return trip


async def _emit_order_status_change(db: AsyncSession, order: Order, old_status: str, new_status: str) -> None:
    if old_status == new_status:
        return
    await publish_monitor_event(
        "order_status_change",
        {
            "order_id": int(order.id),
            "order_no": order.order_no,
            "old_status": old_status,
            "new_status": new_status,
        },
    )
    await publish_role_order_update(
        "delivery",
        [int(order.delivery_id)],
        int(order.id),
        order.order_no,
        new_status,
        f"订单状态变更为{new_status}",
        canteen_id=int(order.canteen_id) if order.canteen_id is not None else None,
    )


async def _notify_delivered(db: AsyncSession, order: Order) -> None:
    cid = int(order.canteen_id) if order.canteen_id is not None else None
    await push_notification(
        db=db,
        role="client",
        event_type="order_status_change",
        title=f"订单 {order.order_no} 已送达",
        content="订单已送达，等待确认收货。",
        route=f"/client/orders/{order.id}",
        object_type="order",
        object_id=int(order.id),
        target_user_ids=[int(order.client_id)],
        canteen_id=cid,
    )
    await push_notification(
        db=db,
        role="delivery",
        event_type="order_status_change",
        title=f"订单 {order.order_no} 已送达",
        content="司机端已确认送达，等待客户确认收货。",
        route=f"/delivery/orders/{order.id}",
        object_type="order",
        object_id=int(order.id),
        target_user_ids=[int(order.delivery_id)],
    )


@router.post("/login")
async def driver_login(payload: DriverLoginIn, db: AsyncSession = Depends(get_db)):
    if payload.password != "demo123":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "车牌号或密码错误")
    vehicle_no = payload.vehicle_no.strip().upper()
    vehicles = (
        await db.scalars(
            select(DeliveryVehicle).where(
                DeliveryVehicle.vehicle_no == vehicle_no,
                DeliveryVehicle.status == "active",
            )
        )
    ).all()
    if not vehicles:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "车牌号或密码错误")
    if len(vehicles) > 1:
        raise HTTPException(400, "该车牌存在多个配送商绑定，请在车辆管理中去重后再登录")
    vehicle = vehicles[0]
    delivery = await db.scalar(select(User).where(User.id == int(vehicle.delivery_id), User.role == "delivery"))
    if not delivery or delivery.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "配送商账号不存在或已停用")
    token = _create_driver_token(vehicle, delivery)
    return {
        "token": token,
        "role": "driver",
        "vehicle_id": int(vehicle.id),
        "vehicle_no": vehicle.vehicle_no,
        "driver_name": vehicle.driver_name or "",
        "delivery_id": int(delivery.id),
        "delivery_name": delivery.company_name or delivery.username or "",
    }


@router.get("/me")
async def driver_me(ctx: DriverContext = Depends(_driver_context)):
    return {
        "vehicle_id": ctx.vehicle_id,
        "vehicle_no": ctx.vehicle_no,
        "driver_name": ctx.driver_name,
        "delivery_id": ctx.delivery_id,
        "delivery_name": ctx.delivery_name,
    }


@router.get("/trips/today")
async def driver_today_trips(
    planning_date: Optional[date] = None,
    ctx: DriverContext = Depends(_driver_context),
    db: AsyncSession = Depends(get_db),
):
    target_date = planning_date or date.today()
    rows = (
        await db.scalars(
            select(DeliveryDispatchTrip)
            .where(
                DeliveryDispatchTrip.delivery_id == ctx.delivery_id,
                or_(
                    DeliveryDispatchTrip.vehicle_id == ctx.vehicle_id,
                    DeliveryDispatchTrip.vehicle_no == ctx.vehicle_no,
                ),
                DeliveryDispatchTrip.planning_date == target_date,
                DeliveryDispatchTrip.status.in_(["待发车", "有阻塞", "运输中", "已完成"]),
            )
            .order_by(DeliveryDispatchTrip.departure_time.asc(), DeliveryDispatchTrip.id.asc())
        )
    ).all()
    for trip in rows:
        await _refresh_item_readiness(db, trip)
    await db.commit()
    return {
        "date": target_date.isoformat(),
        "vehicle_no": ctx.vehicle_no,
        "driver_name": ctx.driver_name,
        "delivery_name": ctx.delivery_name,
        "trips": [_serialize_trip(row) for row in rows],
    }


@router.get("/trips/{trip_id}")
async def driver_trip_detail(
    trip_id: int,
    ctx: DriverContext = Depends(_driver_context),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_for_driver(db, trip_id, ctx)
    await _refresh_item_readiness(db, trip)
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.post("/trips/{trip_id}/start")
async def driver_start_trip(
    trip_id: int,
    ctx: DriverContext = Depends(_driver_context),
    db: AsyncSession = Depends(get_db),
):
    trip = await _trip_for_driver(db, trip_id, ctx)
    if str(trip.status) != "运输中":
        raise HTTPException(400, "调度端尚未发车，请先由调度员执行整车发车或异常发车")
    await write_audit_log(
        db=db,
        actor_user_id=ctx.delivery_id,
        action="driver_trip_start",
        category="delivery",
        object_type="delivery_dispatch_trip",
        object_id=int(trip.id),
        detail=f"司机端开始配送：{trip.route_no} / {ctx.vehicle_no}",
        after_json={"vehicle_id": ctx.vehicle_id, "vehicle_no": ctx.vehicle_no},
    )
    await db.commit()
    return await _load_trip_payload(db, trip)


@router.post("/stops/{stop_id}/deliver")
async def driver_deliver_stop(
    stop_id: int,
    ctx: DriverContext = Depends(_driver_context),
    db: AsyncSession = Depends(get_db),
):
    stop = await db.scalar(select(DeliveryDispatchStop).where(DeliveryDispatchStop.id == stop_id))
    if not stop:
        raise HTTPException(404, "站点不存在")
    trip = await _trip_for_driver(db, int(stop.trip_id), ctx)
    order = await db.scalar(
        select(Order).where(
            Order.id == int(stop.order_id),
            Order.delivery_id == ctx.delivery_id,
        )
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    old_status = str(order.status)
    if old_status == "发货":
        ensure_order_transition(old_status, "收货")
        order.status = "收货"
        order.version += 1
        order.updated_at = datetime.utcnow()
        db.add(
            OrderStatusLog(
                order_id=int(order.id),
                old_status=old_status,
                new_status="收货",
                actor_user_id=ctx.delivery_id,
            )
        )
        await add_outbox_event(
            db=db,
            event_type="order_status_change",
            payload={
                "order_id": int(order.id),
                "order_no": order.order_no,
                "old_status": old_status,
                "new_status": "收货",
            },
            channel="monitor",
        )
        await close_delivery_overdue_ticket_if_delivered(db, order)
        await close_delivery_overdue_alert_if_delivered(db, order)
        await _emit_order_status_change(db, order, old_status, "收货")
        await _notify_delivered(db, order)
    elif old_status not in {"收货", "收货确认", "已结算"}:
        raise HTTPException(400, f"订单当前状态为 {old_status}，不能确认送达")

    delivery = await db.scalar(select(Delivery).where(Delivery.order_id == int(order.id)))
    if delivery:
        delivery.arrived_at = datetime.utcnow()
        delivery.status = "已送达"
        delivery.driver_name = trip.driver_name or ctx.driver_name or delivery.driver_name
        delivery.vehicle_no = trip.vehicle_no or ctx.vehicle_no or delivery.vehicle_no
    stop.status = "已送达"
    stop.affected = False
    stop.updated_at = datetime.utcnow()

    stops = (
        await db.scalars(select(DeliveryDispatchStop).where(DeliveryDispatchStop.trip_id == int(trip.id)))
    ).all()
    if stops and all(str(s.status) == "已送达" for s in stops):
        trip.status = "已完成"
        trip.completed_at = datetime.utcnow()
    trip.updated_at = datetime.utcnow()

    await write_audit_log(
        db=db,
        actor_user_id=ctx.delivery_id,
        action="driver_stop_deliver",
        category="delivery",
        object_type="order",
        object_id=int(order.id),
        detail=f"司机端确认送达：{order.order_no} / {ctx.vehicle_no}",
        after_json={
            "trip_id": int(trip.id),
            "route_no": trip.route_no,
            "stop_id": int(stop.id),
            "vehicle_id": ctx.vehicle_id,
            "vehicle_no": ctx.vehicle_no,
        },
    )
    await db.commit()
    return {"message": "已确认送达", "trip": await _load_trip_payload(db, trip)}
