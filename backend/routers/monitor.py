from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models import (
    Alert,
    AuditLog,
    Bill,
    Category,
    ClientCanteen,
    Delivery,
    DeliveryDevice,
    DeliveryVehicle,
    IoTData,
    Order,
    OrderItemAllocation,
    OrderReturn,
    Product,
    QualityReport,
    SupplierProductQuote,
    Ticket,
    User,
)
from services.alert_state_machine import ensure_alert_transition
from services.audit_service import write_audit_log
from services.outbox_service import add_outbox_event
from services.planning_display_notes import ESTIMATED_ON_TIME_RATE_NOTE_CN
router = APIRouter(prefix="/monitor", tags=["monitor"])


def _audit_meta(request: Request) -> dict:
    return {
        "trace_id": getattr(request.state, "trace_id", ""),
        "source_ip": request.client.host if request.client else "",
    }


def _num(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _line_rows(order: Order) -> list[dict[str, Any]]:
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    rows: list[dict[str, Any]] = []
    for idx in range(max(len(items), len(snaps))):
        item = items[idx] if idx < len(items) and isinstance(items[idx], dict) else {}
        snap = snaps[idx] if idx < len(snaps) and isinstance(snaps[idx], dict) else {}
        qty = _num(snap.get("order_quantity", item.get("quantity", item.get("qty", 0))))
        unit_price = _num(snap.get("order_unit_price", item.get("unit_price", item.get("price", 0))))
        product_id = item.get("product_id") or snap.get("product_id")
        name = (
            str(snap.get("product_name") or item.get("product_name") or item.get("goods_name") or "").strip()
            or f"商品#{product_id or idx + 1}"
        )
        rows.append(
            {
                "product_id": int(product_id) if str(product_id or "").isdigit() else None,
                "goods_name": name,
                "category1_name": str(snap.get("category1_name") or ""),
                "spec": str(snap.get("spec") or item.get("spec") or "标准"),
                "unit": str(snap.get("unit") or item.get("unit") or ""),
                "qty": qty,
                "unit_price": unit_price,
                "line_amount": round(qty * unit_price, 2),
            }
        )
    return rows


def _order_day(order: Order) -> date:
    return order.created_at.date() if order.created_at else datetime.utcnow().date()


def _status_bucket(status: str) -> str:
    return {
        "下单": "下单",
        "配货": "配货",
        "发货": "在途",
        "收货": "收货",
        "收货确认": "确认",
        "已结算": "结算",
        "取消": "取消",
    }.get(status or "", status or "未知")


def _user_name(user_map: dict[int, User], user_id: Optional[int], prefix: str) -> str:
    if not user_id:
        return f"{prefix}未分配"
    u = user_map.get(int(user_id))
    if not u:
        return f"{prefix}#{user_id}"
    return u.company_name or u.username or f"{prefix}#{user_id}"


def _canteen_name(canteen_map: dict[int, ClientCanteen], order: Order, user_map: dict[int, User]) -> str:
    if order.canteen_id and int(order.canteen_id) in canteen_map:
        return canteen_map[int(order.canteen_id)].name
    return _user_name(user_map, order.client_id, "客户")


def _pct(part: float, total: float) -> float:
    return round((part / total * 100), 2) if total else 0.0


def _severity_weight(level: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(level or "", 0)


def _district_from_address(address: Optional[str]) -> str:
    text = address or ""
    for name in (
        "东城区",
        "西城区",
        "朝阳区",
        "丰台区",
        "石景山区",
        "海淀区",
        "门头沟区",
        "房山区",
        "通州区",
        "顺义区",
        "昌平区",
        "大兴区",
        "怀柔区",
        "平谷区",
        "密云区",
        "延庆区",
        "雄安",
        "容城县",
        "雄县",
        "安新县",
    ):
        if name in text:
            return "雄安" if name in {"容城县", "雄县", "安新县"} else name
    return "未标注区域"


@router.get("/dashboard")
async def monitor_dashboard(
    _=Depends(require_role("monitor")), db: AsyncSession = Depends(get_db)
):
    today = datetime.utcnow().date()
    orders = (await db.scalars(select(Order))).all()
    alerts = (await db.scalars(select(Alert).order_by(Alert.id.desc()).limit(20))).all()
    today_orders = [o for o in orders if o.created_at.date() == today]
    active_vehicles = len((await db.scalars(select(Delivery).where(Delivery.status == "运输中"))).all())
    status_count = {}
    for o in orders:
        status_count[o.status] = status_count.get(o.status, 0) + 1

    seven_days = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        seven_days.append(
            {
                "date": day.isoformat(),
                "count": len([o for o in orders if o.created_at.date() == day]),
            }
        )
    return {
        "today_orders": len(today_orders),
        "today_gmv": float(sum(float(o.total_amount) for o in today_orders)),
        "active_vehicles": active_vehicles,
        "pending_alerts": len([a for a in alerts if a.status == "open"]),
        "order_status_distribution": status_count,
        "order_trend_7d": seven_days,
        "supplier_performance": [
            {"name": "supplier001", "rate": 96},
            {"name": "supplier002", "rate": 92},
            {"name": "supplier003", "rate": 88},
            {"name": "supplier004", "rate": 84},
            {"name": "supplier005", "rate": 81},
        ],
        "category_purchase_ratio": [
            {"name": "蔬菜", "value": 35},
            {"name": "水果", "value": 20},
            {"name": "粮油", "value": 18},
            {"name": "肉禽蛋", "value": 15},
            {"name": "水产", "value": 7},
            {"name": "调味品", "value": 5},
        ],
        "latest_orders": [
            {
                "order_id": o.id,
                "order_no": o.order_no,
                "status": o.status,
                "created_at": o.created_at.isoformat(),
            }
            for o in orders[-10:]
        ],
        "latest_alerts": [
            {
                "id": a.id,
                "level": a.level,
                "type": a.type,
                "description": a.description,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ],
    }


@router.get("/neural/overview")
async def monitor_neural_overview(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.utcnow().date()
    orders = (await db.scalars(select(Order).order_by(Order.id.desc()).limit(2000))).all()
    alerts = (await db.scalars(select(Alert).order_by(Alert.id.desc()).limit(80))).all()
    deliveries = (await db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(500))).all()
    returns = (await db.scalars(select(OrderReturn).order_by(OrderReturn.id.desc()).limit(500))).all()
    tickets = (await db.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(500))).all()
    quality_reports = (
        await db.scalars(select(QualityReport).order_by(QualityReport.id.desc()).limit(500))
    ).all()
    bills = (await db.scalars(select(Bill).order_by(Bill.id.desc()).limit(500))).all()
    canteens = (await db.scalars(select(ClientCanteen))).all()
    canteen_map = {int(c.id): c for c in canteens}

    user_ids = {
        int(uid)
        for o in orders
        for uid in (o.client_id, o.delivery_id, o.supplier_id)
        if uid is not None
    }
    user_ids.update(int(t.created_by) for t in tickets if t.created_by)
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(u.id): u for u in users}

    today_orders = [o for o in orders if _order_day(o) == today]
    open_alerts = [a for a in alerts if a.status == "open"]
    abnormal_orders = [o for o in orders if bool(o.has_abnormal)]
    active_deliveries = [d for d in deliveries if d.status == "运输中"]
    pending_tickets = [t for t in tickets if t.status != "已关闭"]
    pending_quality = [q for q in quality_reports if q.status != "已通过"]
    pending_bills = [b for b in bills if b.status != "已结算"]

    status_count = Counter(_status_bucket(o.status) for o in orders)
    status_total = sum(status_count.values())
    lifecycle = [
        {
            "name": name,
            "count": int(status_count.get(name, 0)),
            "percent": _pct(status_count.get(name, 0), status_total),
        }
        for name in ("下单", "配货", "在途", "收货", "确认", "结算", "取消")
    ]

    seven_days = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        rows = [o for o in orders if _order_day(o) == day]
        seven_days.append(
            {
                "date": day.isoformat(),
                "count": len(rows),
                "gmv": round(sum(_num(o.total_amount) for o in rows), 2),
            }
        )

    category_counter: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "amount": 0.0})
    goods_counter: dict[str, dict[str, float]] = defaultdict(lambda: {"qty": 0.0, "amount": 0.0})
    for o in orders:
        for line in _line_rows(o):
            cat = line["category1_name"] or "未归类"
            category_counter[cat]["count"] += 1
            category_counter[cat]["amount"] += _num(line["line_amount"])
            goods_counter[line["goods_name"]]["qty"] += _num(line["qty"])
            goods_counter[line["goods_name"]]["amount"] += _num(line["line_amount"])

    category_purchase_ratio = [
        {"name": name, "value": round(v["amount"], 2), "count": int(v["count"])}
        for name, v in sorted(category_counter.items(), key=lambda item: item[1]["amount"], reverse=True)[:8]
    ]
    top_goods = [
        {"name": name, "value": round(v["amount"], 2), "qty": round(v["qty"], 3)}
        for name, v in sorted(goods_counter.items(), key=lambda item: item[1]["amount"], reverse=True)[:8]
    ]

    recent_events: list[dict[str, Any]] = []
    for o in orders[:20]:
        recent_events.append(
            {
                "id": f"order-{o.id}",
                "kind": "order",
                "level": "normal" if not o.has_abnormal else "warning",
                "title": f"{o.order_no} {_status_bucket(o.status)}",
                "description": f"{_canteen_name(canteen_map, o, user_map)} / ¥{_num(o.total_amount):.2f}",
                "created_at": _iso(o.created_at),
            }
        )
    for a in alerts[:20]:
        recent_events.append(
            {
                "id": f"alert-{a.id}",
                "kind": "alert",
                "level": a.level,
                "title": f"{a.type} 预警",
                "description": a.description,
                "created_at": _iso(a.created_at),
            }
        )
    for t in tickets[:10]:
        recent_events.append(
            {
                "id": f"ticket-{t.id}",
                "kind": "ticket",
                "level": "medium" if t.status != "已关闭" else "low",
                "title": f"{t.type} / {t.status}",
                "description": t.description[:80],
                "created_at": _iso(t.created_at),
            }
        )
    recent_events.sort(key=lambda row: row.get("created_at") or "", reverse=True)

    command_channels = [
        {
            "name": "订单链路",
            "count": len([o for o in orders if o.status in {"下单", "配货", "发货"}]),
            "status": "active",
            "description": "下单、配货、发货节点持续监控",
        },
        {
            "name": "风险预警",
            "count": len(open_alerts),
            "status": "critical" if any(a.level == "high" for a in open_alerts) else "active",
            "description": "开放预警按高、中、低分级接入",
        },
        {
            "name": "质检工单",
            "count": len(pending_quality) + len(pending_tickets),
            "status": "active",
            "description": "质检待审与售后/配送异常工单",
        },
        {
            "name": "账务结算",
            "count": len(pending_bills),
            "status": "active",
            "description": "待结算账单持续归集",
        },
    ]

    today_gmv = sum(_num(o.total_amount) for o in today_orders)
    fulfilled = len([o for o in orders if o.status in {"收货确认", "已结算"}])
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "kpi": {
            "today_orders": len(today_orders),
            "today_gmv": round(today_gmv, 2),
            "active_vehicles": len(active_deliveries),
            "pending_alerts": len(open_alerts),
            "abnormal_orders": len(abnormal_orders),
            "open_tickets": len(pending_tickets),
            "pending_quality": len(pending_quality),
            "return_orders": len(returns),
            "pending_bills": len(pending_bills),
            "avg_ticket": round(today_gmv / len(today_orders), 2) if today_orders else 0.0,
            "fulfillment_rate": _pct(fulfilled, len(orders)),
        },
        "risk_summary": {
            "open_alerts": len(open_alerts),
            "high_alerts": len([a for a in open_alerts if a.level == "high"]),
            "medium_alerts": len([a for a in open_alerts if a.level == "medium"]),
            "low_alerts": len([a for a in open_alerts if a.level == "low"]),
            "abnormal_orders": len(abnormal_orders),
            "pending_tickets": len(pending_tickets),
            "pending_quality": len(pending_quality),
        },
        "order_status_distribution": [
            {"name": name, "value": count}
            for name, count in sorted(status_count.items(), key=lambda item: item[1], reverse=True)
        ],
        "order_trend_7d": seven_days,
        "lifecycle": lifecycle,
        "category_purchase_ratio": category_purchase_ratio,
        "top_goods": top_goods,
        "latest_orders": [
            {
                "order_id": int(o.id),
                "order_no": o.order_no,
                "status": o.status,
                "client_name": _canteen_name(canteen_map, o, user_map),
                "delivery_name": _user_name(user_map, o.delivery_id, "配送商"),
                "amount": _num(o.total_amount),
                "created_at": _iso(o.created_at),
            }
            for o in orders[:12]
        ],
        "latest_alerts": [
            {
                "id": int(a.id),
                "level": a.level,
                "type": a.type,
                "description": a.description,
                "status": a.status,
                "created_at": _iso(a.created_at),
            }
            for a in sorted(alerts[:20], key=lambda row: _severity_weight(row.level), reverse=True)
        ],
        "recent_events": recent_events[:24],
        "command_channels": command_channels,
    }


