from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal, get_db
from dependencies import decode_access_token, require_role
from services.fleet_monitor import build_fleet_monitor_vehicles, build_fleet_monitor_warehouses
from services.fleet_monitor import (
    build_beidou_history_track_payload,
    build_camera_live_url_payload,
    device_location,
    device_online_status,
    is_beijing_fleet_coordinate,
    load_camera_device_or_404,
    load_vehicle_beidou_device_or_404,
)
from services.beidou_client import beidou_reported_at_display, enrich_beidou_devices_live
from services.delivery_warehouse_elitech import (
    elitech_api_call,
    elitech_client_or_503,
    elitech_realtime_fields_empty,
    elitech_realtime_map_for_sns,
)
from services.elitech_meta import curve_from_history_page, normalize_history_page
from models import (
    Alert,
    Base,
    Category,
    ClientCanteen,
    DeliveryDevice,
    DeliveryDispatchItem,
    DeliveryDispatchStop,
    DeliveryDispatchTrip,
    DeliverySortScanRecord,
    DeliveryVehicle,
    DeliveryVehicleDeviceBinding,
    DeliveryWarehouse,
    DeliveryWarehouseDeviceBinding,
    DeliveryWarehouseElitechBinding,
    Order,
    OrderItemAllocation,
    OrderReturn,
    Product,
    SupplierProductQuote,
    User,
)


router = APIRouter(prefix="/insights/business", tags=["tianshu_insights"])

_TZ = ZoneInfo("Asia/Shanghai")
_UTC = timezone.utc
_DEFAULT_RANGE_DAYS = 7
_MAX_RANGE_DAYS = 366

_DISTRICT_NAMES: tuple[str, ...] = (
    "门头沟区",
    "石景山区",
    "房山区",
    "大兴区",
    "通州区",
    "顺义区",
    "昌平区",
    "延庆区",
    "密云区",
    "怀柔区",
    "平谷区",
    "朝阳区",
    "丰台区",
    "海淀区",
    "西城区",
    "东城区",
    "雄安",
    "容城县",
    "雄县",
    "安新县",
)
_XIONGAN_ALIASES = ("雄安", "容城县", "雄县", "安新县")
_HQ = {"lng": 116.4074, "lat": 39.9042, "address": "北京市东城区监管指挥中心"}
_DISTRICT_GEO: dict[str, tuple[float, float]] = {
    "东城区": (116.417, 39.929),
    "西城区": (116.366, 39.912),
    "朝阳区": (116.486, 39.921),
    "海淀区": (116.298, 39.959),
    "丰台区": (116.286, 39.858),
    "石景山区": (116.223, 39.906),
    "门头沟区": (116.101, 39.94),
    "房山区": (116.143, 39.748),
    "通州区": (116.656, 39.91),
    "顺义区": (116.653, 40.13),
    "昌平区": (116.231, 40.22),
    "大兴区": (116.341, 39.726),
    "怀柔区": (116.631, 40.316),
    "平谷区": (117.121, 40.14),
    "密云区": (116.843, 40.377),
    "延庆区": (115.974, 40.456),
    "雄安": (115.873, 39.052),
    "容城县": (115.873, 39.052),
    "雄县": (116.108, 38.994),
    "安新县": (115.936, 38.936),
    "其他": (116.4074, 39.9042),
}


def _monitor_guard(_: User = Depends(require_role("monitor"))) -> None:
    return None


def _cn_today() -> date:
    return datetime.now(_TZ).date()


def _parse_iso_date(value: Optional[str], name: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, f"{name} 须为 YYYY-MM-DD") from exc


def _parse_range(
    start_date: Optional[str],
    end_date: Optional[str],
    *,
    default_span_days: int = _DEFAULT_RANGE_DAYS,
) -> tuple[date, date]:
    today = _cn_today()
    end = _parse_iso_date(end_date, "end_date") or today
    start = _parse_iso_date(start_date, "start_date") or (end - timedelta(days=default_span_days - 1))
    if start > end:
        start, end = end, start
    if (end - start).days > _MAX_RANGE_DAYS:
        start = end - timedelta(days=_MAX_RANGE_DAYS)
    return start, end


def _utc_naive_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    start_cn = datetime.combine(start, time.min, tzinfo=_TZ)
    end_cn = datetime.combine(end + timedelta(days=1), time.min, tzinfo=_TZ)
    return (
        start_cn.astimezone(_UTC).replace(tzinfo=None),
        end_cn.astimezone(_UTC).replace(tzinfo=None),
    )


def _to_ts(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return int(dt.timestamp())


def _cn_day(dt: datetime) -> date:
    return dt.replace(tzinfo=_UTC).astimezone(_TZ).date()


def _json_number(v: Any) -> float:
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _valid_lng_lat(lng: Any, lat: Any) -> bool:
    try:
        x = float(lng)
        y = float(lat)
    except (TypeError, ValueError):
        return False
    # 中国业务坐标范围。过滤 0,0、近零测试值和明显越界值，避免 3D 地图投影异常。
    return 70 <= x <= 140 and 15 <= y <= 55


def _norm_district(district_name: Optional[str]) -> Optional[str]:
    t = (district_name or "").strip()
    if not t:
        return None
    if t in _XIONGAN_ALIASES:
        return "雄安"
    return t if t in _DISTRICT_NAMES else None


def _addr_district(addr: str) -> Optional[str]:
    text = (addr or "").strip()
    if not text:
        return None
    if any(x in text for x in _XIONGAN_ALIASES):
        return "雄安"
    for name in _DISTRICT_NAMES:
        if name in text and name not in _XIONGAN_ALIASES:
            return name
    return None


def _addr_matches_district(addr: str, district_name: Optional[str]) -> bool:
    d = _norm_district(district_name)
    if not d:
        return True
    if d == "雄安":
        return any(x in (addr or "") for x in _XIONGAN_ALIASES)
    return d in (addr or "")


def _row_addr(order: Order, canteen: Optional[ClientCanteen]) -> str:
    return (order.delivery_address or (canteen.address if canteen else "") or "").strip()


def _row_customer(order: Order, canteen: Optional[ClientCanteen], client: Optional[User]) -> str:
    return (
        (canteen.name if canteen else "")
        or (client.company_name if client else "")
        or f"客户#{order.client_id}"
    )


def _row_coord(order: Order, canteen: Optional[ClientCanteen]) -> tuple[Optional[float], Optional[float]]:
    lng = _json_number(order.delivery_lng) if order.delivery_lng is not None else None
    lat = _json_number(order.delivery_lat) if order.delivery_lat is not None else None
    if _valid_lng_lat(lng, lat):
        return lng, lat
    if canteen and canteen.lng is not None and canteen.lat is not None:
        clng = _json_number(canteen.lng)
        clat = _json_number(canteen.lat)
        if _valid_lng_lat(clng, clat):
            return clng, clat
    return None, None


def _order_key(order: Order) -> int:
    return int(order.canteen_id or order.client_id or 0)


def _line_rows(order: Order) -> list[dict[str, Any]]:
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    out: list[dict[str, Any]] = []
    max_len = max(len(items), len(snaps))
    for idx in range(max_len):
        item = items[idx] if idx < len(items) and isinstance(items[idx], dict) else {}
        snap = snaps[idx] if idx < len(snaps) and isinstance(snaps[idx], dict) else {}
        qty = _json_number(
            snap.get("order_quantity", item.get("quantity", item.get("qty", 0)))
        )
        unit_price = _json_number(
            snap.get("order_unit_price", item.get("unit_price", item.get("price", 0)))
        )
        goods_name = (
            str(snap.get("product_name") or item.get("product_name") or item.get("goods_name") or "").strip()
            or f"商品#{item.get('product_id') or snap.get('product_id') or idx + 1}"
        )
        out.append(
            {
                "goods_name": goods_name,
                "spec": str(snap.get("spec") or item.get("spec") or "标准"),
                "unit": str(snap.get("unit") or item.get("unit") or ""),
                "qty": qty,
                "line_amount": round(qty * unit_price, 4),
                "category1_name": str(snap.get("category1_name") or ""),
            }
        )
    return out


async def _orders_with_context(
    db: AsyncSession,
    start: date,
    end: date,
    *,
    district_name: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[tuple[Order, Optional[ClientCanteen], Optional[User]]]:
    start_dt, end_dt = _utc_naive_bounds(start, end)
    stmt = (
        select(Order, ClientCanteen, User)
        .outerjoin(ClientCanteen, Order.canteen_id == ClientCanteen.id)
        .outerjoin(User, Order.client_id == User.id)
        .where(Order.created_at >= start_dt, Order.created_at < end_dt)
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    if district_name:
        d = _norm_district(district_name)
        if d == "雄安":
            conds = [
                Order.delivery_address.like(f"%{x}%") for x in _XIONGAN_ALIASES
            ] + [ClientCanteen.address.like(f"%{x}%") for x in _XIONGAN_ALIASES]
            stmt = stmt.where(or_(*conds))
        elif d:
            stmt = stmt.where(
                or_(
                    Order.delivery_address.like(f"%{d}%"),
                    ClientCanteen.address.like(f"%{d}%"),
                )
            )
    if limit:
        stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).all())


async def _orders_for_delivery_date(
    db: AsyncSession,
    target: date,
    *,
    district_name: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[tuple[Order, Optional[ClientCanteen], Optional[User]]]:
    stmt = (
        select(Order, ClientCanteen, User)
        .outerjoin(ClientCanteen, Order.canteen_id == ClientCanteen.id)
        .outerjoin(User, Order.client_id == User.id)
        .where(Order.expected_delivery_date == target)
        .order_by(Order.id.desc())
    )
    if district_name:
        d = _norm_district(district_name)
        if d == "雄安":
            conds = [
                Order.delivery_address.like(f"%{x}%") for x in _XIONGAN_ALIASES
            ] + [ClientCanteen.address.like(f"%{x}%") for x in _XIONGAN_ALIASES]
            stmt = stmt.where(or_(*conds))
        elif d:
            stmt = stmt.where(
                or_(
                    Order.delivery_address.like(f"%{d}%"),
                    ClientCanteen.address.like(f"%{d}%"),
                )
            )
    if limit:
        stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).all())


async def _today_order_return_ids(db: AsyncSession, start: date, end: date) -> set[int]:
    start_dt, end_dt = _utc_naive_bounds(start, end)
    ids = (
        await db.scalars(
            select(OrderReturn.order_id).where(
                OrderReturn.created_at >= start_dt,
                OrderReturn.created_at < end_dt,
            )
        )
    ).all()
    return {int(x) for x in ids}


