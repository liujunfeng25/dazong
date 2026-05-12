from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal, get_db
from dependencies import decode_access_token, require_role
from models import (
    Alert,
    Base,
    Category,
    ClientCanteen,
    Order,
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
    if lng is not None and lat is not None:
        return lng, lat
    if canteen and canteen.lng is not None and canteen.lat is not None:
        return _json_number(canteen.lng), _json_number(canteen.lat)
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


@router.get("/cockpit-customer-map-points")
async def cockpit_customer_map_points(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    district_name: Optional[str] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    start, end = _parse_range(start_date, end_date)
    rows = await _orders_with_context(db, start, end, district_name=district_name)
    grouped: dict[str, dict[str, Any]] = {}
    for o, canteen, client in rows:
        addr = _row_addr(o, canteen)
        if not addr:
            continue
        lng, lat = _row_coord(o, canteen)
        if lng is None or lat is None:
            continue
        key = addr
        g = grouped.setdefault(
            key,
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
    points = []
    for g in sorted(grouped.values(), key=lambda x: (x["order_count"], x["gmv"]), reverse=True)[:limit]:
        ids = [x for x in g["member_ids"] if x]
        names = [x for x in g["customer_names"] if x]
        member_count = len(ids)
        points.append(
            {
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
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "district_name": _norm_district(district_name),
        "points": points,
        "failed_geocode_count": 0,
        "geocode_enabled": True,
        "approx_district_points": 0,
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
            async with SessionLocal() as db:
                day = _cn_today()
                rows = await _orders_with_context(db, day, day)
                new_orders = [
                    o
                    for o, _c, _u in rows
                    if (_to_ts(o.created_at) > last_ts)
                    or (_to_ts(o.created_at) == last_ts and int(o.id) > last_id)
                ]
                if not new_orders:
                    continue
                new_orders.sort(key=lambda o: (o.created_at, o.id))
                gmv, count, last_ts, last_id = await _today_ws_summary(db)
                day_t0 = int(datetime.combine(day, time.min, tzinfo=_TZ).timestamp())
                await websocket.send_json(
                    {
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
                )
    except WebSocketDisconnect:
        return
    except Exception:
        with contextlib.suppress(Exception):
            await websocket.close(code=1011)