@router.get("/neural/logistics")
async def monitor_neural_logistics(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    orders = (await db.scalars(select(Order).order_by(Order.id.desc()).limit(1000))).all()
    deliveries = (await db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(500))).all()
    vehicles = (await db.scalars(select(DeliveryVehicle).order_by(DeliveryVehicle.id.desc()).limit(500))).all()
    devices = (await db.scalars(select(DeliveryDevice).order_by(DeliveryDevice.id.desc()).limit(500))).all()
    iot_rows = (await db.scalars(select(IoTData).order_by(IoTData.recorded_at.desc()).limit(300))).all()
    alerts = (await db.scalars(select(Alert).order_by(Alert.id.desc()).limit(100))).all()

    order_map = {int(o.id): o for o in orders}
    user_ids = {int(o.delivery_id) for o in orders if o.delivery_id}
    user_ids.update(int(v.delivery_id) for v in vehicles if v.delivery_id)
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(u.id): u for u in users}

    latest_iot_by_device: dict[str, IoTData] = {}
    for row in iot_rows:
        latest_iot_by_device.setdefault(str(row.device_id), row)

    sensor_cards = []
    for row in iot_rows:
        if row.device_type != "sensor":
            continue
        payload = row.payload_json or {}
        sensor_cards.append(
            {
                "device_id": row.device_id,
                "temperature": _num(payload.get("temperature", payload.get("temp"))),
                "humidity": _num(payload.get("humidity")),
                "recorded_at": _iso(row.recorded_at),
                "status": "normal",
            }
        )
        if len(sensor_cards) >= 12:
            break

    delivery_cards = []
    for d in deliveries[:80]:
        order = order_map.get(int(d.order_id))
        delivery_cards.append(
            {
                "id": int(d.id),
                "order_id": int(d.order_id),
                "order_no": order.order_no if order else f"订单#{d.order_id}",
                "status": d.status,
                "driver_name": d.driver_name,
                "vehicle_no": d.vehicle_no,
                "current_lng": d.current_lng,
                "current_lat": d.current_lat,
                "capacity_weight_kg": _num(d.vehicle_capacity_weight_kg),
                "capacity_volume_m3": _num(d.vehicle_capacity_volume_m3),
                "departed_at": _iso(d.departed_at),
                "arrived_at": _iso(d.arrived_at),
                "route_points": d.route_json or [],
            }
        )

    vehicle_cards = []
    active_delivery_by_no = {d.vehicle_no: d for d in deliveries if d.status == "运输中"}
    for v in vehicles[:80]:
        active = active_delivery_by_no.get(v.vehicle_no)
        vehicle_cards.append(
            {
                "id": int(v.id),
                "vehicle_no": v.vehicle_no,
                "model": v.vehicle_model,
                "driver_name": v.driver_name,
                "delivery_name": _user_name(user_map, v.delivery_id, "配送商"),
                "status": "运输中" if active else v.status,
                "capacity_weight_kg": _num(v.capacity_weight_kg),
                "capacity_volume_m3": _num(v.capacity_volume_m3),
                "current_lng": active.current_lng if active else None,
                "current_lat": active.current_lat if active else None,
            }
        )
    if not vehicle_cards:
        vehicle_cards = [
            {
                "id": int(d.id),
                "vehicle_no": d.vehicle_no,
                "model": "",
                "driver_name": d.driver_name,
                "delivery_name": "配送任务",
                "status": d.status,
                "capacity_weight_kg": _num(d.vehicle_capacity_weight_kg),
                "capacity_volume_m3": _num(d.vehicle_capacity_volume_m3),
                "current_lng": d.current_lng,
                "current_lat": d.current_lat,
            }
            for d in deliveries[:40]
        ]

    exceptions = []
    for d in deliveries:
        order = order_map.get(int(d.order_id))
        if d.status not in {"运输中", "待发车"}:
            continue
        if order and order.expected_delivery_date and order.expected_delivery_date < datetime.utcnow().date():
            exceptions.append(
                {
                    "id": f"late-{d.id}",
                    "type": "delivery_overdue",
                    "level": "high",
                    "title": f"{order.order_no} 配送超期",
                    "description": f"{d.vehicle_no} / {d.driver_name}",
                }
            )
    for a in alerts:
        if a.status == "open" and ("配送" in a.type or "温" in a.type or "车辆" in a.type):
            exceptions.append(
                {
                    "id": f"alert-{a.id}",
                    "type": a.type,
                    "level": a.level,
                    "title": f"{a.type} 预警",
                    "description": a.description,
                }
            )

    capacity_weight = sum(_num(v.capacity_weight_kg) for v in vehicles) or sum(
        _num(d.vehicle_capacity_weight_kg) for d in deliveries
    )
    capacity_volume = sum(_num(v.capacity_volume_m3) for v in vehicles) or sum(
        _num(d.vehicle_capacity_volume_m3) for d in deliveries
    )
    arrived = len([d for d in deliveries if d.arrived_at or d.status in {"已送达", "已完成"}])
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "delivery_count": len(deliveries),
            "active_routes": len([d for d in deliveries if d.status == "运输中"]),
            "vehicle_count": len(vehicle_cards),
            "device_count": len(devices),
            "sensor_count": len([d for d in devices if d.device_type == "sensor"]),
            "gps_count": len([d for d in devices if d.device_type == "gps"]),
            "exception_count": len(exceptions),
            "capacity_weight_kg": round(capacity_weight, 3),
            "capacity_volume_m3": round(capacity_volume, 4),
            "arrival_rate": _pct(arrived, len(deliveries)),
        },
        "vehicles": vehicle_cards,
        "deliveries": delivery_cards,
        "devices": [
            {
                "id": int(d.id),
                "delivery_id": int(d.delivery_id),
                "device_type": d.device_type,
                "vendor": d.vendor,
                "device_code": d.device_code,
                "device_name": d.device_name,
                "channel_no": d.channel_no,
                "status": d.status,
                "latest_payload": (
                    latest_iot_by_device.get(str(d.device_code)).payload_json
                    if str(d.device_code) in latest_iot_by_device
                    else d.raw_payload_json
                ),
            }
            for d in devices[:80]
        ],
        "sensor": sensor_cards,
        "exceptions": exceptions[:30],
    }