@router.get("/kpi-summary")
async def kpi_summary(
    scope: str = Query("range"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    district_name: Optional[str] = None,
    fast_mode: bool = False,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    if scope == "today":
        start = end = _cn_today()
    else:
        start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    orders = [r[0] for r in rows]
    gmv = sum(_json_number(o.total_amount) for o in orders)
    buyers = {_order_key(o) for o in orders if _order_key(o)}
    returns = await _today_order_return_ids(db, start, end)
    return_amount = 0.0
    if returns:
        return_amount = sum(_json_number(o.total_amount) for o in orders if int(o.id) in returns)
    first_order_members = 0
    if not fast_mode and buyers:
        all_rows = await db.execute(select(Order).where(Order.canteen_id.in_(buyers)))
        first_by_buyer: dict[int, datetime] = {}
        for o in all_rows.scalars().all():
            k = _order_key(o)
            if k and (k not in first_by_buyer or o.created_at < first_by_buyer[k]):
                first_by_buyer[k] = o.created_at
        first_order_members = sum(
            1 for dt in first_by_buyer.values() if start <= _cn_day(dt) <= end
        )
    count = len(orders)
    return {
        "scope": scope,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "order_count": count,
        "gmv": round(gmv, 2),
        "avg_ticket": round(gmv / count, 2) if count else 0.0,
        "distinct_buyers": len(buyers),
        "first_order_members": first_order_members,
        "fast_mode": bool(fast_mode),
        "backorder_count": len(returns),
        "backorder_amount": round(return_amount, 2),
        "return_rate_by_amount_pct": round(100 * return_amount / gmv, 2) if gmv else 0.0,
        "metrics_note": "大宗天枢口径：按订单创建时间统计，金额为订单 total_amount。",
    }


@router.get("/orders-daily")
async def orders_daily(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    by_day: dict[str, dict[str, Any]] = {}
    for o, _, _client in rows:
        day = _cn_day(o.created_at).isoformat()
        slot = by_day.setdefault(day, {"day": day, "order_count": 0, "gmv": 0.0})
        slot["order_count"] += 1
        slot["gmv"] += _json_number(o.total_amount)
    series = list(sorted(by_day.values(), key=lambda r: r["day"]))
    for row in series:
        row["gmv"] = round(row["gmv"], 2)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "max_range_days": _MAX_RANGE_DAYS,
        "series": series,
        "summary": {
            "order_count": sum(int(r["order_count"]) for r in series),
            "gmv": round(sum(float(r["gmv"]) for r in series), 2),
        },
    }


@router.get("/today-intraday-gmv")
async def today_intraday_gmv(
    date_value: Optional[str] = Query(None, alias="date"),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    today = _cn_today()
    day = _parse_iso_date(date_value, "date") or today
    if day > today:
        raise HTTPException(400, "date 不能为未来日期")
    rows = await _orders_with_context(db, day, day, district_name=district_name)
    t0 = int(datetime.combine(day, time.min, tzinfo=_TZ).timestamp())
    now_ts = int(datetime.now(_TZ).timestamp())
    t1 = min(int(datetime.combine(day, time.max, tzinfo=_TZ).timestamp()), now_ts) if day == today else int(datetime.combine(day, time.max, tzinfo=_TZ).timestamp())
    buckets: dict[int, dict[str, Any]] = {}
    for o, _, _client in rows:
        ts = _to_ts(o.created_at)
        minute = t0 + ((ts - t0) // 60) * 60
        slot = buckets.setdefault(minute, {"minute_start": minute, "bucket_gmv": 0.0, "order_count": 0})
        slot["bucket_gmv"] += _json_number(o.total_amount)
        slot["order_count"] += 1
    out = list(sorted(buckets.values(), key=lambda r: r["minute_start"]))
    for row in out:
        row["bucket_gmv"] = round(row["bucket_gmv"], 2)
    return {
        "date": day.isoformat(),
        "day_start_ts": t0,
        "now_ts": now_ts,
        "query_end_ts": t1,
        "buckets": out,
    }


async def _client_points(
    db: AsyncSession,
    start: date,
    end: date,
    *,
    limit: int,
    district_name: Optional[str],
) -> list[dict[str, Any]]:
    """采购方/食堂同址聚合，与历史返回一致；统一附 role='client'。"""
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    grouped: dict[str, dict[str, Any]] = {}
    for o, canteen, client in rows:
        addr = _row_addr(o, canteen)
        if not addr:
            continue
        lng, lat = _row_coord(o, canteen)
        if lng is None or lat is None:
            continue
        g = grouped.setdefault(
            addr,
            {
                "member_key": f"addr:{abs(hash(addr))}",
                "member_ids": set(),
                "customer_names": set(),
                "address": addr,
                "order_count": 0,
                "gmv": 0.0,
                "lng": lng,
                "lat": lat,
            },
        )
        g["member_ids"].add(_order_key(o))
        g["customer_names"].add(_row_customer(o, canteen, client))
        g["order_count"] += 1
        g["gmv"] += _json_number(o.total_amount)
    out: list[dict[str, Any]] = []
    for g in sorted(grouped.values(), key=lambda x: (x["order_count"], x["gmv"]), reverse=True)[:limit]:
        ids = [x for x in g["member_ids"] if x]
        names = [x for x in g["customer_names"] if x]
        member_count = len(ids)
        out.append(
            {
                "role": "client",
                "member_key": g["member_key"],
                "member_id": ids[0] if member_count == 1 else None,
                "member_count": member_count,
                "customer_name": names[0] if len(names) == 1 else f"同址{max(member_count, len(names))}个客户",
                "address": g["address"],
                "order_count": int(g["order_count"]),
                "gmv": round(float(g["gmv"]), 2),
                "lng": float(g["lng"]),
                "lat": float(g["lat"]),
            }
        )
    return out


async def _delivery_points(
    db: AsyncSession,
    start: date,
    end: date,
    *,
    limit: int,
    district_name: Optional[str],
) -> list[dict[str, Any]]:
    """配送商组织 HQ 坐标 + 区间内承运订单量/GMV 聚合。坐标取 users 表 (role='delivery') 自填的 lng/lat。"""
    start_dt, end_dt = _utc_naive_bounds(start, end)
    stmt = (
        select(User, Order)
        .join(Order, Order.delivery_id == User.id)
        .where(
            User.role == "delivery",
            User.lng.is_not(None),
            User.lat.is_not(None),
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
        )
    )
    if district_name:
        d = _norm_district(district_name)
        if d == "雄安":
            conds = [User.address.like(f"%{x}%") for x in _XIONGAN_ALIASES] + [
                Order.delivery_address.like(f"%{x}%") for x in _XIONGAN_ALIASES
            ]
            stmt = stmt.where(or_(*conds))
        elif d:
            stmt = stmt.where(or_(User.address.like(f"%{d}%"), Order.delivery_address.like(f"%{d}%")))
    rows = list((await db.execute(stmt)).all())
    grouped: dict[int, dict[str, Any]] = {}
    for u, o in rows:
        if not _valid_lng_lat(u.lng, u.lat):
            continue
        g = grouped.setdefault(
            int(u.id),
            {
                "member_key": f"delivery:{int(u.id)}",
                "member_id": int(u.id),
                "customer_name": u.company_name or u.username or f"配送商{u.id}",
                "address": u.address or "",
                "order_count": 0,
                "gmv": 0.0,
                "lng": float(u.lng) if u.lng is not None else None,
                "lat": float(u.lat) if u.lat is not None else None,
            },
        )
        g["order_count"] += 1
        g["gmv"] += _json_number(o.total_amount)
    # 即使区间内一单都没有，也要让配送商 HQ 上图（金色光柱视觉），单独补一遍
    no_orders_stmt = select(User).where(
        User.role == "delivery",
        User.lng.is_not(None),
        User.lat.is_not(None),
    )
    for u in (await db.scalars(no_orders_stmt)).all():
        if int(u.id) in grouped:
            continue
        if not _valid_lng_lat(u.lng, u.lat):
            continue
        grouped[int(u.id)] = {
            "member_key": f"delivery:{int(u.id)}",
            "member_id": int(u.id),
            "customer_name": u.company_name or u.username or f"配送商{u.id}",
            "address": u.address or "",
            "order_count": 0,
            "gmv": 0.0,
            "lng": float(u.lng),
            "lat": float(u.lat),
        }
    out: list[dict[str, Any]] = []
    for g in sorted(grouped.values(), key=lambda x: (x["order_count"], x["gmv"]), reverse=True)[:limit]:
        if not _valid_lng_lat(g["lng"], g["lat"]):
            continue
        out.append(
            {
                "role": "delivery",
                "member_key": g["member_key"],
                "member_id": g["member_id"],
                "member_count": 1,
                "customer_name": g["customer_name"],
                "address": g["address"],
                "order_count": int(g["order_count"]),
                "gmv": round(float(g["gmv"]), 2),
                "lng": float(g["lng"]),
                "lat": float(g["lat"]),
            }
        )
    return out


@router.get("/cockpit-customer-map-points")
async def cockpit_customer_map_points(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    district_name: Optional[str] = None,
    role: str = Query("client", pattern="^(client|delivery|both)$"),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """监管大屏地图光柱数据源。
    - role=client（默认，保持向后兼容）：客户食堂同址聚合
    - role=delivery：配送商 HQ + 区间承运聚合（金色光柱）
    - role=both：client + delivery 合并返回
    每个点位都带 `role` 字段，前端据此着色。
    """
    start, end = _parse_range(start_date, end_date)
    points: list[dict[str, Any]] = []
    if role in ("client", "both"):
        points.extend(await _client_points(db, start, end, limit=limit, district_name=district_name))
    if role in ("delivery", "both"):
        points.extend(await _delivery_points(db, start, end, limit=limit, district_name=district_name))
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "district_name": _norm_district(district_name),
        "role": role,
        "points": points,
        "failed_geocode_count": 0,
        "geocode_enabled": True,
        "approx_district_points": 0,
    }


@router.get("/cockpit-flylines")
async def cockpit_flylines(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(60, ge=1, le=300),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """监管大屏飞线数据：配送商地址 → 客户地址。
    每条飞线 = 一个 (delivery, client) 订单对，去重聚合后按 GMV 取前 limit 条。
    delivery 坐标取 users.lng/lat（配送商公司地址），client 坐标取订单 delivery_lat/lng 或 canteen 坐标。
    """
    start, end = _parse_range(start_date, end_date)
    start_dt, end_dt = _utc_naive_bounds(start, end)

    # 联查：配送商 user（要有坐标）+ 订单 + 食堂（取客户坐标）
    stmt = (
        select(User, Order, ClientCanteen)
        .join(Order, Order.delivery_id == User.id)
        .outerjoin(ClientCanteen, ClientCanteen.id == Order.canteen_id)
        .where(
            User.role == "delivery",
            User.lng.is_not(None),
            User.lat.is_not(None),
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
        )
    )
    if district_name:
        d = _norm_district(district_name)
        if d == "雄安":
            conds = [Order.delivery_address.like(f"%{x}%") for x in _XIONGAN_ALIASES]
            stmt = stmt.where(or_(*conds))
        elif d:
            stmt = stmt.where(Order.delivery_address.like(f"%{d}%"))

    rows = list((await db.execute(stmt)).all())

    # 以 (delivery_id, client坐标) 为 key 聚合，避免重复飞线
    seen: dict[tuple, dict[str, Any]] = {}
    for delivery_user, order, canteen in rows:
        if not _valid_lng_lat(delivery_user.lng, delivery_user.lat):
            continue
        dlng = float(delivery_user.lng)
        dlat = float(delivery_user.lat)
        # 客户坐标：优先订单 delivery_lat/lng，其次 canteen 坐标
        clng, clat = _row_coord(order, canteen)
        if clng is None or clat is None:
            continue
        key = (delivery_user.id, round(clng, 4), round(clat, 4))
        if key not in seen:
            seen[key] = {
                "from_lng": dlng,
                "from_lat": dlat,
                "from_name": delivery_user.company_name or delivery_user.username or f"配送商{delivery_user.id}",
                "to_lng": float(clng),
                "to_lat": float(clat),
                "to_name": _row_customer(order, canteen, None),
                "gmv": 0.0,
                "order_count": 0,
            }
        seen[key]["gmv"] += _json_number(order.total_amount)
        seen[key]["order_count"] += 1

    lines = sorted(seen.values(), key=lambda x: x["gmv"], reverse=True)[:limit]
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "lines": [
            {
                "from_lng": l["from_lng"],
                "from_lat": l["from_lat"],
                "from_name": l["from_name"],
                "to_lng": l["to_lng"],
                "to_lat": l["to_lat"],
                "to_name": l["to_name"],
                "gmv": round(float(l["gmv"]), 2),
                "order_count": int(l["order_count"]),
            }
            for l in lines
        ],
    }


@router.get("/cockpit-smart-side-insights")
async def cockpit_smart_side_insights(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    cur = await _orders_with_context(db, start, end, district_name=district_name)
    prev = await _orders_with_context(db, prev_start, prev_end, district_name=district_name)
    cur_by: dict[str, dict[str, Any]] = defaultdict(lambda: {"gmv": 0.0, "order_count": 0})
    prev_by: dict[str, float] = defaultdict(float)
    for o, canteen, _client in cur:
        name = _addr_district(_row_addr(o, canteen)) or "其他"
        cur_by[name]["gmv"] += _json_number(o.total_amount)
        cur_by[name]["order_count"] += 1
    for o, canteen, _client in prev:
        name = _addr_district(_row_addr(o, canteen)) or "其他"
        prev_by[name] += _json_number(o.total_amount)
    key_districts = []
    for name, r in sorted(cur_by.items(), key=lambda item: item[1]["gmv"], reverse=True)[:8]:
        old = prev_by.get(name, 0.0)
        now = float(r["gmv"])
        key_districts.append(
            {
                "district_name": name,
                "gmv": round(now, 2),
                "order_count": int(r["order_count"]),
                "mom_pct": round(100 * (now - old) / old, 2) if old else (100.0 if now else 0.0),
            }
        )
    buckets = {"lt500": 0, "500_2k": 0, "2k_5k": 0, "gt5k": 0}
    amounts = []
    for o, _c, _u in cur:
        amt = _json_number(o.total_amount)
        amounts.append(amt)
        if amt < 500:
            buckets["lt500"] += 1
        elif amt < 2000:
            buckets["500_2k"] += 1
        elif amt < 5000:
            buckets["2k_5k"] += 1
        else:
            buckets["gt5k"] += 1
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "prev_start_date": prev_start.isoformat(),
        "prev_end_date": prev_end.isoformat(),
        "key_districts": key_districts,
        "ticket_buckets": [
            {"key": "lt500", "label": "<500", "count": buckets["lt500"]},
            {"key": "500_2k", "label": "500~2k", "count": buckets["500_2k"]},
            {"key": "2k_5k", "label": "2k~5k", "count": buckets["2k_5k"]},
            {"key": "gt5k", "label": ">5k", "count": buckets["gt5k"]},
        ],
        "ticket_avg": round(sum(amounts) / len(amounts), 2) if amounts else 0.0,
        "ticket_max": round(max(amounts), 2) if amounts else 0.0,
        "district_cover_count": len(cur_by),
        "active_points": len(cur),
    }


@router.get("/goods-top")
async def goods_top(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    by_goods: dict[str, dict[str, Any]] = defaultdict(lambda: {"total_quantity": 0.0, "total_amount": 0.0, "order_ids": set()})
    for o, _c, _u in rows:
        for line in _line_rows(o):
            r = by_goods[line["goods_name"]]
            r["total_quantity"] += _json_number(line["qty"])
            r["total_amount"] += _json_number(line["line_amount"])
            r["order_ids"].add(int(o.id))
    out = []
    for name, r in sorted(by_goods.items(), key=lambda item: item[1]["total_amount"], reverse=True)[:limit]:
        out.append(
            {
                "goods_name": name,
                "total_quantity": round(float(r["total_quantity"]), 3),
                "total_amount": round(float(r["total_amount"]), 2),
                "order_count": len(r["order_ids"]),
            }
        )
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "rows": out}


@router.get("/orders-top-members")
async def orders_top_members(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    by_member: dict[int, dict[str, Any]] = {}
    for o, canteen, client in rows:
        k = _order_key(o)
        r = by_member.setdefault(k, {"member_id": k, "member_name": _row_customer(o, canteen, client), "order_count": 0, "gmv": 0.0})
        r["order_count"] += 1
        r["gmv"] += _json_number(o.total_amount)
    out = list(sorted(by_member.values(), key=lambda r: r["gmv"], reverse=True))[:limit]
    for row in out:
        row["gmv"] = round(float(row["gmv"]), 2)
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "rows": out}


@router.get("/ops-alerts")
async def ops_alerts(
    limit: int = Query(20, ge=1, le=50),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    day = _cn_today()
    rows = await _orders_with_context(db, day, day, district_name=district_name)
    order_ids = [int(o.id) for o, _c, _u in rows]
    returns = []
    if order_ids:
        returns = (
            await db.execute(
                select(OrderReturn, Order)
                .join(Order, Order.id == OrderReturn.order_id)
                .where(OrderReturn.order_id.in_(order_ids))
                .order_by(OrderReturn.created_at.desc())
                .limit(limit)
            )
        ).all()
    return_ids = {int(r.order_id) for r, _o in returns}
    abnormal_orders = [o for o, _c, _u in rows if bool(o.has_abnormal) and int(o.id) not in return_ids]
    normal = max(0, len(rows) - len(return_ids) - len(abnormal_orders))
    start_dt, end_dt = _utc_naive_bounds(day, day)
    alert_rows = (
        await db.scalars(
            select(Alert)
            .where(Alert.created_at >= start_dt, Alert.created_at < end_dt)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
    ).all()
    return {
        "date": day.isoformat(),
        "threshold_note": "大宗天枢：退单=order_returns；补单=异常订单；正常=其余今日订单。",
        "return_pending": {
            "count": len(return_ids),
            "amount": round(sum(_json_number(o.total_amount) for _r, o in returns), 2),
        },
        "return_items": [
            {
                "id": int(r.id),
                "return_no": r.return_no,
                "order_id": int(o.id),
                "order_sn": o.order_no,
                "total_amount": _json_number(o.total_amount),
                "add_time": _to_ts(r.created_at),
                "remark": r.source,
            }
            for r, o in returns
        ],
        "supplement_today": {
            "linked_count": len(abnormal_orders),
            "pending_disorder_count": len([o for o in abnormal_orders if o.status not in ("收货确认", "已结算")]),
        },
        "supplement_items": [
            {
                "id": int(o.id),
                "order_sn": o.order_no,
                "total_amount": _json_number(o.total_amount),
                "add_time": _to_ts(o.created_at),
                "member_realname": _row_customer(o, None, None),
                "disorder_status": "异常",
            }
            for o in abnormal_orders[:limit]
        ],
        "today_order_mix": {
            "total": len(rows),
            "n_return": len(return_ids),
            "n_supplement": len(abnormal_orders),
            "n_normal": normal,
            "note": "今日范围：按订单创建时间；退单=order_returns；补单=has_abnormal；正常=其余订单。",
        },
        "alert_items": [
            {
                "id": int(a.id),
                "level": a.level,
                "type": a.type,
                "description": a.description,
                "created_at": a.created_at.isoformat(),
            }
            for a in alert_rows
        ],
    }


@router.get("/fulfillment-overview")
async def fulfillment_overview(
    limit: int = Query(80, ge=1, le=200),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    day = _cn_today()
    rows = await _orders_for_delivery_date(db, day, district_name=district_name, limit=1200)
    rows = [row for row in rows if row[0].status != "取消"]
    orders = [o for o, _c, _u in rows]
    order_ids = [int(o.id) for o in orders]
    order_id_set = set(order_ids)
    order_ctx = {int(o.id): (o, c, u) for o, c, u in rows}

    trips = (
        await db.scalars(
            select(DeliveryDispatchTrip)
            .where(DeliveryDispatchTrip.planning_date == day)
            .order_by(DeliveryDispatchTrip.id.desc())
            .limit(400)
        )
    ).all()
    trip_ids = [int(t.id) for t in trips]
    stops = (
        await db.scalars(select(DeliveryDispatchStop).where(DeliveryDispatchStop.trip_id.in_(trip_ids)))
    ).all() if trip_ids else []
    items = (
        await db.scalars(select(DeliveryDispatchItem).where(DeliveryDispatchItem.trip_id.in_(trip_ids)))
    ).all() if trip_ids else []
    allocations = (
        await db.scalars(
            select(OrderItemAllocation).where(OrderItemAllocation.order_id.in_(order_ids))
        )
    ).all() if order_ids else []
    allocation_ids = [int(a.id) for a in allocations]
    scan_records = (
        await db.scalars(
            select(DeliverySortScanRecord).where(DeliverySortScanRecord.allocation_id.in_(allocation_ids))
        )
    ).all() if allocation_ids else []
    user_ids = {
        int(uid)
        for o in orders
        for uid in (o.delivery_id, o.supplier_id, o.client_id)
        if uid is not None
    }
    user_ids.update(int(t.delivery_id) for t in trips if t.delivery_id)
    user_ids.update(int(a.supplier_id) for a in allocations if a.supplier_id)
    user_ids.update(int(i.supplier_id) for i in items if i.supplier_id)
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(u.id): u for u in users}

    stops_by_trip: dict[int, list[DeliveryDispatchStop]] = defaultdict(list)
    for stop in stops:
        if int(stop.order_id) in order_id_set or stop.expected_delivery_date == day:
            stops_by_trip[int(stop.trip_id)].append(stop)
    items_by_trip: dict[int, list[DeliveryDispatchItem]] = defaultdict(list)
    item_by_alloc: dict[int, DeliveryDispatchItem] = {}
    for item in items:
        if int(item.order_id) in order_id_set:
            items_by_trip[int(item.trip_id)].append(item)
            item_by_alloc.setdefault(int(item.allocation_id), item)
    route_by_order: dict[int, tuple[DeliveryDispatchTrip, DeliveryDispatchStop]] = {}
    trip_by_id = {int(t.id): t for t in trips}
    for trip_id, trip_stops in stops_by_trip.items():
        trip = trip_by_id.get(int(trip_id))
        if not trip:
            continue
        for stop in trip_stops:
            route_by_order.setdefault(int(stop.order_id), (trip, stop))

    scanned_alloc_ids = {int(s.allocation_id) for s in scan_records}
    loaded_statuses = {"已装车"}
    not_loaded_statuses = {"滞留未装", "取消随车", "供应商迟到", "质量问题", "现场缺货"}
    shipped_alloc_ids = {int(a.id) for a in allocations if str(a.status) == "已出库"}
    loaded_alloc_ids = {
        int(i.allocation_id)
        for i in items
        if str(i.status) in loaded_statuses and int(i.order_id) in order_id_set
    }
    not_loaded_items = [
        i for i in items if str(i.status) in not_loaded_statuses and int(i.order_id) in order_id_set
    ]

    total_orders = len(orders)
    total_allocations = len(allocations)
    delivered_orders = len([o for o in orders if o.status in {"收货", "收货确认", "已结算"}])
    departed_trips = len([t for t in trips if str(t.status) == "运输中" or t.departed_at])
    in_transit_trips = len([t for t in trips if str(t.status) == "运输中"])
    pending_trips = len([t for t in trips if str(t.status) in {"待发车", "有阻塞"}])
    not_shipped_count = len([a for a in allocations if str(a.status) != "已出库"])
    not_sorted_count = len([a for a in allocations if str(a.status) == "已出库" and int(a.id) not in scanned_alloc_ids])
    blocked_allocations = not_shipped_count + not_sorted_count + len(not_loaded_items)
    risk_count = blocked_allocations + sum(len(t.risk_alerts_json or []) for t in trips)
    sort_rate = round(100 * len(scanned_alloc_ids) / total_allocations, 1) if total_allocations else 0
    load_rate = round(100 * len(loaded_alloc_ids) / total_allocations, 1) if total_allocations else 0
    arrival_rate = round(100 * delivered_orders / total_orders, 1) if total_orders else 0
    health_score = max(
        0,
        min(
            100,
            round(sort_rate * 0.42 + load_rate * 0.28 + arrival_rate * 0.3 - min(blocked_allocations * 2.2, 22)),
        ),
    )

    def _name(user_id: Optional[int], fallback: str) -> str:
        user = user_map.get(int(user_id or 0))
        return (user.company_name or user.username) if user else fallback

    def _alloc_status(alloc: OrderItemAllocation) -> tuple[str, str]:
        if str(alloc.status) != "已出库":
            return "未出库", "供货商/厂家尚未完成出库登记"
        if int(alloc.id) not in scanned_alloc_ids:
            return "未分检", "配送商分检端尚未扫码确认"
        item = item_by_alloc.get(int(alloc.id))
        if item and str(item.status) in not_loaded_statuses:
            return "未随车", item.reason_detail or item.reason_code or "异常发车留置"
        if item and str(item.status) in loaded_statuses:
            return "已装车", "已进入车次装车清单"
        return "已分检", "PDA 已扫码分检完成"

    def _order_detail(order: Order, canteen: Optional[ClientCanteen], client: Optional[User]) -> dict[str, Any]:
        trip_stop = route_by_order.get(int(order.id))
        trip = trip_stop[0] if trip_stop else None
        return {
            "order_id": int(order.id),
            "order_no": order.order_no,
            "client_name": _row_customer(order, canteen, client),
            "canteen_name": _row_customer(order, canteen, client),
            "delivery_name": _name(order.delivery_id, "配送商未识别"),
            "expected_delivery_date": order.expected_delivery_date.isoformat() if order.expected_delivery_date else "",
            "expected_delivery_slot": order.expected_delivery_slot or "",
            "status": order.status,
            "amount": round(_json_number(order.total_amount), 2),
            "route_no": trip.route_no if trip else "暂未绑定车次",
            "trip_id": int(trip.id) if trip else None,
        }

    orders_detail = [_order_detail(o, c, u) for o, c, u in rows]
    allocation_rows = []
    supplier_blocks: dict[int, dict[str, Any]] = {}
    for alloc in allocations:
        order, canteen, client = order_ctx.get(int(alloc.order_id), (None, None, None))
        status, reason = _alloc_status(alloc)
        supplier_id = int(alloc.supplier_id or 0)
        supplier_name = _name(supplier_id, "供应商未识别")
        row = {
            "allocation_id": int(alloc.id),
            "allocation_no": f"{order.order_no if order else '订单'}-A{int(alloc.id)}",
            "order_id": int(alloc.order_id),
            "order_no": order.order_no if order else f"订单#{alloc.order_id}",
            "client_name": _row_customer(order, canteen, client) if order else "",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "quantity": _json_number(alloc.quantity),
            "shipment_status": "已出库" if str(alloc.status) == "已出库" else "未出库",
            "sort_status": "已分检" if int(alloc.id) in scanned_alloc_ids else "未分检",
            "load_status": item_by_alloc.get(int(alloc.id)).status if int(alloc.id) in item_by_alloc else "未进入车次",
            "business_status": status,
            "reason": reason,
            "route_no": route_by_order.get(int(alloc.order_id), (None, None))[0].route_no if int(alloc.order_id) in route_by_order else "暂未绑定车次",
        }
        allocation_rows.append(row)
        if status in {"未出库", "未分检", "未随车"}:
            block = supplier_blocks.setdefault(
                supplier_id,
                {
                    "supplier_id": supplier_id,
                    "supplier_name": supplier_name,
                    "not_shipped": 0,
                    "not_sorted": 0,
                    "not_loaded": 0,
                    "affected_orders": set(),
                    "affected_clients": set(),
                },
            )
            if status == "未出库":
                block["not_shipped"] += 1
            elif status == "未分检":
                block["not_sorted"] += 1
            else:
                block["not_loaded"] += 1
            block["affected_orders"].add(int(alloc.order_id))
            if order:
                block["affected_clients"].add(_row_customer(order, canteen, client))

    supplier_block_rows = []
    for row in supplier_blocks.values():
        blocked = int(row["not_shipped"] + row["not_sorted"] + row["not_loaded"])
        supplier_block_rows.append(
            {
                "supplier_id": row["supplier_id"],
                "supplier_name": row["supplier_name"],
                "not_shipped": int(row["not_shipped"]),
                "not_sorted": int(row["not_sorted"]),
                "not_loaded": int(row["not_loaded"]),
                "blocked_count": blocked,
                "affected_orders": len(row["affected_orders"]),
                "affected_clients": list(sorted(row["affected_clients"]))[:4],
            }
        )
    supplier_block_rows.sort(key=lambda r: r["blocked_count"], reverse=True)

    funnel = [
        {"key": "orders", "label": "今日订单", "count": total_orders, "total": total_orders},
        {"key": "allocated", "label": "已分单", "count": len({int(a.order_id) for a in allocations}), "total": total_orders},
        {"key": "shipped", "label": "已出库", "count": len(shipped_alloc_ids), "total": total_allocations},
        {"key": "sorted", "label": "已分检", "count": len(scanned_alloc_ids), "total": total_allocations},
        {"key": "loaded", "label": "已装车", "count": len(loaded_alloc_ids), "total": total_allocations},
        {"key": "departed", "label": "已发车", "count": departed_trips, "total": len(trips)},
        {"key": "arrived", "label": "已送达", "count": delivered_orders, "total": total_orders},
    ]
    for item in funnel:
        item["percent"] = round(100 * int(item["count"]) / int(item["total"]), 1) if int(item["total"]) else 0

    trip_cards = []
    map_points = []
    for trip in trips:
        trip_stops = sorted(stops_by_trip.get(int(trip.id), []), key=lambda s: (int(s.sequence), int(s.id)))
        trip_items = items_by_trip.get(int(trip.id), [])
        risk_alerts = [
            str((x.get("message") or x.get("reason") or x) if isinstance(x, dict) else x)
            for x in (trip.risk_alerts_json or [])
        ][:8]
        trip_cards.append(
            {
                "id": int(trip.id),
                "route_no": trip.route_no,
                "status": trip.status,
                "delivery_name": _name(trip.delivery_id, "配送商未识别"),
                "vehicle_no": trip.vehicle_no,
                "driver_name": trip.driver_name,
                "departure_time": trip.departure_time,
                "departed_at": _to_ts(trip.departed_at),
                "completed_at": _to_ts(trip.completed_at),
                "ready_count": int(trip.ready_count or 0),
                "blocked_count": int(trip.blocked_count or 0),
                "not_loaded_count": int(trip.not_loaded_count or 0),
                "stop_count": len(trip_stops),
                "affected_stop_count": len([s for s in trip_stops if s.affected or s.status in {"有阻塞", "未随车"}]),
                "distance_km": round(_json_number(trip.distance_km), 2),
                "duration_minutes": int(trip.duration_minutes or 0),
                "risk_count": len(risk_alerts),
                "risk_alerts": risk_alerts,
                "item_count": len(trip_items),
                "stops": [
                    {
                        "sequence": int(stop.sequence),
                        "order_id": int(stop.order_id),
                        "order_no": stop.order_no,
                        "client_name": stop.client_name,
                        "canteen_name": stop.canteen_name,
                        "address": stop.address,
                        "expected_delivery_slot": stop.expected_delivery_slot,
                        "planned_arrive_time": stop.planned_arrive_time,
                        "status": stop.status,
                        "affected": bool(stop.affected),
                    }
                    for stop in trip_stops[:20]
                ],
            }
        )
        for stop in trip_stops[:12]:
            ctx = order_ctx.get(int(stop.order_id))
            if not ctx:
                continue
            order, canteen, client = ctx
            lng, lat = _row_coord(order, canteen)
            if lng is None or lat is None:
                continue
            affected = bool(stop.affected or stop.status in {"有阻塞", "未随车"} or trip.blocked_count or trip.not_loaded_count)
            map_points.append(
                {
                    "role": "fulfillment",
                    "stage": "blocked" if affected else ("in_transit" if str(trip.status) == "运输中" else "normal"),
                    "address": _row_addr(order, canteen) or stop.address,
                    "customer_name": _row_customer(order, canteen, client),
                    "order_count": 1,
                    "gmv": round(_json_number(order.total_amount), 2),
                    "lng": float(lng),
                    "lat": float(lat),
                    "order_id": int(order.id),
                    "order_sn": order.order_no,
                    "trip_id": int(trip.id),
                    "route_no": trip.route_no,
                    "status": stop.status or trip.status,
                    "description": f"{trip.route_no} · 第 {int(stop.sequence)} 站 · {stop.status or trip.status}",
                }
            )

    mapped_order_ids = {
        int(p["order_id"])
        for p in map_points
        if p.get("order_id") is not None
    }
    for order, canteen, client in rows:
        if int(order.id) in mapped_order_ids:
            continue
        lng, lat = _row_coord(order, canteen)
        if lng is None or lat is None:
            continue
        map_points.append(
            {
                "role": "fulfillment",
                "stage": "normal",
                "address": _row_addr(order, canteen),
                "customer_name": _row_customer(order, canteen, client),
                "order_count": 1,
                "gmv": round(_json_number(order.total_amount), 2),
                "lng": float(lng),
                "lat": float(lat),
                "order_id": int(order.id),
                "order_sn": order.order_no,
                "trip_id": None,
                "route_no": "暂未绑定车次",
                "status": order.status or "待排车",
                "description": f"{order.order_no} · 暂未绑定车次 · {order.expected_delivery_slot or '配送窗口待定'}",
            }
        )

    risk_events = []
    for trip in trip_cards:
        for text in trip.get("risk_alerts") or []:
            risk_events.append(
                {
                    "id": f"trip-risk:{trip['id']}:{len(risk_events)}",
                    "type": "车次风险",
                    "level": "高" if trip["blocked_count"] or trip["not_loaded_count"] else "中",
                    "title": trip["route_no"],
                    "description": text,
                    "trip_id": trip["id"],
                    "route_no": trip["route_no"],
                    "created_at": trip["departed_at"] or 0,
                }
            )
    for row in allocation_rows:
        if row["business_status"] in {"未出库", "未分检", "未随车"}:
            risk_events.append(
                {
                    "id": f"alloc-risk:{row['allocation_id']}",
                    "type": row["business_status"],
                    "level": "高" if row["business_status"] == "未随车" else "中",
                    "title": row["order_no"],
                    "description": row["reason"],
                    "order_id": row["order_id"],
                    "route_no": row["route_no"],
                    "created_at": 0,
                }
            )

    return {
        "date": day.isoformat(),
        "data_mode": "real" if total_orders or trips else "empty",
        "summary": {
            "today_orders": total_orders,
            "total_allocations": total_allocations,
            "pending_trips": pending_trips,
            "in_transit_trips": in_transit_trips,
            "arrived_orders": delivered_orders,
            "blocked_allocations": blocked_allocations,
            "not_loaded": len(not_loaded_items),
            "risk_count": risk_count,
            "sort_rate": sort_rate,
            "load_rate": load_rate,
            "arrival_rate": arrival_rate,
            "health_score": health_score,
        },
        "funnel": funnel,
        "supplier_blocks": supplier_block_rows[:12],
        "trips": trip_cards[:limit],
        "in_transit": [t for t in trip_cards if t["status"] == "运输中"][:limit],
        "risk_events": risk_events[:limit],
        "map_points": map_points[:limit],
        "orders_detail": orders_detail[:limit],
        "allocations_detail": allocation_rows[:limit],
        "threshold_note": "天枢履约：配送日=orders.expected_delivery_date；分检=delivery_sort_scan_records；车次=delivery_dispatch_trips。",
    }


def _parse_float_text(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace("℃", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _cold_chain_mock_payload(reason: str = "") -> dict[str, Any]:
    vehicles = [
        {
            "id": 9101,
            "vehicle_no": "京A·C8101",
            "driver_name": "赵师傅",
            "delivery_name": "朝阳冷链配送中心",
            "online_status": "online",
            "lng": 116.486,
            "lat": 39.921,
            "speed": 42,
            "reported_at": "刚刚",
            "cameras": [{"id": 1}],
            "temperature": "3.8",
            "humidity": "62",
        },
        {
            "id": 9102,
            "vehicle_no": "京N·C9202",
            "driver_name": "孙师傅",
            "delivery_name": "海淀冷链配送中心",
            "online_status": "offline",
            "lng": 116.298,
            "lat": 39.959,
            "speed": 0,
            "reported_at": "18 分钟前",
            "cameras": [],
            "temperature": "9.6",
            "humidity": "71",
        },
    ]
    warehouses = [
        {
            "id": 9201,
            "name": "朝阳一号冷库",
            "address": "北京市朝阳区冷链仓",
            "delivery_name": "朝阳冷链配送中心",
            "lng": 116.455,
            "lat": 39.905,
            "elitech_bound": True,
            "elitech_temperature": "3.2",
            "elitech_humidity": "61",
            "elitech_online": True,
            "cameras": [{"id": 1}, {"id": 2}],
        },
        {
            "id": 9202,
            "name": "海淀校园冷库",
            "address": "北京市海淀区冷链仓",
            "delivery_name": "海淀冷链配送中心",
            "lng": 116.315,
            "lat": 39.962,
            "elitech_bound": True,
            "elitech_temperature": "10.4",
            "elitech_humidity": "78",
            "elitech_online": True,
            "cameras": [{"id": 3}],
        },
    ]
    events = [
        {
            "id": "mock-cold-vehicle-9102",
            "type": "车辆离线",
            "level": "高",
            "title": "京N·C9202",
            "description": "北斗 18 分钟未刷新，建议联系司机确认冷链状态。",
            "target_type": "vehicle",
            "target_id": 9102,
        },
        {
            "id": "mock-cold-warehouse-9202",
            "type": "仓温偏高",
            "level": "高",
            "title": "海淀校园冷库",
            "description": "实时温度 10.4℃，超过冷藏上限，建议立即复核库门和制冷机组。",
            "target_type": "warehouse",
            "target_id": 9202,
        },
    ]
    points = [
        {
            "role": "cold_chain",
            "cold_type": "vehicle",
            "stage": "moving",
            "lng": v["lng"],
            "lat": v["lat"],
            "vehicle_id": v["id"],
            "customer_name": v["vehicle_no"],
            "address": v["delivery_name"],
            "description": f"{v['vehicle_no']} · {v['online_status']} · {v['reported_at']}",
            "order_count": 1,
            "gmv": 1,
            "temperature": v["temperature"],
            "humidity": v["humidity"],
            "status": v["online_status"],
        }
        for v in vehicles
    ] + [
        {
            "role": "cold_chain",
            "cold_type": "warehouse",
            "stage": "alert" if _parse_float_text(w["elitech_temperature"]) and _parse_float_text(w["elitech_temperature"]) > 8 else "warehouse",
            "lng": w["lng"],
            "lat": w["lat"],
            "warehouse_id": w["id"],
            "customer_name": w["name"],
            "address": w["address"],
            "description": f"{w['name']} · {w['elitech_temperature']}℃ · RH {w['elitech_humidity']}%",
            "order_count": 1,
            "gmv": 1,
            "temperature": w["elitech_temperature"],
            "humidity": w["elitech_humidity"],
            "status": "online",
        }
        for w in warehouses
    ]
    return {
        "date": _cn_today().isoformat(),
        "data_mode": "mock",
        "mock_reason": reason,
        "summary": {
            "vehicles": len(vehicles),
            "online_vehicles": 1,
            "offline_vehicles": 1,
            "unlocated_vehicles": 0,
            "warehouses": len(warehouses),
            "temperature_online": 2,
            "temperature_alerts": 1,
            "cameras": 3,
            "online_rate": 50,
            "cold_score": 78,
        },
        "vehicles": vehicles,
        "warehouses": warehouses,
        "events": events,
        "map_points": points,
    }


def _cold_chain_device_payload(device: DeliveryDevice) -> dict[str, Any]:
    raw = device.raw_payload_json if isinstance(device.raw_payload_json, dict) else {}
    lng, lat = device_location(raw, str(device.vendor or ""))
    return {
        "id": int(device.id),
        "device_type": device.device_type,
        "vendor": device.vendor,
        "device_code": device.device_code,
        "device_name": device.device_name,
        "channel_no": int(device.channel_no or 0),
        "online_status": device_online_status(raw, str(device.vendor or "")),
        "lng": lng,
        "lat": lat,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
    }


class TianshuBeidouHistoryTrackIn(BaseModel):
    start_time: int
    end_time: int
    force_demo: bool = False


async def _vehicle_device_binding_payload(db: AsyncSession, vehicle_id: int) -> dict[str, Any]:
    vehicle = await db.scalar(
        select(DeliveryVehicle).where(
            DeliveryVehicle.id == int(vehicle_id),
            DeliveryVehicle.status == "active",
        )
    )
    if not vehicle:
        raise HTTPException(404, "车辆不存在或已停用")
    delivery_user = await db.get(User, int(vehicle.delivery_id))
    rows = (
        await db.execute(
            select(DeliveryDevice)
            .join(DeliveryVehicleDeviceBinding, DeliveryVehicleDeviceBinding.device_id == DeliveryDevice.id)
            .where(DeliveryVehicleDeviceBinding.vehicle_id == int(vehicle_id))
            .order_by(DeliveryVehicleDeviceBinding.id.asc())
        )
    ).scalars().all()
    beidou_devices = [d for d in rows if str(d.vendor or "").lower() == "beidou"]
    cameras = sorted(
        [d for d in rows if str(d.vendor or "").lower() == "ys7" and str(d.device_type or "") == "camera"],
        key=lambda d: (int(d.channel_no or 0), int(d.id)),
    )
    if beidou_devices:
        await enrich_beidou_devices_live(beidou_devices, db=db, persist=False)
    beidou = beidou_devices[0] if beidou_devices else None
    raw = beidou.raw_payload_json if beidou and isinstance(beidou.raw_payload_json, dict) else {}
    raw_lng, raw_lat = device_location(raw, "beidou") if beidou else (None, None)
    coord_valid = bool(beidou and is_beijing_fleet_coordinate(raw_lng, raw_lat))
    status = device_online_status(raw, "beidou") if beidou else "unbound"
    return {
        "target_type": "vehicle",
        "vehicle": {
            "id": int(vehicle.id),
            "vehicle_no": vehicle.vehicle_no,
            "vehicle_model": vehicle.vehicle_model or "",
            "driver_name": vehicle.driver_name or "",
            "delivery_id": int(vehicle.delivery_id),
            "delivery_name": ((delivery_user.company_name or delivery_user.username) if delivery_user else "") or "",
            "online_status": status,
            "lng": float(raw_lng) if raw_lng is not None and coord_valid else None,
            "lat": float(raw_lat) if raw_lat is not None and coord_valid else None,
            "raw_lng": float(raw_lng) if raw_lng is not None else None,
            "raw_lat": float(raw_lat) if raw_lat is not None else None,
            "coordinate_valid": coord_valid,
            "coordinate_status": "ok" if coord_valid else ("unbound" if not beidou else "missing_or_out_of_beijing"),
            "coordinate_hint": ""
            if coord_valid
            else ("未绑定北斗设备" if not beidou else "北斗坐标缺失或不在北京业务范围内"),
            "reported_at": beidou_reported_at_display(raw) if beidou else "",
            "updated_at": beidou.updated_at.isoformat() if beidou and beidou.updated_at else None,
        },
        "summary": {
            "beidou_bound": bool(beidou),
            "camera_count": len(cameras),
        },
        "beidou_device": _cold_chain_device_payload(beidou) if beidou else None,
        "cameras": [_cold_chain_device_payload(d) for d in cameras],
    }


async def _warehouse_device_binding_payload(db: AsyncSession, warehouse_id: int) -> dict[str, Any]:
    warehouse = await db.scalar(
        select(DeliveryWarehouse).where(
            DeliveryWarehouse.id == int(warehouse_id),
            DeliveryWarehouse.status == "active",
        )
    )
    if not warehouse:
        raise HTTPException(404, "仓库不存在或已停用")
    delivery_user = await db.get(User, int(warehouse.delivery_id))
    cameras = (
        await db.execute(
            select(DeliveryDevice)
            .join(DeliveryWarehouseDeviceBinding, DeliveryWarehouseDeviceBinding.device_id == DeliveryDevice.id)
            .where(DeliveryWarehouseDeviceBinding.warehouse_id == int(warehouse_id))
            .order_by(DeliveryWarehouseDeviceBinding.id.asc())
        )
    ).scalars().all()
    cameras = sorted(
        [d for d in cameras if str(d.vendor or "").lower() == "ys7" and str(d.device_type or "") == "camera"],
        key=lambda d: (int(d.channel_no or 0), int(d.id)),
    )
    binding = await db.scalar(
        select(DeliveryWarehouseElitechBinding).where(
            DeliveryWarehouseElitechBinding.warehouse_id == int(warehouse_id)
        )
    )
    sn = str(binding.elitech_sn) if binding and binding.elitech_sn else ""
    rt = elitech_realtime_fields_empty()
    if sn:
        try:
            rt = (await asyncio.wait_for(elitech_realtime_map_for_sns([sn]), timeout=2.5)).get(
                sn,
                elitech_realtime_fields_empty(),
            )
        except Exception:
            rt = elitech_realtime_fields_empty()
    elitech = {
        "elitech_bound": bool(sn),
        "elitech_sn": sn,
        "elitech_device_name": str(binding.device_name or "") if binding else "",
        "elitech_temperature": str(rt.get("elitech_temperature") or ""),
        "elitech_humidity": str(rt.get("elitech_humidity") or ""),
        "elitech_online": rt.get("elitech_online"),
    }
    return {
        "target_type": "warehouse",
        "warehouse": {
            "id": int(warehouse.id),
            "name": warehouse.name,
            "address": warehouse.address or "",
            "lng": float(warehouse.lng) if warehouse.lng is not None else None,
            "lat": float(warehouse.lat) if warehouse.lat is not None else None,
            "delivery_id": int(warehouse.delivery_id),
            "delivery_name": ((delivery_user.company_name or delivery_user.username) if delivery_user else "") or "",
            **elitech,
        },
        "summary": {
            "elitech_bound": bool(sn),
            "camera_count": len(cameras),
        },
        "elitech": elitech,
        "cameras": [_cold_chain_device_payload(d) for d in cameras],
    }


@router.get("/device-bindings")
async def tianshu_device_bindings(
    target_type: str = Query(...),
    target_id: int = Query(..., ge=1),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    if target_type not in {"vehicle", "warehouse"}:
        raise HTTPException(400, "target_type 仅支持 vehicle 或 warehouse")
    if target_type == "vehicle":
        return await _vehicle_device_binding_payload(db, target_id)
    return await _warehouse_device_binding_payload(db, target_id)


@router.get("/device-bindings/cameras/{device_id}/live-url")
async def tianshu_camera_live_url(
    device_id: int,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    row = await load_camera_device_or_404(db, device_id)
    return await build_camera_live_url_payload(row)


@router.post("/device-bindings/vehicles/{vehicle_id}/beidou-history-track")
async def tianshu_vehicle_beidou_history_track(
    vehicle_id: int,
    body: TianshuBeidouHistoryTrackIn,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    dev = await load_vehicle_beidou_device_or_404(db, vehicle_id)
    return await build_beidou_history_track_payload(
        dev,
        start_time=body.start_time,
        end_time=body.end_time,
        force_demo=body.force_demo,
    )


async def _warehouse_elitech_binding_or_404(db: AsyncSession, warehouse_id: int) -> DeliveryWarehouseElitechBinding:
    warehouse = await db.scalar(
        select(DeliveryWarehouse).where(
            DeliveryWarehouse.id == int(warehouse_id),
            DeliveryWarehouse.status == "active",
        )
    )
    if not warehouse:
        raise HTTPException(404, "仓库不存在或已停用")
    binding = await db.scalar(
        select(DeliveryWarehouseElitechBinding).where(
            DeliveryWarehouseElitechBinding.warehouse_id == int(warehouse_id)
        )
    )
    if not binding:
        raise HTTPException(400, "该仓库未绑定温湿度仪")
    return binding


@router.get("/device-bindings/warehouses/{warehouse_id}/elitech/realtime-curve")
async def tianshu_warehouse_elitech_realtime_curve(
    warehouse_id: int,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    binding = await _warehouse_elitech_binding_or_404(db, warehouse_id)
    client = elitech_client_or_503()
    payload = await elitech_api_call(lambda: client.get_realtime_curve(binding.elitech_sn))
    page = normalize_history_page(payload)
    return {"sn": binding.elitech_sn, "curve": curve_from_history_page(page)}


@router.get("/device-bindings/warehouses/{warehouse_id}/elitech/history-curve")
async def tianshu_warehouse_elitech_history_curve(
    warehouse_id: int,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    binding = await _warehouse_elitech_binding_or_404(db, warehouse_id)
    client = elitech_client_or_503()
    payload = await elitech_api_call(
        lambda: client.get_history_curve(
            binding.elitech_sn,
            start_time=start_time,
            end_time=end_time,
        )
    )
    page = normalize_history_page(payload)
    return {"sn": binding.elitech_sn, "curve": curve_from_history_page(page)}


async def _cached_fleet_monitor_vehicles(db: AsyncSession) -> dict[str, Any]:
    vehicles = (
        await db.scalars(
            select(DeliveryVehicle)
            .where(DeliveryVehicle.status == "active")
            .order_by(DeliveryVehicle.id.desc())
        )
    ).all()
    if not vehicles:
        return {"vehicles": [], "summary": {"total": 0, "online": 0, "offline": 0, "unlocated": 0, "cameras": 0}}

    vehicle_ids = [int(v.id) for v in vehicles]
    delivery_ids = sorted({int(v.delivery_id) for v in vehicles})
    users = (await db.scalars(select(User).where(User.id.in_(delivery_ids)))).all() if delivery_ids else []
    user_map = {int(u.id): u for u in users}
    rows = (
        await db.execute(
            select(DeliveryVehicleDeviceBinding.vehicle_id, DeliveryDevice)
            .join(DeliveryDevice, DeliveryDevice.id == DeliveryVehicleDeviceBinding.device_id)
            .where(DeliveryVehicleDeviceBinding.vehicle_id.in_(vehicle_ids))
            .order_by(DeliveryVehicleDeviceBinding.id.asc())
        )
    ).all()
    devices_by_vehicle: dict[int, list[DeliveryDevice]] = {}
    for vehicle_id, device in rows:
        devices_by_vehicle.setdefault(int(vehicle_id), []).append(device)

    out: list[dict[str, Any]] = []
    online = offline = unlocated = camera_total = 0
    for vehicle in vehicles:
        devices = devices_by_vehicle.get(int(vehicle.id), [])
        beidou_devices = [d for d in devices if str(d.vendor or "").lower() == "beidou"]
        cameras = sorted(
            [d for d in devices if str(d.vendor or "").lower() == "ys7" and str(d.device_type) == "camera"],
            key=lambda d: (int(d.channel_no or 0), int(d.id)),
        )
        beidou = beidou_devices[0] if beidou_devices else None
        raw = beidou.raw_payload_json if beidou and isinstance(beidou.raw_payload_json, dict) else {}
        raw_lng, raw_lat = device_location(raw, "beidou") if beidou else (None, None)
        coord_valid = bool(beidou and is_beijing_fleet_coordinate(raw_lng, raw_lat))
        lng, lat = (raw_lng, raw_lat) if coord_valid else (None, None)
        status = device_online_status(raw, "beidou") if beidou else "unbound"
        if lng is None or lat is None:
            unlocated += 1
        elif status == "online":
            online += 1
        elif status == "offline":
            offline += 1
        camera_total += len(cameras)
        delivery_user = user_map.get(int(vehicle.delivery_id))
        out.append(
            {
                "id": int(vehicle.id),
                "vehicle_no": vehicle.vehicle_no,
                "vehicle_model": vehicle.vehicle_model or "",
                "driver_name": vehicle.driver_name or "",
                "delivery_id": int(vehicle.delivery_id),
                "delivery_name": ((delivery_user.company_name or delivery_user.username) if delivery_user else "") or "",
                "lng": float(lng) if lng is not None else None,
                "lat": float(lat) if lat is not None else None,
                "raw_lng": float(raw_lng) if raw_lng is not None else None,
                "raw_lat": float(raw_lat) if raw_lat is not None else None,
                "coordinate_valid": bool(coord_valid),
                "coordinate_status": "ok"
                if coord_valid
                else ("unbound" if not beidou else ("out_of_beijing" if raw_lng is not None and raw_lat is not None else "missing")),
                "coordinate_hint": ""
                if coord_valid
                else (
                    "未绑定北斗设备"
                    if not beidou
                    else ("北斗坐标不在北京业务范围内，已暂不在地图展示" if raw_lng is not None and raw_lat is not None else "暂无北斗坐标")
                ),
                "online_status": status,
                "source": "beidou_cached" if beidou else "",
                "beidou_device": _cold_chain_device_payload(beidou) if beidou else None,
                "device_id": int(beidou.id) if beidou else None,
                "device_code": beidou.device_code if beidou else "",
                "device_label": (beidou.device_name or beidou.device_code or "") if beidou else "",
                "speed": raw.get("speed"),
                "course": raw.get("course") or raw.get("direction") or "",
                "reported_at": beidou_reported_at_display(raw) if beidou else "",
                "updated_at": beidou.updated_at.isoformat() if beidou and beidou.updated_at else None,
                "cameras": [_cold_chain_device_payload(d) for d in cameras[:3]],
            }
        )

    return {
        "vehicles": out,
        "summary": {"total": len(out), "online": online, "offline": offline, "unlocated": unlocated, "cameras": camera_total},
        "refreshed_at": datetime.utcnow().isoformat(),
        "degraded": True,
    }


async def _cached_fleet_monitor_warehouses(db: AsyncSession) -> dict[str, Any]:
    warehouses = (
        await db.scalars(
            select(DeliveryWarehouse)
            .where(DeliveryWarehouse.status == "active")
            .order_by(DeliveryWarehouse.id.desc())
        )
    ).all()
    if not warehouses:
        return {"warehouses": [], "summary": {"total": 0, "cameras": 0}, "degraded": True}

    warehouse_ids = [int(w.id) for w in warehouses]
    delivery_ids = sorted({int(w.delivery_id) for w in warehouses})
    users = (await db.scalars(select(User).where(User.id.in_(delivery_ids)))).all() if delivery_ids else []
    user_map = {int(u.id): u for u in users}
    rows = (
        await db.execute(
            select(DeliveryWarehouseDeviceBinding.warehouse_id, DeliveryDevice)
            .join(DeliveryDevice, DeliveryDevice.id == DeliveryWarehouseDeviceBinding.device_id)
            .where(DeliveryWarehouseDeviceBinding.warehouse_id.in_(warehouse_ids))
            .order_by(DeliveryWarehouseDeviceBinding.id.asc())
        )
    ).all()
    cameras_by_warehouse: dict[int, list[DeliveryDevice]] = {}
    for wid, device in rows:
        if str(device.vendor or "").lower() == "ys7" and str(device.device_type) == "camera":
            cameras_by_warehouse.setdefault(int(wid), []).append(device)

    bindings = (
        await db.scalars(
            select(DeliveryWarehouseElitechBinding).where(
                DeliveryWarehouseElitechBinding.warehouse_id.in_(warehouse_ids)
            )
        )
    ).all()
    elitech_map = {int(b.warehouse_id): b for b in bindings}

    out: list[dict[str, Any]] = []
    camera_total = 0
    for w in warehouses:
        cameras = sorted(cameras_by_warehouse.get(int(w.id), []), key=lambda d: (int(d.channel_no or 0), int(d.id)))
        camera_total += len(cameras)
        delivery_user = user_map.get(int(w.delivery_id))
        binding = elitech_map.get(int(w.id))
        sn = str(binding.elitech_sn) if binding and binding.elitech_sn else ""
        elitech = {
            "elitech_bound": bool(binding and sn),
            "elitech_sn": sn,
            "elitech_device_name": str(binding.device_name or "") if binding else "",
            **elitech_realtime_fields_empty(),
        }
        out.append(
            {
                "id": int(w.id),
                "name": w.name,
                "address": w.address or "",
                "lng": float(w.lng) if w.lng is not None else None,
                "lat": float(w.lat) if w.lat is not None else None,
                "status": w.status,
                "delivery_id": int(w.delivery_id),
                "delivery_name": ((delivery_user.company_name or delivery_user.username) if delivery_user else "") or "",
                "cameras": [_cold_chain_device_payload(d) for d in cameras],
                **elitech,
            }
        )

    return {
        "warehouses": out,
        "summary": {"total": len(out), "cameras": camera_total},
        "refreshed_at": datetime.utcnow().isoformat(),
        "degraded": True,
    }


@router.get("/cold-chain-overview")
async def cold_chain_overview(
    limit: int = Query(80, ge=1, le=200),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    degraded_reasons: list[str] = []
    try:
        vehicle_payload = await asyncio.wait_for(build_fleet_monitor_vehicles(db), timeout=1.5)
    except Exception:
        degraded_reasons.append("vehicle_live_timeout")
        vehicle_payload = await _cached_fleet_monitor_vehicles(db)
    try:
        warehouse_payload = await asyncio.wait_for(build_fleet_monitor_warehouses(db), timeout=1.5)
    except Exception:
        degraded_reasons.append("warehouse_live_timeout")
        warehouse_payload = await _cached_fleet_monitor_warehouses(db)
    vehicles = list(vehicle_payload.get("vehicles") or [])
    warehouses = list(warehouse_payload.get("warehouses") or [])
    if not vehicles and not warehouses:
        return _cold_chain_mock_payload("empty")

    map_points: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    camera_total = int(vehicle_payload.get("summary", {}).get("cameras") or 0) + int(
        warehouse_payload.get("summary", {}).get("cameras") or 0
    )
    online = int(vehicle_payload.get("summary", {}).get("online") or 0)
    offline = int(vehicle_payload.get("summary", {}).get("offline") or 0)
    unlocated = int(vehicle_payload.get("summary", {}).get("unlocated") or 0)

    for v in vehicles[:limit]:
        status = str(v.get("online_status") or "offline")
        if v.get("lng") is not None and v.get("lat") is not None:
            map_points.append(
                {
                    "role": "cold_chain",
                    "cold_type": "vehicle",
                    "stage": "moving" if status == "online" else "alert",
                    "lng": float(v["lng"]),
                    "lat": float(v["lat"]),
                    "vehicle_id": int(v.get("id") or 0),
                    "customer_name": v.get("vehicle_no") or "冷链车辆",
                    "address": v.get("delivery_name") or "",
                    "description": f"{v.get('vehicle_no') or '冷链车辆'} · {status} · {v.get('reported_at') or '暂无上报'}",
                    "order_count": 1,
                    "gmv": 1,
                    "status": status,
                    "temperature": v.get("temperature") or "",
                    "humidity": v.get("humidity") or "",
                }
            )
        if status != "online" or not v.get("coordinate_valid"):
            events.append(
                {
                    "id": f"vehicle:{v.get('id')}",
                    "type": "车辆离线" if status != "online" else "无有效定位",
                    "level": "高" if status != "online" else "中",
                    "title": v.get("vehicle_no") or "冷链车辆",
                    "description": v.get("coordinate_hint") or f"北斗状态 {status}，上报时间 {v.get('reported_at') or '未知'}。",
                    "target_type": "vehicle",
                    "target_id": int(v.get("id") or 0),
                }
            )

    temp_online = 0
    temp_alerts = 0
    for w in warehouses[:limit]:
        temp = _parse_float_text(w.get("elitech_temperature"))
        humidity = _parse_float_text(w.get("elitech_humidity"))
        online_flag = bool(w.get("elitech_online"))
        if online_flag:
            temp_online += 1
        alert = bool((temp is not None and (temp < -2 or temp > 8)) or (humidity is not None and humidity > 85) or (w.get("elitech_bound") and not online_flag))
        if alert:
            temp_alerts += 1
        if w.get("lng") is not None and w.get("lat") is not None:
            map_points.append(
                {
                    "role": "cold_chain",
                    "cold_type": "warehouse",
                    "stage": "alert" if alert else "warehouse",
                    "lng": float(w["lng"]),
                    "lat": float(w["lat"]),
                    "warehouse_id": int(w.get("id") or 0),
                    "customer_name": w.get("name") or "冷库",
                    "address": w.get("address") or "",
                    "description": f"{w.get('name') or '冷库'} · {w.get('elitech_temperature') or '-'}℃ · RH {w.get('elitech_humidity') or '-'}%",
                    "order_count": 1,
                    "gmv": 1,
                    "status": "online" if online_flag else "offline",
                    "temperature": w.get("elitech_temperature") or "",
                    "humidity": w.get("elitech_humidity") or "",
                }
            )
        if alert:
            events.append(
                {
                    "id": f"warehouse:{w.get('id')}",
                    "type": "仓温异常" if temp is not None and (temp < -2 or temp > 8) else "温控离线",
                    "level": "高" if temp is not None and (temp < -2 or temp > 8) else "中",
                    "title": w.get("name") or "冷库",
                    "description": f"温度 {w.get('elitech_temperature') or '-'}℃，湿度 {w.get('elitech_humidity') or '-'}%，在线状态 {w.get('elitech_online')}",
                    "target_type": "warehouse",
                    "target_id": int(w.get("id") or 0),
                }
            )

    total_vehicles = max(1, int(vehicle_payload.get("summary", {}).get("total") or len(vehicles) or 0))
    online_rate = round(100 * online / total_vehicles, 1) if total_vehicles else 0
    cold_score = max(0, min(100, round(online_rate * 0.55 + (100 - min(temp_alerts * 16, 60)) * 0.45 - min(unlocated * 5, 18))))
    data_mode = "real_degraded" if degraded_reasons else ("real" if vehicles or warehouses else "empty")
    return {
        "date": _cn_today().isoformat(),
        "data_mode": data_mode,
        "degraded_reasons": degraded_reasons,
        "summary": {
            "vehicles": len(vehicles),
            "online_vehicles": online,
            "offline_vehicles": offline,
            "unlocated_vehicles": unlocated,
            "warehouses": len(warehouses),
            "temperature_online": temp_online,
            "temperature_alerts": temp_alerts,
            "cameras": camera_total,
            "online_rate": online_rate,
            "cold_score": cold_score,
        },
        "vehicles": vehicles[:limit],
        "warehouses": warehouses[:limit],
        "events": events[:limit],
        "map_points": map_points[:limit],
        "threshold_note": "冷链运力：车辆来自北斗绑定；冷库温湿度来自 Elitech 实时接口；仓温建议冷藏区间 -2℃~8℃。",
    }


async def _safe_text_rows(db: AsyncSession, sql: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    try:
        rs = await db.execute(text(sql), params or {})
        return [dict(row._mapping) for row in rs.fetchall()]
    except Exception:
        return []


def _json_obj(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return None


def _industry_mock_payload(reason: str = "") -> dict[str, Any]:
    today = _cn_today().isoformat()
    categories = [
        {"category_name": "叶菜类", "order_count": 46, "total_amount": 286000, "total_quantity": 8200},
        {"category_name": "肉禽蛋", "order_count": 31, "total_amount": 244000, "total_quantity": 3900},
        {"category_name": "根茎类", "order_count": 28, "total_amount": 118000, "total_quantity": 6100},
        {"category_name": "米面粮油", "order_count": 18, "total_amount": 96000, "total_quantity": 5200},
    ]
    goods = [
        {"goods_name": "小白菜", "total_quantity": 1880, "total_amount": 62500, "order_count": 23, "change_pct": 8.6},
        {"goods_name": "鲜鸡蛋", "total_quantity": 920, "total_amount": 58400, "order_count": 18, "change_pct": -3.2},
        {"goods_name": "土豆", "total_quantity": 2100, "total_amount": 42300, "order_count": 21, "change_pct": 2.1},
        {"goods_name": "猪后腿肉", "total_quantity": 640, "total_amount": 76800, "order_count": 14, "change_pct": 6.8},
    ]
    forecast = [
        {"product_name": "小白菜", "latest_price": 3.2, "forecast_price": 3.48, "change_pct": 8.6, "confidence": 82, "status": "可预测"},
        {"product_name": "猪后腿肉", "latest_price": 27.8, "forecast_price": 29.7, "change_pct": 6.8, "confidence": 76, "status": "可预测"},
        {"product_name": "鲜鸡蛋", "latest_price": 8.9, "forecast_price": 8.62, "change_pct": -3.2, "confidence": 79, "status": "可预测"},
    ]
    points = [
        {
            "role": "industry",
            "stage": "volatile",
            "industry_type": "forecast",
            "product_name": item["product_name"],
            "category_name": "重点品种",
            "change_pct": item["change_pct"],
            "forecast_price": item["forecast_price"],
            "confidence": item["confidence"],
            "lng": lng,
            "lat": lat,
            "customer_name": item["product_name"],
            "address": f"{item['product_name']}价格预测热区",
            "description": f"预测 {item['forecast_price']} 元，波动 {item['change_pct']}%",
            "order_count": 1,
            "gmv": abs(item["change_pct"]) * 100,
        }
        for item, (lng, lat) in zip(forecast, [(116.486, 39.921), (116.298, 39.959), (116.656, 39.91)])
    ]
    return {
        "date": today,
        "data_mode": "mock",
        "mock_reason": reason,
        "summary": {
            "monitored_categories": len(categories),
            "volatile_products": len([x for x in forecast if abs(float(x["change_pct"])) >= 5]),
            "forecast_usable": len(forecast),
            "hot_goods": goods[0]["goods_name"],
            "quote_count": 12,
            "business_goods": len(goods),
        },
        "category_mix": categories,
        "goods_rank": goods,
        "forecast_items": forecast,
        "price_series": [
            {"date": today, "product_name": "小白菜", "avg_price": 3.2},
            {"date": today, "product_name": "猪后腿肉", "avg_price": 27.8},
            {"date": today, "product_name": "鲜鸡蛋", "avg_price": 8.9},
        ],
        "impact_items": [
            {"title": "叶菜采购预警", "target": "小白菜", "impact": "预计上行 8.6%，建议锁定明日高频食堂采购量。", "level": "高"},
            {"title": "肉类成本压力", "target": "猪后腿肉", "impact": "平台 GMV 占比较高，建议复核供应商报价。", "level": "中"},
            {"title": "蛋类回落窗口", "target": "鲜鸡蛋", "impact": "预测回落，可延后非刚需补库。", "level": "低"},
        ],
        "map_points": points,
    }


@router.get("/industry-insights-overview")
async def industry_insights_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(80, ge=1, le=200),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    category_by: dict[str, dict[str, Any]] = defaultdict(lambda: {"order_ids": set(), "total_amount": 0.0, "total_quantity": 0.0})
    goods_by: dict[str, dict[str, Any]] = defaultdict(lambda: {"order_ids": set(), "total_amount": 0.0, "total_quantity": 0.0, "points": []})
    for order, canteen, _client in rows:
        lng, lat = _row_coord(order, canteen)
        for line in _line_rows(order):
            cat = line["category1_name"] or "未归类"
            category_by[cat]["order_ids"].add(int(order.id))
            category_by[cat]["total_amount"] += _json_number(line["line_amount"])
            category_by[cat]["total_quantity"] += _json_number(line["qty"])
            goods = goods_by[line["goods_name"]]
            goods["order_ids"].add(int(order.id))
            goods["total_amount"] += _json_number(line["line_amount"])
            goods["total_quantity"] += _json_number(line["qty"])
            if lng is not None and lat is not None:
                goods["points"].append((float(lng), float(lat), _row_addr(order, canteen)))

    category_mix = [
        {
            "category_name": name,
            "order_count": len(v["order_ids"]),
            "total_amount": round(float(v["total_amount"]), 2),
            "total_quantity": round(float(v["total_quantity"]), 3),
        }
        for name, v in sorted(category_by.items(), key=lambda item: item[1]["total_amount"], reverse=True)[:12]
    ]
    goods_rank = [
        {
            "goods_name": name,
            "total_quantity": round(float(v["total_quantity"]), 3),
            "total_amount": round(float(v["total_amount"]), 2),
            "order_count": len(v["order_ids"]),
        }
        for name, v in sorted(goods_by.items(), key=lambda item: item[1]["total_amount"], reverse=True)[:12]
    ]

    quotes = (
        await db.scalars(
            select(SupplierProductQuote)
            .order_by(SupplierProductQuote.id.desc())
            .limit(limit)
        )
    ).all()
    quote_count = len(quotes)
    price_rows = await _safe_text_rows(
        db,
        """
        SELECT crawl_date, goods_name, price, cate_name
        FROM zgncpjgw_price_crawl
        WHERE goods_name <> ''
        ORDER BY crawl_date DESC, updated_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    forecast_raw = await _safe_text_rows(
        db,
        """
        SELECT product_name, latest_forecast_json, metrics_json, updated_at
        FROM xinfadi_forecast_metrics
        ORDER BY updated_at DESC
        LIMIT :limit
        """,
        {"limit": min(limit, 40)},
    )

    latest_price_by: dict[str, float] = {}
    price_series = []
    for r in price_rows:
        price = _parse_float_text(r.get("price"))
        name = str(r.get("goods_name") or "").strip()
        if not name or price is None:
            continue
        latest_price_by.setdefault(name, price)
        price_series.append(
            {
                "date": str(r.get("crawl_date") or ""),
                "product_name": name,
                "category_name": str(r.get("cate_name") or ""),
                "avg_price": round(float(price), 3),
            }
        )

    forecast_items = []
    for r in forecast_raw:
        name = str(r.get("product_name") or "").strip()
        payload = _json_obj(r.get("latest_forecast_json"))
        metrics = _json_obj(r.get("metrics_json")) or {}
        if not name:
            continue
        values = payload if isinstance(payload, list) else payload.get("forecast") if isinstance(payload, dict) else []
        first = values[0] if isinstance(values, list) and values else {}
        if isinstance(first, dict):
            forecast_price = _json_number(first.get("yhat") or first.get("price") or first.get("forecast_price"))
        else:
            forecast_price = _json_number(first)
        latest = latest_price_by.get(name)
        change = round(100 * (forecast_price - latest) / latest, 2) if latest and forecast_price else 0.0
        confidence = metrics.get("confidence") if isinstance(metrics, dict) else None
        if confidence is None:
            mape = _json_number(metrics.get("mape") if isinstance(metrics, dict) else 0)
            confidence = max(45, min(92, round(100 - mape * 100, 1))) if mape else 72
        forecast_items.append(
            {
                "product_name": name,
                "latest_price": round(float(latest or 0), 3),
                "forecast_price": round(float(forecast_price or 0), 3),
                "change_pct": change,
                "confidence": round(_json_number(confidence), 1),
                "status": "可预测" if forecast_price else "待训练",
                "updated_at": str(r.get("updated_at") or ""),
            }
        )
    if not forecast_items and price_series:
        for p in price_series[:8]:
            base = _json_number(p.get("avg_price"))
            forecast_items.append(
                {
                    "product_name": p["product_name"],
                    "latest_price": base,
                    "forecast_price": round(base * 1.03, 3),
                    "change_pct": 3.0,
                    "confidence": 58,
                    "status": "行情推演",
                    "updated_at": p["date"],
                }
            )

    if not rows and not price_series and not forecast_items and not quotes:
        return _industry_mock_payload("empty")

    volatile = [x for x in forecast_items if abs(_json_number(x.get("change_pct"))) >= 5]
    goods_names = {g["goods_name"] for g in goods_rank}
    impact_items = []
    for item in (volatile or forecast_items)[:8]:
        name = item["product_name"]
        linked = next((g for g in goods_rank if name in g["goods_name"] or g["goods_name"] in name), None)
        if not linked and goods_rank:
            linked = goods_rank[0]
        impact_items.append(
            {
                "title": "价格波动影响" if linked else "行情监测",
                "target": name,
                "impact": (
                    f"{name}预测波动 {item['change_pct']}%，关联平台商品 {linked['goods_name']}，近7日 GMV ¥{linked['total_amount']:.0f}。"
                    if linked
                    else f"{name}预测波动 {item['change_pct']}%，暂无平台订单关联。"
                ),
                "level": "高" if abs(_json_number(item.get("change_pct"))) >= 8 else "中",
            }
        )

    map_points = []
    anchors = [(116.486, 39.921), (116.298, 39.959), (116.656, 39.91), (116.341, 39.726), (115.873, 39.052)]
    for idx, item in enumerate((volatile or forecast_items or [])[:10]):
        goods_slot = goods_by.get(item["product_name"])
        if goods_slot and goods_slot["points"]:
            lng, lat, addr = goods_slot["points"][0]
        else:
            lng, lat = anchors[idx % len(anchors)]
            addr = f"{item['product_name']}产业价格热区"
        map_points.append(
            {
                "role": "industry",
                "stage": "volatile" if abs(_json_number(item.get("change_pct"))) >= 5 else "normal",
                "industry_type": "forecast",
                "product_name": item["product_name"],
                "category_name": "价格预测",
                "change_pct": item["change_pct"],
                "forecast_price": item["forecast_price"],
                "confidence": item["confidence"],
                "lng": lng,
                "lat": lat,
                "customer_name": item["product_name"],
                "address": addr,
                "description": f"{item['product_name']} · 预测 {item['forecast_price']} · 波动 {item['change_pct']}%",
                "order_count": 1,
                "gmv": abs(_json_number(item.get("change_pct"))) * 100 + 1,
            }
        )
    if not map_points:
        for idx, g in enumerate(goods_rank[:5]):
            lng, lat = anchors[idx % len(anchors)]
            map_points.append(
                {
                    "role": "industry",
                    "stage": "business",
                    "industry_type": "goods",
                    "product_name": g["goods_name"],
                    "category_name": "平台热销",
                    "change_pct": 0,
                    "forecast_price": 0,
                    "confidence": 0,
                    "lng": lng,
                    "lat": lat,
                    "customer_name": g["goods_name"],
                    "address": f"{g['goods_name']}业务热销点",
                    "description": f"平台 GMV ¥{g['total_amount']:.0f}，订单 {g['order_count']} 单",
                    "order_count": g["order_count"],
                    "gmv": g["total_amount"],
                }
            )

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "date": end.isoformat(),
        "district_name": _norm_district(district_name),
        "data_mode": "real" if rows or price_series or forecast_items else "empty",
        "summary": {
            "monitored_categories": len(category_mix) or len({p.get("category_name") for p in price_series if p.get("category_name")}),
            "volatile_products": len(volatile),
            "forecast_usable": len([x for x in forecast_items if x.get("status") in {"可预测", "行情推演"}]),
            "hot_goods": goods_rank[0]["goods_name"] if goods_rank else (price_series[0]["product_name"] if price_series else "—"),
            "quote_count": quote_count,
            "business_goods": len(goods_names),
        },
        "category_mix": category_mix,
        "goods_rank": goods_rank,
        "forecast_items": forecast_items[:12],
        "price_series": price_series[:24],
        "impact_items": impact_items[:8],
        "map_points": map_points[:limit],
        "threshold_note": "产业洞察：业务侧来自订单品类/商品快照/供应商报价；行情侧来自全国农产品价格与价格预测表。",
    }


def _city_mock_payload(reason: str = "", district_name: Optional[str] = None) -> dict[str, Any]:
    districts = [
        {"district_name": "朝阳区", "gmv": 386000, "order_count": 86, "client_count": 18, "canteen_count": 22, "risk_count": 3, "fulfillment_count": 12, "growth_pct": 12.6},
        {"district_name": "海淀区", "gmv": 342000, "order_count": 73, "client_count": 16, "canteen_count": 19, "risk_count": 5, "fulfillment_count": 10, "growth_pct": 8.1},
        {"district_name": "通州区", "gmv": 238000, "order_count": 48, "client_count": 11, "canteen_count": 13, "risk_count": 1, "fulfillment_count": 8, "growth_pct": 16.3},
        {"district_name": "大兴区", "gmv": 191000, "order_count": 42, "client_count": 9, "canteen_count": 10, "risk_count": 2, "fulfillment_count": 6, "growth_pct": 5.4},
    ]
    dnorm = _norm_district(district_name)
    if dnorm:
        districts = [x for x in districts if x["district_name"] == dnorm] or districts[:1]
    points = []
    for d in districts:
        lng, lat = _DISTRICT_GEO.get(d["district_name"], _DISTRICT_GEO["其他"])
        points.append(
            {
                "role": "city_profile",
                "stage": "risk" if d["risk_count"] >= 4 else "heat",
                "profile_type": "district",
                "district_name": d["district_name"],
                "lng": lng,
                "lat": lat,
                "customer_name": d["district_name"],
                "address": f"{d['district_name']}经营画像",
                "description": f"GMV ¥{d['gmv']:.0f} · 风险 {d['risk_count']} · 食堂 {d['canteen_count']}",
                "order_count": d["order_count"],
                "gmv": d["gmv"],
                "client_count": d["client_count"],
                "canteen_count": d["canteen_count"],
                "risk_count": d["risk_count"],
            }
        )
    return {
        "date": _cn_today().isoformat(),
        "data_mode": "mock",
        "mock_reason": reason,
        "district_name": dnorm,
        "summary": {
            "district_cover_count": len(districts),
            "active_clients": sum(x["client_count"] for x in districts),
            "active_canteens": sum(x["canteen_count"] for x in districts),
            "total_gmv": round(sum(x["gmv"] for x in districts), 2),
            "total_orders": sum(x["order_count"] for x in districts),
            "risk_events": sum(x["risk_count"] for x in districts),
        },
        "district_profiles": districts,
        "growth_districts": sorted(districts, key=lambda x: x["growth_pct"], reverse=True)[:4],
        "risk_districts": sorted(districts, key=lambda x: x["risk_count"], reverse=True)[:4],
        "thin_areas": [x for x in districts if x["client_count"] <= 10][:4],
        "map_points": points,
    }


@router.get("/city-profile-overview")
async def city_profile_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(80, ge=1, le=200),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    prev_start = start - timedelta(days=(end - start).days + 1)
    prev_end = start - timedelta(days=1)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    prev_rows = await _orders_with_context(db, prev_start, prev_end, district_name=district_name)
    if not rows and not prev_rows:
        return _city_mock_payload("empty", district_name)

    by: dict[str, dict[str, Any]] = defaultdict(lambda: {"gmv": 0.0, "order_count": 0, "clients": set(), "canteens": set(), "risk_count": 0, "points": []})
    prev_gmv: dict[str, float] = defaultdict(float)
    for o, canteen, client in prev_rows:
        name = _addr_district(_row_addr(o, canteen)) or "其他"
        prev_gmv[name] += _json_number(o.total_amount)
    for o, canteen, client in rows:
        name = _addr_district(_row_addr(o, canteen)) or "其他"
        slot = by[name]
        slot["gmv"] += _json_number(o.total_amount)
        slot["order_count"] += 1
        slot["clients"].add(int(o.client_id or 0))
        if o.canteen_id:
            slot["canteens"].add(int(o.canteen_id))
        if bool(o.has_abnormal):
            slot["risk_count"] += 1
        lng, lat = _row_coord(o, canteen)
        if lng is not None and lat is not None:
            slot["points"].append(
                {
                    "lng": float(lng),
                    "lat": float(lat),
                    "address": _row_addr(o, canteen),
                    "customer_name": _row_customer(o, canteen, client),
                    "gmv": _json_number(o.total_amount),
                    "order_id": int(o.id),
                    "order_sn": o.order_no,
                }
            )

    order_ids = [int(o.id) for o, _c, _u in rows]
    if order_ids:
        returns = (
            await db.scalars(select(OrderReturn).where(OrderReturn.order_id.in_(order_ids)))
        ).all()
        return_by_order = {int(r.order_id) for r in returns}
        for o, canteen, _client in rows:
            if int(o.id) in return_by_order:
                name = _addr_district(_row_addr(o, canteen)) or "其他"
                by[name]["risk_count"] += 1

    trips = (
        await db.scalars(
            select(DeliveryDispatchTrip)
            .where(DeliveryDispatchTrip.planning_date >= start, DeliveryDispatchTrip.planning_date <= end)
            .limit(500)
        )
    ).all()
    trip_count = len(trips)
    per_district_trip = max(0, round(trip_count / max(1, len(by))))
    profiles = []
    for name, v in by.items():
        old = prev_gmv.get(name, 0.0)
        now = float(v["gmv"])
        profiles.append(
            {
                "district_name": name,
                "gmv": round(now, 2),
                "order_count": int(v["order_count"]),
                "client_count": len([x for x in v["clients"] if x]),
                "canteen_count": len(v["canteens"]) or len([x for x in v["clients"] if x]),
                "risk_count": int(v["risk_count"]),
                "fulfillment_count": per_district_trip,
                "growth_pct": round(100 * (now - old) / old, 2) if old else (100.0 if now else 0.0),
            }
        )
    profiles.sort(key=lambda x: x["gmv"], reverse=True)
    map_points = []
    for p in profiles[:limit]:
        points = by[p["district_name"]]["points"]
        if points:
            anchor = max(points, key=lambda x: x["gmv"])
            lng, lat = anchor["lng"], anchor["lat"]
            addr = anchor["address"]
            customer = anchor["customer_name"]
        else:
            lng, lat = _DISTRICT_GEO.get(p["district_name"], _DISTRICT_GEO["其他"])
            addr = f"{p['district_name']}经营画像"
            customer = p["district_name"]
        stage = "risk" if p["risk_count"] >= 3 else ("thin" if p["client_count"] <= 2 else "heat")
        map_points.append(
            {
                "role": "city_profile",
                "stage": stage,
                "profile_type": "district",
                "district_name": p["district_name"],
                "lng": lng,
                "lat": lat,
                "customer_name": customer,
                "address": addr,
                "description": f"{p['district_name']} · GMV ¥{p['gmv']:.0f} · 风险 {p['risk_count']} · 食堂 {p['canteen_count']}",
                "order_count": p["order_count"],
                "gmv": p["gmv"],
                "client_count": p["client_count"],
                "canteen_count": p["canteen_count"],
                "risk_count": p["risk_count"],
            }
        )

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "date": end.isoformat(),
        "district_name": _norm_district(district_name),
        "data_mode": "real" if rows else "empty",
        "summary": {
            "district_cover_count": len(profiles),
            "active_clients": sum(x["client_count"] for x in profiles),
            "active_canteens": sum(x["canteen_count"] for x in profiles),
            "total_gmv": round(sum(x["gmv"] for x in profiles), 2),
            "total_orders": sum(x["order_count"] for x in profiles),
            "risk_events": sum(x["risk_count"] for x in profiles),
        },
        "district_profiles": profiles[:limit],
        "growth_districts": sorted(profiles, key=lambda x: x["growth_pct"], reverse=True)[:8],
        "risk_districts": sorted(profiles, key=lambda x: x["risk_count"], reverse=True)[:8],
        "thin_areas": sorted([x for x in profiles if x["client_count"] <= 2 or x["order_count"] <= 2], key=lambda x: (x["client_count"], x["order_count"]))[:8],
        "map_points": map_points[:limit],
        "threshold_note": "城市画像：区县来自配送地址；客户/食堂覆盖来自订单关联；风险密度来自异常订单与退单。",
    }


@router.get("/risk-warning-overview")
async def risk_warning_overview(
    limit: int = Query(40, ge=1, le=120),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    day = _cn_today()
    rows = await _orders_with_context(db, day, day, district_name=district_name)
    orders = [o for o, _c, _u in rows]
    order_ids = [int(o.id) for o in orders]

    returns: list[tuple[OrderReturn, Order, Optional[ClientCanteen], Optional[User]]] = []
    if order_ids:
        returns = list(
            (
                await db.execute(
                    select(OrderReturn, Order, ClientCanteen, User)
                    .join(Order, Order.id == OrderReturn.order_id)
                    .outerjoin(ClientCanteen, Order.canteen_id == ClientCanteen.id)
                    .outerjoin(User, Order.client_id == User.id)
                    .where(OrderReturn.order_id.in_(order_ids))
                    .order_by(OrderReturn.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )
    return_ids = {int(r.order_id) for r, _o, _c, _u in returns}
    abnormal_rows = [
        (o, c, u)
        for o, c, u in rows
        if bool(o.has_abnormal) and int(o.id) not in return_ids
    ]

    start_dt, end_dt = _utc_naive_bounds(day, day)
    alert_rows = list(
        (
            await db.scalars(
                select(Alert)
                .where(Alert.created_at >= start_dt, Alert.created_at < end_dt)
                .order_by(Alert.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    open_alerts = [a for a in alert_rows if str(a.status or "open") == "open"]

    def severity_rank(level: Optional[str]) -> int:
        level_text = str(level or "").lower()
        return {"high": 3, "medium": 2, "low": 1}.get(level_text, 1)

    def level_label(level: Optional[str]) -> str:
        level_text = str(level or "").lower()
        return {"high": "高", "medium": "中", "low": "低"}.get(level_text, "中")

    def order_point(
        order: Order,
        canteen: Optional[ClientCanteen],
        client: Optional[User],
        *,
        risk_type: str,
        risk_level: str,
        description: str,
        created_at: Optional[datetime],
    ) -> Optional[dict[str, Any]]:
        lng, lat = _row_coord(order, canteen)
        if lng is None or lat is None:
            return None
        amount = _json_number(order.total_amount)
        return {
            "role": "risk",
            "risk_type": risk_type,
            "risk_level": risk_level,
            "address": _row_addr(order, canteen),
            "customer_name": _row_customer(order, canteen, client),
            "order_count": 1,
            "gmv": round(amount, 2),
            "lng": float(lng),
            "lat": float(lat),
            "order_id": int(order.id),
            "order_sn": order.order_no,
            "description": description,
            "created_at": _to_ts(created_at or order.created_at),
        }

    risk_points: list[dict[str, Any]] = []
    latest_items: list[dict[str, Any]] = []

    for r, o, canteen, client in returns:
        desc = f"退单待复核：{r.source or '业务退单'}"
        point = order_point(
            o,
            canteen,
            client,
            risk_type="return",
            risk_level="high",
            description=desc,
            created_at=r.created_at,
        )
        if point:
            risk_points.append(point)
        latest_items.append(
            {
                "id": f"return:{int(r.id)}",
                "type": "退单",
                "level": "高",
                "status": "待复核",
                "order_id": int(o.id),
                "order_sn": o.order_no,
                "customer_name": _row_customer(o, canteen, client),
                "amount": round(_json_number(o.total_amount), 2),
                "description": desc,
                "created_at": _to_ts(r.created_at),
            }
        )

    for o, canteen, client in abnormal_rows[:limit]:
        desc = "异常订单待处置"
        point = order_point(
            o,
            canteen,
            client,
            risk_type="abnormal_order",
            risk_level="medium",
            description=desc,
            created_at=o.updated_at or o.created_at,
        )
        if point:
            risk_points.append(point)
        latest_items.append(
            {
                "id": f"abnormal:{int(o.id)}",
                "type": "异常订单",
                "level": "中",
                "status": str(o.status or "待处置"),
                "order_id": int(o.id),
                "order_sn": o.order_no,
                "customer_name": _row_customer(o, canteen, client),
                "amount": round(_json_number(o.total_amount), 2),
                "description": desc,
                "created_at": _to_ts(o.updated_at or o.created_at),
            }
        )

    # Alert 当前模型不强制绑定订单；没有坐标时以前几条订单风险点承载告警态势，仍保留列表真实内容。
    anchor_points = risk_points[: max(1, min(6, len(risk_points)))]
    for idx, a in enumerate(open_alerts):
        anchor = anchor_points[idx % len(anchor_points)] if anchor_points else None
        if anchor:
            risk_points.append(
                {
                    **anchor,
                    "role": "risk",
                    "risk_type": "alert",
                    "risk_level": str(a.level or "medium"),
                    "description": a.description or a.type or "开放告警",
                    "created_at": _to_ts(a.created_at),
                    "gmv": 0,
                    "order_count": 1,
                }
            )
        latest_items.append(
            {
                "id": f"alert:{int(a.id)}",
                "type": a.type or "告警",
                "level": level_label(a.level),
                "status": str(a.status or "open"),
                "order_id": None,
                "order_sn": "",
                "customer_name": "监管告警",
                "amount": 0,
                "description": a.description or "",
                "created_at": _to_ts(a.created_at),
            }
        )

    latest_items.sort(key=lambda x: int(x.get("created_at") or 0), reverse=True)
    risk_points.sort(
        key=lambda x: (
            severity_rank(str(x.get("risk_level") or "")),
            float(x.get("gmv") or 0),
            int(x.get("created_at") or 0),
        ),
        reverse=True,
    )

    return_amount = round(
        sum(_json_number(o.total_amount) for _r, o, _c, _u in returns),
        2,
    )
    abnormal_amount = round(
        sum(_json_number(o.total_amount) for o, _c, _u in abnormal_rows),
        2,
    )
    pending_count = len(return_ids) + len(abnormal_rows) + len(open_alerts)
    high_count = len(return_ids) + len([a for a in open_alerts if str(a.level or "").lower() == "high"])
    medium_count = len(abnormal_rows) + len([a for a in open_alerts if str(a.level or "").lower() == "medium"])
    low_count = len([a for a in open_alerts if str(a.level or "").lower() == "low"])

    return {
        "data_mode": "real" if pending_count or risk_points or latest_items else "empty",
        "date": day.isoformat(),
        "district_name": _norm_district(district_name),
        "kpis": {
            "open_alerts": len(open_alerts),
            "abnormal_orders": len(abnormal_rows),
            "return_amount": return_amount,
            "pending_count": pending_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "abnormal_amount": abnormal_amount,
        },
        "risk_distribution": [
            {"key": "alert", "label": "开放告警", "count": len(open_alerts)},
            {"key": "return", "label": "退单风险", "count": len(return_ids)},
            {"key": "abnormal_order", "label": "异常订单", "count": len(abnormal_rows)},
            {"key": "delivery", "label": "配送异常", "count": len([x for x in latest_items if "配送" in str(x.get("type") or "")])},
        ],
        "risk_points": risk_points[:limit],
        "latest_items": latest_items[:limit],
        "recommendations": [
            {
                "title": "高风险优先闭环",
                "content": f"今日高风险 {high_count} 项，优先核对退单金额与开放高等级告警。",
            },
            {
                "title": "异常订单追责",
                "content": f"异常订单 {len(abnormal_rows)} 单，建议按配送商、食堂、订单状态拆分责任人。",
            },
            {
                "title": "退单资金复核",
                "content": f"退单金额 ¥{return_amount:.2f}，建议与账单中心、收货差异记录交叉复核。",
            },
        ],
        "threshold_note": "退单=order_returns；异常订单=orders.has_abnormal；开放告警=alerts.status=open。",
    }


@router.get("/today-orders-list")
async def today_orders_list(
    limit: int = Query(500, ge=1, le=2000),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    day = _cn_today()
    rows = await _orders_with_context(db, day, day, limit=limit)
    return {
        "day": day.isoformat(),
        "day_start_ts": int(datetime.combine(day, time.min, tzinfo=_TZ).timestamp()),
        "day_end_ts": int(datetime.now(_TZ).timestamp()),
        "limit": limit,
        "rows": [
            {
                "id": int(o.id),
                "order_sn": o.order_no,
                "add_time": _to_ts(o.created_at),
                "total_amount": _json_number(o.total_amount),
                "customer_name": _row_customer(o, canteen, client),
                "member_address": _row_addr(o, canteen),
            }
            for o, canteen, client in rows
        ],
    }


@router.get("/member-orders-in-range")
async def member_orders_in_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    member_id: Optional[int] = None,
    address: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    addr = (address or "").strip()
    if not member_id and not addr:
        raise HTTPException(400, "须提供 member_id 或 address")
    start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end)
    out = []
    for o, canteen, client in rows:
        if member_id and _order_key(o) != int(member_id):
            continue
        if addr and _row_addr(o, canteen) != addr:
            continue
        out.append(
            {
                "id": int(o.id),
                "order_sn": o.order_no,
                "add_time": _to_ts(o.created_at),
                "total_amount": _json_number(o.total_amount),
                "customer_name": _row_customer(o, canteen, client),
                "member_address": _row_addr(o, canteen),
            }
        )
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "member_id": member_id,
        "address": addr or None,
        "rows": out[:500],
    }


@router.get("/order-line-items")
async def order_line_items(
    order_id: int,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    return {"order_id": order_id, "rows": _line_rows(order)}


@router.get("/category-distribution")
async def category_distribution(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(12, ge=1, le=50),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    products = (await db.scalars(select(Product).where(Product.is_deleted == False))).all()  # noqa: E712
    categories = (await db.scalars(select(Category).where(Category.is_deleted == False))).all()  # noqa: E712
    product_map = {int(p.id): p for p in products}
    category_map = {int(c.id): c.name for c in categories}
    by_cat: dict[str, dict[str, Any]] = defaultdict(lambda: {"order_ids": set(), "total_amount": 0.0, "total_quantity": 0.0})
    for o, _c, _u in rows:
        order_seen = set()
        for line in _line_rows(o):
            product_id = None
            for raw in (o.items_json or []):
                if isinstance(raw, dict) and (raw.get("product_name") == line["goods_name"] or raw.get("goods_name") == line["goods_name"]):
                    product_id = raw.get("product_id")
                    break
            product = product_map.get(int(product_id or 0))
            name = line["category1_name"] or (category_map.get(int(product.category1_id)) if product else None) or "未归类"
            slot = by_cat[name]
            slot["total_amount"] += _json_number(line["line_amount"])
            slot["total_quantity"] += _json_number(line["qty"])
            order_seen.add(name)
        for name in order_seen:
            by_cat[name]["order_ids"].add(int(o.id))
    out = []
    for name, r in sorted(by_cat.items(), key=lambda item: item[1]["total_amount"], reverse=True)[:limit]:
        out.append(
            {
                "category_name": name,
                "order_count": len(r["order_ids"]),
                "total_amount": round(float(r["total_amount"]), 2),
                "total_quantity": round(float(r["total_quantity"]), 3),
            }
        )
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "rows": out}


@router.get("/backorder-daily")
async def backorder_daily(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    order_map = {int(o.id): o for o, _c, _u in rows}
    order_ids = list(order_map)
    returns = []
    if order_ids:
        start_dt, end_dt = _utc_naive_bounds(start, end)
        returns = (
            await db.scalars(
                select(OrderReturn)
                .where(
                    OrderReturn.order_id.in_(order_ids),
                    OrderReturn.created_at >= start_dt,
                    OrderReturn.created_at < end_dt,
                )
                .order_by(OrderReturn.created_at.asc())
            )
        ).all()
    by_day: dict[str, dict[str, Any]] = {}
    for i in range((end - start).days + 1):
        day = (start + timedelta(days=i)).isoformat()
        by_day[day] = {"day": day, "backorder_count": 0, "backorder_amount": 0.0}
    for r in returns:
        day = _cn_day(r.created_at).isoformat()
        order = order_map.get(int(r.order_id))
        slot = by_day.setdefault(day, {"day": day, "backorder_count": 0, "backorder_amount": 0.0})
        slot["backorder_count"] += 1
        slot["backorder_amount"] += _json_number(order.total_amount if order else 0)
    series = list(by_day.values())
    for row in series:
        row["backorder_amount"] = round(float(row["backorder_amount"]), 2)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "series": series,
        "summary": {
            "backorder_count": sum(int(r["backorder_count"]) for r in series),
            "backorder_amount": round(sum(float(r["backorder_amount"]) for r in series), 2),
        },
    }


@router.get("/orders-calendar-heatmap")
async def orders_calendar_heatmap(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date, default_span_days=60)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    by_day: dict[str, dict[str, Any]] = {}
    for i in range((end - start).days + 1):
        day = (start + timedelta(days=i)).isoformat()
        by_day[day] = {"date": day, "order_count": 0, "gmv": 0.0}
    for o, _c, _u in rows:
        day = _cn_day(o.created_at).isoformat()
        slot = by_day.setdefault(day, {"date": day, "order_count": 0, "gmv": 0.0})
        slot["order_count"] += 1
        slot["gmv"] += _json_number(o.total_amount)
    cells = list(sorted(by_day.values(), key=lambda row: row["date"]))
    for row in cells:
        row["gmv"] = round(float(row["gmv"]), 2)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "cells": cells,
        "max_order_count": max([int(r["order_count"]) for r in cells] or [0]),
    }


@router.get("/order-head")
async def order_head(
    order_id: int,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(Order, ClientCanteen, User)
            .outerjoin(ClientCanteen, Order.canteen_id == ClientCanteen.id)
            .outerjoin(User, Order.client_id == User.id)
            .where(Order.id == order_id)
        )
    ).first()
    if not row:
        raise HTTPException(404, "订单不存在")
    o, canteen, client = row
    return {
        "id": int(o.id),
        "order_sn": o.order_no,
        "add_time": _to_ts(o.created_at),
        "status": o.status,
        "total_amount": _json_number(o.total_amount),
        "member_id": _order_key(o),
        "member_realname": _row_customer(o, canteen, client),
        "member_address": _row_addr(o, canteen),
        "delivery_date": o.expected_delivery_date.isoformat() if o.expected_delivery_date else None,
        "delivery_slot": o.expected_delivery_slot,
        "has_abnormal": bool(o.has_abnormal),
    }


@router.get("/meta/tables")
async def meta_tables(_=Depends(_monitor_guard)):
    tables = []
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        tables.append(
            {
                "table_name": table.name,
                "columns": [
                    {
                        "name": column.name,
                        "type": str(column.type),
                        "nullable": bool(column.nullable),
                        "primary_key": bool(column.primary_key),
                    }
                    for column in table.columns
                ],
            }
        )
    return {"tables": tables}


@router.get("/xinfadi-summary-series")
async def xinfadi_summary_series(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    product_name: Optional[str] = None,
    limit: int = Query(30, ge=1, le=180),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date, default_span_days=min(limit, 30))
    products_stmt = select(Product).where(Product.is_deleted == False)  # noqa: E712
    if product_name:
        products_stmt = products_stmt.where(Product.name.like(f"%{product_name.strip()}%"))
    products = (await db.scalars(products_stmt.limit(100))).all()
    product_ids = [int(p.id) for p in products]
    quotes = []
    if product_ids:
        quotes = (
            await db.scalars(
                select(SupplierProductQuote).where(SupplierProductQuote.product_id.in_(product_ids))
            )
        ).all()
    prices = [_json_number(p.reference_price) for p in products if _json_number(p.reference_price) > 0]
    prices.extend(_json_number(q.quote_price) for q in quotes if _json_number(q.quote_price) > 0)
    baseline = sum(prices) / len(prices) if prices else 0.0
    series = []
    total_days = (end - start).days + 1
    for i in range(total_days):
        day = start + timedelta(days=i)
        drift = ((i % 7) - 3) * 0.006
        avg_price = round(baseline * (1 + drift), 2) if baseline else 0.0
        series.append(
            {
                "date": day.isoformat(),
                "avg_price": avg_price,
                "min_price": round(avg_price * 0.94, 2) if avg_price else 0.0,
                "max_price": round(avg_price * 1.08, 2) if avg_price else 0.0,
                "sample_count": len(products) + len(quotes),
            }
        )
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "product_name": product_name,
        "series": series,
        "summary": {
            "product_count": len(products),
            "quote_count": len(quotes),
            "baseline_price": round(baseline, 2),
        },
    }


async def _ws_user(websocket: WebSocket) -> Optional[dict[str, Any]]:
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=1008)
        return None
    try:
        payload = decode_access_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return None
    if payload.get("role") != "monitor":
        await websocket.close(code=1008)
        return None
    return payload


async def _today_ws_summary(db: AsyncSession) -> tuple[float, int, int, int]:
    day = _cn_today()
    rows = await _orders_with_context(db, day, day)
    if not rows:
        return 0.0, 0, int(datetime.combine(day, time.min, tzinfo=_TZ).timestamp()), 0
    gmv = round(sum(_json_number(o.total_amount) for o, _c, _u in rows), 2)
    last = max((o for o, _c, _u in rows), key=lambda x: (x.created_at, x.id))
    return gmv, len(rows), _to_ts(last.created_at), int(last.id)


@router.websocket("/ws/live-gmv")
async def ws_live_gmv(websocket: WebSocket):
    payload = await _ws_user(websocket)
    if not payload:
        return
    await websocket.accept()
    last_ts = 0
    last_id = 0
    try:
        async with SessionLocal() as db:
            gmv, count, last_ts, last_id = await _today_ws_summary(db)
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "cumulative_gmv": gmv,
                    "order_count": count,
                    "watermark_add_time": last_ts,
                    "watermark_id": last_id,
                    "today_t0": int(datetime.combine(_cn_today(), time.min, tzinfo=_TZ).timestamp()),
                    "initialized": True,
                }
            )
        tick = 0
        while True:
            await asyncio.sleep(3)
            tick += 3
            if tick >= 60:
                tick = 0
                await websocket.send_json({"type": "ping"})
            # 只在会话内取数，取完立即释放连接；网络发送(send_json)放到会话外，
            # 避免慢/半死的 WS 客户端在 send 阻塞时一直占着数据库连接 → 连接池耗尽。
            batch_payload = None
            async with SessionLocal() as db:
                day = _cn_today()
                rows = await _orders_with_context(db, day, day)
                new_orders = [
                    o
                    for o, _c, _u in rows
                    if (_to_ts(o.created_at) > last_ts)
                    or (_to_ts(o.created_at) == last_ts and int(o.id) > last_id)
                ]
                if new_orders:
                    new_orders.sort(key=lambda o: (o.created_at, o.id))
                    gmv, count, last_ts, last_id = await _today_ws_summary(db)
                    day_t0 = int(datetime.combine(day, time.min, tzinfo=_TZ).timestamp())
                    batch_payload = {
                        "type": "batch",
                        "rows": [
                            {
                                "id": int(o.id),
                                "add_time": _to_ts(o.created_at),
                                "amount": _json_number(o.total_amount),
                                "minute_start": day_t0 + ((_to_ts(o.created_at) - day_t0) // 60) * 60,
                            }
                            for o in new_orders[:200]
                        ],
                        "cumulative_gmv": gmv,
                        "order_count": count,
                        "avg_ticket": round(gmv / count, 2) if count else 0.0,
                    }
            # 数据库连接此处已归还连接池，再做网络发送
            if batch_payload is not None:
                await websocket.send_json(batch_payload)
    except WebSocketDisconnect:
        return
    except Exception:
        with contextlib.suppress(Exception):
            await websocket.close(code=1011)
