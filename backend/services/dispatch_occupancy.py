"""发车车次占用：仅同一计划日互相占用，跨日排线不拦截。"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.delivery_dispatch import DeliveryDispatchTrip

ACTIVE_DISPATCH_TRIP_STATUSES = frozenset({"待发车", "有阻塞", "运输中"})
TERMINAL_DISPATCH_TRIP_STATUSES = frozenset({"已完成", "已取消"})


def active_dispatch_trip_filters(
    *,
    delivery_id: int,
    planning_date: date,
) -> tuple[ColumnElement[bool], ...]:
    """未完成车次占用条件：同配送商 + 同计划日 + 活跃状态。"""
    return (
        DeliveryDispatchTrip.delivery_id == int(delivery_id),
        DeliveryDispatchTrip.planning_date == planning_date,
        DeliveryDispatchTrip.status.in_(tuple(ACTIVE_DISPATCH_TRIP_STATUSES)),
    )


def trip_occupancy_label(status: str) -> str:
    if str(status) in TERMINAL_DISPATCH_TRIP_STATUSES:
        return "已释放"
    if str(status) in ACTIVE_DISPATCH_TRIP_STATUSES:
        return "占用中"
    return "未知"


async def cross_day_in_transit_warnings(
    db: AsyncSession,
    *,
    delivery_id: int,
    planning_date: date,
    vehicle_ids: list[int] | None = None,
    vehicle_nos: list[str] | None = None,
) -> list[str]:
    """上一计划日仍在运输中的车辆 — 软警告，不拦截排线。"""
    prev_date = planning_date - timedelta(days=1)
    rows = (
        await db.scalars(
            select(DeliveryDispatchTrip).where(
                DeliveryDispatchTrip.delivery_id == int(delivery_id),
                DeliveryDispatchTrip.planning_date == prev_date,
                DeliveryDispatchTrip.status == "运输中",
            )
        )
    ).all()
    if not rows:
        return []
    vid_set = {int(x) for x in (vehicle_ids or []) if int(x) > 0}
    vno_set = {str(x).strip() for x in (vehicle_nos or []) if str(x).strip()}
    filter_vehicles = bool(vid_set or vno_set)
    warnings: list[str] = []
    seen: set[str] = set()
    for trip in rows:
        key = str(trip.vehicle_no or trip.id)
        if key in seen:
            continue
        if filter_vehicles:
            matched = False
            if trip.vehicle_id is not None and int(trip.vehicle_id) in vid_set:
                matched = True
            if str(trip.vehicle_no or "").strip() in vno_set:
                matched = True
            if not matched:
                continue
        seen.add(key)
        warnings.append(
            f"车辆 {trip.vehicle_no or '-'} 在 {prev_date.isoformat()} 仍有在途车次 {trip.route_no}，"
            f"请确认 {planning_date.isoformat()} 可用后再保存计划。"
        )
    return warnings