@router.get("/neural/mining")
async def monitor_neural_mining(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    xfd_rows_result = await db.execute(
        text(
            """
            SELECT crawl_date, category1, category2, product_name, min_price, avg_price, max_price, unit, origin
            FROM xinfadi_price_crawl
            ORDER BY crawl_date DESC, product_name ASC
            LIMIT 3000
            """
        )
    )
    xfd_rows = xfd_rows_result.fetchall()
    if xfd_rows:
        latest_day = max(row.crawl_date for row in xfd_rows if row.crawl_date)
        latest = [row for row in xfd_rows if row.crawl_date == latest_day]
        category_rows: dict[str, dict[str, float]] = defaultdict(lambda: {"quote_count": 0, "avg_sum": 0.0})
        product_rows: dict[str, dict[str, Any]] = defaultdict(lambda: {"quote_count": 0, "avg_sum": 0.0, "min": 0.0, "max": 0.0, "category": ""})
        for row in latest:
            avg_price = _num(row.avg_price)
            min_price = _num(row.min_price)
            max_price = _num(row.max_price)
            category = row.category1 or "未分类"
            product = row.product_name or "未知品名"
            category_rows[category]["quote_count"] += 1
            category_rows[category]["avg_sum"] += avg_price
            prod = product_rows[product]
            prod["quote_count"] += 1
            prod["avg_sum"] += avg_price
            prod["min"] = min_price if not prod["min"] else min(prod["min"], min_price)
            prod["max"] = max(prod["max"], max_price)
            prod["category"] = category

        price_spreads = []
        for name, row in product_rows.items():
            avg_price = row["avg_sum"] / row["quote_count"] if row["quote_count"] else 0
            spread = max(0.0, row["max"] - row["min"])
            price_spreads.append(
                {
                    "product_id": None,
                    "product_name": name,
                    "category_name": row["category"] or "未分类",
                    "reference_price": round(avg_price, 2),
                    "min_quote": round(row["min"], 2),
                    "max_quote": round(row["max"], 2),
                    "avg_quote": round(avg_price, 2),
                    "spread": round(spread, 2),
                    "spread_rate": _pct(spread, avg_price),
                    "supplier_count": int(row["quote_count"]),
                }
            )
        price_spreads.sort(key=lambda item: item["spread_rate"], reverse=True)
        forecast_watchlist = [
            {
                "product_id": None,
                "product_name": row["product_name"],
                "category_name": row["category_name"],
                "current_price": row["avg_quote"],
                "next_price": round(row["avg_quote"] * (1 + min(0.08, row["spread_rate"] / 1000)), 2),
                "confidence": round(max(0.54, 0.9 - row["spread_rate"] / 200), 2),
                "risk": "high" if row["spread_rate"] >= 20 else "medium" if row["spread_rate"] >= 10 else "low",
                "reason": "新发地当日高低价价差较高" if row["spread_rate"] >= 10 else "行情稳定",
            }
            for row in price_spreads[:12]
        ]
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "source": "xinfadi_price_crawl",
            "latest_crawl_date": latest_day.isoformat() if latest_day else None,
            "summary": {
                "product_count": len(product_rows),
                "category_count": len(category_rows),
                "quote_count": len(latest),
                "return_orders": 0,
                "mapped_products": len(product_rows),
                "high_spread_products": len([r for r in price_spreads if r["spread_rate"] >= 20]),
            },
            "category_distribution": [
                {
                    "name": name,
                    "order_count": int(row["quote_count"]),
                    "amount": round(row["avg_sum"], 2),
                    "qty": int(row["quote_count"]),
                }
                for name, row in sorted(category_rows.items(), key=lambda item: item[1]["quote_count"], reverse=True)[:12]
            ],
            "top_goods": [
                {
                    "name": name,
                    "order_count": int(row["quote_count"]),
                    "amount": round(row["avg_sum"], 2),
                    "qty": int(row["quote_count"]),
                }
                for name, row in sorted(product_rows.items(), key=lambda item: item[1]["quote_count"], reverse=True)[:12]
            ],
            "top_customers": [],
            "regional_distribution": [],
            "price_spreads": price_spreads[:20],
            "supplier_quote_rank": [{"supplier_name": "新发地行情", "quote_count": len(latest), "avg_quote": round(sum(_num(r.avg_price) for r in latest) / len(latest), 2) if latest else 0}],
            "return_trend": [],
            "forecast_watchlist": forecast_watchlist,
        }

    orders = (await db.scalars(select(Order).order_by(Order.id.desc()).limit(3000))).all()
    products = (await db.scalars(select(Product).where(Product.is_deleted == False))).all()  # noqa: E712
    categories = (await db.scalars(select(Category).where(Category.is_deleted == False))).all()  # noqa: E712
    quotes = (await db.scalars(select(SupplierProductQuote).order_by(SupplierProductQuote.id.desc()).limit(3000))).all()
    returns = (await db.scalars(select(OrderReturn).order_by(OrderReturn.created_at.desc()).limit(1000))).all()
    canteens = (await db.scalars(select(ClientCanteen))).all()

    user_ids = {
        int(uid)
        for o in orders
        for uid in (o.client_id, o.delivery_id, o.supplier_id)
        if uid is not None
    }
    user_ids.update(int(q.supplier_id) for q in quotes if q.supplier_id)
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(u.id): u for u in users}
    canteen_map = {int(c.id): c for c in canteens}
    product_map = {int(p.id): p for p in products}
    category_map = {int(c.id): c.name for c in categories}

    category_rows: dict[str, dict[str, float]] = defaultdict(lambda: {"order_count": 0, "amount": 0.0, "qty": 0.0})
    goods_rows: dict[str, dict[str, float]] = defaultdict(lambda: {"order_count": 0, "amount": 0.0, "qty": 0.0})
    customer_rows: dict[str, dict[str, float]] = defaultdict(lambda: {"order_count": 0, "gmv": 0.0})
    district_rows: dict[str, dict[str, float]] = defaultdict(lambda: {"order_count": 0, "gmv": 0.0})

    for o in orders:
        customer = _canteen_name(canteen_map, o, user_map)
        customer_rows[customer]["order_count"] += 1
        customer_rows[customer]["gmv"] += _num(o.total_amount)
        district = _district_from_address(o.delivery_address)
        district_rows[district]["order_count"] += 1
        district_rows[district]["gmv"] += _num(o.total_amount)
        seen_goods: set[str] = set()
        seen_categories: set[str] = set()
        for line in _line_rows(o):
            product = product_map.get(int(line["product_id"] or 0))
            cat = line["category1_name"] or (
                category_map.get(int(product.category1_id)) if product else None
            ) or "未归类"
            category_rows[cat]["amount"] += _num(line["line_amount"])
            category_rows[cat]["qty"] += _num(line["qty"])
            goods_rows[line["goods_name"]]["amount"] += _num(line["line_amount"])
            goods_rows[line["goods_name"]]["qty"] += _num(line["qty"])
            seen_categories.add(cat)
            seen_goods.add(line["goods_name"])
        for cat in seen_categories:
            category_rows[cat]["order_count"] += 1
        for goods in seen_goods:
            goods_rows[goods]["order_count"] += 1

    quotes_by_product: dict[int, list[SupplierProductQuote]] = defaultdict(list)
    for q in quotes:
        quotes_by_product[int(q.product_id)].append(q)

    price_spreads = []
    for product_id, rows in quotes_by_product.items():
        product = product_map.get(product_id)
        prices = [_num(q.quote_price) for q in rows if _num(q.quote_price) > 0]
        if not product or not prices:
            continue
        low = min(prices)
        high = max(prices)
        avg = sum(prices) / len(prices)
        price_spreads.append(
            {
                "product_id": product_id,
                "product_name": product.name,
                "category_name": category_map.get(int(product.category1_id), "未归类"),
                "reference_price": _num(product.reference_price),
                "min_quote": round(low, 2),
                "max_quote": round(high, 2),
                "avg_quote": round(avg, 2),
                "spread": round(high - low, 2),
                "spread_rate": _pct(high - low, avg),
                "supplier_count": len(rows),
            }
        )
    price_spreads.sort(key=lambda row: row["spread_rate"], reverse=True)

    supplier_rows: dict[int, dict[str, float]] = defaultdict(lambda: {"quote_count": 0, "avg_sum": 0.0})
    for q in quotes:
        supplier_rows[int(q.supplier_id)]["quote_count"] += 1
        supplier_rows[int(q.supplier_id)]["avg_sum"] += _num(q.quote_price)
    supplier_quote_rank = [
        {
            "supplier_id": sid,
            "supplier_name": _user_name(user_map, sid, "供应商"),
            "quote_count": int(row["quote_count"]),
            "avg_quote": round(row["avg_sum"] / row["quote_count"], 2) if row["quote_count"] else 0.0,
        }
        for sid, row in sorted(supplier_rows.items(), key=lambda item: item[1]["quote_count"], reverse=True)[:12]
    ]

    return_by_day: dict[str, int] = defaultdict(int)
    for r in returns:
        return_by_day[r.created_at.date().isoformat()] += 1
    return_trend = [
        {"date": (datetime.utcnow().date() - timedelta(days=i)).isoformat(), "count": 0}
        for i in range(13, -1, -1)
    ]
    for row in return_trend:
        row["count"] = return_by_day.get(row["date"], 0)

    forecast_watchlist = []
    for row in price_spreads[:12]:
        drift = min(0.12, max(-0.08, row["spread_rate"] / 1000))
        baseline = row["avg_quote"] or row["reference_price"]
        forecast_watchlist.append(
            {
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "category_name": row["category_name"],
                "current_price": baseline,
                "next_price": round(baseline * (1 + drift), 2),
                "confidence": round(max(0.56, 0.86 - row["spread_rate"] / 200), 2),
                "risk": "high" if row["spread_rate"] >= 20 else "medium" if row["spread_rate"] >= 10 else "low",
                "reason": "供应商报价离散度较高" if row["spread_rate"] >= 10 else "报价稳定",
            }
        )

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "product_count": len(products),
            "category_count": len(categories),
            "quote_count": len(quotes),
            "return_orders": len(returns),
            "mapped_products": len([p for p in products if p.goods_sn or p.supplier_id]),
            "high_spread_products": len([r for r in price_spreads if r["spread_rate"] >= 20]),
        },
        "category_distribution": [
            {
                "name": name,
                "order_count": int(row["order_count"]),
                "amount": round(row["amount"], 2),
                "qty": round(row["qty"], 3),
            }
            for name, row in sorted(category_rows.items(), key=lambda item: item[1]["amount"], reverse=True)[:12]
        ],
        "top_goods": [
            {
                "name": name,
                "order_count": int(row["order_count"]),
                "amount": round(row["amount"], 2),
                "qty": round(row["qty"], 3),
            }
            for name, row in sorted(goods_rows.items(), key=lambda item: item[1]["amount"], reverse=True)[:12]
        ],
        "top_customers": [
            {
                "name": name,
                "order_count": int(row["order_count"]),
                "gmv": round(row["gmv"], 2),
            }
            for name, row in sorted(customer_rows.items(), key=lambda item: item[1]["gmv"], reverse=True)[:12]
        ],
        "regional_distribution": [
            {
                "name": name,
                "order_count": int(row["order_count"]),
                "gmv": round(row["gmv"], 2),
            }
            for name, row in sorted(district_rows.items(), key=lambda item: item[1]["gmv"], reverse=True)[:12]
        ],
        "price_spreads": price_spreads[:20],
        "supplier_quote_rank": supplier_quote_rank,
        "return_trend": return_trend,
        "forecast_watchlist": forecast_watchlist,
    }


@router.get("/orders")
async def monitor_orders(
    status: str = "",
    order_no: str = "",
    created_date_start: str = "",
    created_date_end: str = "",
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.utcnow().date()
    try:
        start_date = date.fromisoformat(created_date_start) if created_date_start else today
        end_date = date.fromisoformat(created_date_end) if created_date_end else today
    except ValueError:
        raise HTTPException(400, "时间筛选格式错误，需为 YYYY-MM-DD")
    if end_date < start_date:
        raise HTTPException(400, "结束日期不能早于开始日期")
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min)

    stmt = select(Order).order_by(Order.id.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    if order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))
    stmt = stmt.where(Order.created_at >= start_dt, Order.created_at < end_dt)
    return (await db.scalars(stmt)).all()


@router.get("/logistics")
async def monitor_logistics(
    _=Depends(require_role("monitor")), db: AsyncSession = Depends(get_db)
):
    deliveries = (await db.scalars(select(Delivery).order_by(Delivery.id.desc()))).all()
    return deliveries


@router.get("/alerts")
async def monitor_alerts(
    level: str = "",
    status: str = "",
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Alert).order_by(Alert.id.desc())
    if level:
        stmt = stmt.where(Alert.level == level)
    if status:
        stmt = stmt.where(Alert.status == status)
    return (await db.scalars(stmt)).all()


@router.put("/alerts/{alert_id}/close")
async def close_alert(
    alert_id: int,
    request: Request,
    user=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(Alert).where(Alert.id == alert_id))
    if not row:
        raise HTTPException(404, "预警不存在")
    ensure_alert_transition(row.status, "closed")
    old_status = row.status
    row.status = "closed"
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="alert_close",
        category="alert",
        object_type="alert",
        object_id=row.id,
        detail=f"{old_status}->closed",
        **_audit_meta(request),
    )
    await add_outbox_event(
        db=db,
        event_type="alert_close",
        payload={"id": row.id, "old_status": old_status, "new_status": "closed"},
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/audit-logs")
async def monitor_audit_logs(
    category: str = "",
    action: str = "",
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if category:
        stmt = stmt.where(AuditLog.category == category)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return (await db.scalars(stmt.limit(500))).all()


@router.get("/reports")
async def monitor_reports(
    period: str = "day",
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    orders = (await db.scalars(select(Order))).all()
    return {
        "period": period,
        "gmv_total": float(sum(float(o.total_amount) for o in orders)),
        "orders_count": len(orders),
        "delivery_performance": [
            {"name": "delivery001", "score": 95},
            {"name": "delivery002", "score": 88},
            {"name": "delivery003", "score": 82},
        ],
    }


@router.get("/route-planning-showcase")
async def monitor_route_planning_showcase(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    orders = (await db.scalars(select(Order).order_by(Order.id.desc()).limit(200))).all()
    deliveries = (await db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(200))).all()
    delivery_users = (
        await db.execute(
            select(User.id, User.company_name, User.username).where(User.role == "delivery")
        )
    ).all()
    delivery_name_map = {
        int(uid): (company_name or username or f"配送商#{uid}")
        for uid, company_name, username in delivery_users
    }
    logistics_orders = [o for o in orders if str(o.status) in {"配货", "发货", "收货"}]
    total_weight = float(sum(float(o.total_weight_kg or 0) for o in logistics_orders))
    total_volume = float(sum(float(o.total_volume_m3 or 0) for o in logistics_orders))
    optimized_distance = round(max(12.0, len(logistics_orders) * 6.3), 2)
    baseline_distance = round(optimized_distance * 1.2, 2)
    optimized_minutes = max(35, len(logistics_orders) * 16)
    baseline_minutes = int(round(optimized_minutes * 1.18))
    open_alerts = int(
        await db.scalar(select(func.count(Alert.id)).where(Alert.status == "open")) or 0
    )
    active_deliveries = [d for d in deliveries if str(d.status) == "运输中"]
    route_cards = []
    for idx, d in enumerate(active_deliveries[:8], 1):
        route_cards.append(
            {
                "delivery_id": int(d.id),
                "order_id": int(d.order_id),
                "route_no": f"RT-{datetime.utcnow().strftime('%m%d')}-{idx:02d}",
                "status": d.status,
                "vehicle_no": d.vehicle_no or "待分配车辆",
                "delivery_name": delivery_name_map.get(int(d.delivery_id), f"配送商#{d.delivery_id}"),
                "distance_km": round(float(d.distance_km or 0), 2),
                "estimated_arrival": (
                    (d.departed_at + timedelta(minutes=65)).isoformat()
                    if d.departed_at
                    else None
                ),
            }
        )
    capability_cards = [
        {
            "title": "北斗定位融合",
            "desc": "车辆实时位置优先取北斗设备，支持在途轨迹监控与里程核算。",
        },
        {
            "title": "高德驾车路径与ETA",
            "desc": "配送规划已接入高德驾车路径，按路段距离与时长估算到达时刻。",
        },
        {
            "title": "载重容积双约束",
            "desc": "规划同时校验车辆载重与容积，避免超载超容积发车。",
        },
        {
            "title": "时窗与顺路策略",
            "desc": "优先保障时间窗，再结合顺路策略减少总里程与空驶。",
        },
        {
            "title": "电子围栏闭环",
            "desc": "规划支持围栏事件扩展，可落地到到仓/离仓/越界告警。",
        },
    ]
    return {
        "summary": {
            "active_routes": len(active_deliveries),
            "planned_orders": len(logistics_orders),
            "optimized_distance_km": optimized_distance,
            "baseline_distance_km": baseline_distance,
            "distance_saved_km": round(max(0.0, baseline_distance - optimized_distance), 2),
            "optimized_duration_minutes": optimized_minutes,
            "baseline_duration_minutes": baseline_minutes,
            "duration_saved_minutes": max(0, baseline_minutes - optimized_minutes),
            "open_alerts": open_alerts,
            "total_weight_kg": round(total_weight, 2),
            "total_volume_m3": round(total_volume, 3),
            "estimated_on_time_rate": round(max(0.82, min(0.97, 0.86 + len(active_deliveries) * 0.01)), 4),
            "estimated_on_time_rate_note": ESTIMATED_ON_TIME_RATE_NOTE_CN,
        },
        "route_cards": route_cards,
        "capability_cards": capability_cards,
        "roadmap": [
            {"stage": "当前演示能力", "value": "可解释路径 + 约束命中 + 价值对比"},
            {"stage": "近期增强", "value": "订单级时窗与坐标落库 + 围栏事件"},
            {"stage": "生产闭环", "value": "实时ETA偏差分析 + 自动重规划"},
        ],
    }
