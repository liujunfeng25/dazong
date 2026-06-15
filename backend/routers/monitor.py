from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, SessionLocal
from dependencies import require_role
from models import (
    Alert,
    AuditLog,
    Bill,
    BillingStatement,
    Category,
    ClientCanteen,
    Delivery,
    DeliveryDevice,
    DeliveryDispatchItem,
    DeliveryDispatchStop,
    DeliveryDispatchTrip,
    DeliverySortScanRecord,
    DeliveryVehicle,
    DeliveryVehicleDeviceBinding,
    IoTData,
    MonitorBroadcast,
    Notification,
    Order,
    OrderItemAllocation,
    OrderItemStatusLog,
    OrderReceivingLine,
    OrderReturn,
    OrderStatusLog,
    Product,
    QualityReport,
    SupplierProductQuote,
    Ticket,
    User,
)
from services.alert_state_machine import ensure_alert_transition
from services.audit_service import write_audit_log
from schemas.camera_ptz import CameraPtzIn
from routers.delivery_dispatch import _load_trip_payload
from services.fleet_monitor import (
    build_beidou_history_track_payload,
    build_camera_live_url_payload,
    build_fleet_monitor_vehicles,
    build_fleet_monitor_warehouses,
    control_ys7_camera_ptz,
    load_camera_device_or_404,
    load_vehicle_beidou_device_or_404,
)
from services.order_quality_missing import period_quality_coverage
from services.outbox_service import add_outbox_event
from services.planning_display_notes import ESTIMATED_ON_TIME_RATE_NOTE_CN
from services.ticket_service import complaint_phase
from services.ws_manager import ws_manager

import time as _time
import asyncio as _asyncio
_AUDIT_CHAIN_CACHE: dict = {"ts": 0.0, "data": None}
_AUDIT_CHAIN_TTL = 300  # seconds —— 监管首页态势数据分钟级新鲜度足够
_AUDIT_CHAIN_LOCK = _asyncio.Lock()
# 高频追加表（audit/status 流水）单接口最多取的行数，避免数据膨胀时拖死首页
_AUDIT_CHAIN_LOG_LIMIT = 20000

router = APIRouter(prefix="/monitor", tags=["monitor"])

BUSINESS_BROADCAST_ROLES = ("client", "delivery", "supplier", "factory", "operation")
ROLE_LABELS = {
    "client": "采购端",
    "delivery": "配送端",
    "supplier": "供应端",
    "factory": "加工端",
    "operation": "运营端",
    "monitor": "监管端",
}
PRIORITY_LABELS = {"normal": "常规", "important": "重要", "urgent": "紧急"}
COMPLAINT_PHASE_LABELS = {
    "delivery_handling": "待配送反馈",
    "operation_review": "待运营结案",
    "closed": "已关闭",
}
FLOW_ACTION_LABELS = {
    "created": "客户提交投诉",
    "auto_dispatch": "系统派发配送商",
    "delivery_response": "配送商反馈",
    "operation_resolution": "运营结案",
}
FLOW_ROLE_LABELS = {
    "client": "采购方",
    "delivery": "配送商",
    "operation": "运营",
    "system": "系统",
}
ALERT_TYPE_LABELS = {
    "delivery_overdue": "配送超时",
    "quality_missing": "质检缺失",
    "sensor": "传感器异常",
    "shortage": "短收异常",
    "bill_discrepancy": "账单差异",
}
ALERT_TRIGGER_LABELS = {
    "supplier_ship": "供应商发货确认",
    "order_status": "订单状态变更",
}
ALERT_LEVEL_LABELS = {"high": "高危", "medium": "中危", "low": "低危"}
ALERT_STATUS_LABELS = {"open": "待处理", "closed": "已关闭"}
# 预警 payload 字段 → 中文标签；未列出的纯技术键不展示
ALERT_FACT_LABELS = {
    "order_no": "订单号",
    "status": "订单状态",
    "new_status": "新订单状态",
    "scan_count": "在途扫描次数",
    "first_seen_at": "首次发现",
    "last_seen_at": "最近发现",
    "expected_delivery_date": "约定送达日期",
    "expected_delivery_slot": "约定送达时段",
    "missing_count": "缺质检分单数",
    "trigger": "触发来源",
}
ALERT_FACT_HIDDEN_KEYS = {"order_id", "missing_allocation_ids"}


def _alert_type_label(t: Optional[str]) -> str:
    return ALERT_TYPE_LABELS.get(t or "", t or "")


def _clean_alert_text(s: Optional[str]) -> str:
    """把存储描述里的 `触发：<英文枚举>` 替换成中文标签，避免向领导暴露编程字段。"""
    text = str(s or "")
    for code, label in ALERT_TRIGGER_LABELS.items():
        text = text.replace(f"触发：{code}", f"触发：{label}")
    return text


def _alert_facts(payload: Any) -> list[dict[str, Any]]:
    """从预警 payload 生成中文事实磁贴，隐藏纯技术字段、跳过空值。"""
    data = payload if isinstance(payload, dict) else {}
    facts: list[dict[str, Any]] = []
    for key, label in ALERT_FACT_LABELS.items():
        if key in ALERT_FACT_HIDDEN_KEYS:
            continue
        value = data.get(key)
        if value is None or value == "":
            continue
        if key == "trigger":
            value = ALERT_TRIGGER_LABELS.get(value, value)
        elif key in ("first_seen_at", "last_seen_at"):
            value = _fmt_cn_time(value)
        facts.append({"label": label, "value": value})
    return facts


def _fmt_cn_time(value: Any) -> str:
    """ISO 字符串 → 北京时间可读串；解析失败原样返回。"""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return str(value)


class MonitorBroadcastIn(BaseModel):
    title: str = Field(default="", max_length=160)
    content: str = Field(..., min_length=1, max_length=2000)
    priority: str = Field(default="normal", max_length=24)
    target_type: str = Field(default="all", max_length=24)
    roles: list[str] = Field(default_factory=list)
    user_ids: list[int] = Field(default_factory=list)


def _role_label(role: str) -> str:
    return ROLE_LABELS.get(role or "", role or "未知端")


def _broadcast_priority(priority: str) -> str:
    return priority if priority in PRIORITY_LABELS else "normal"


def _broadcast_target_summary(target_type: str, roles: list[str], recipients: list[User]) -> str:
    if target_type == "all":
        return "业务全域"
    if target_type == "roles":
        labels = [_role_label(role) for role in roles if role in BUSINESS_BROADCAST_ROLES]
        return "、".join(labels) or "指定端"
    names = []
    for user in recipients[:4]:
        names.append(user.company_name or user.username)
    extra = len(recipients) - len(names)
    if extra > 0:
        names.append(f"等 {extra} 人")
    return "、".join(names) or "指定用户"


def _broadcast_route_for_role(role: str) -> str:
    return f"/{role}/notifications"


def _mask_phone(phone: Optional[str]) -> str:
    text_value = str(phone or "").strip()
    if len(text_value) < 7:
        return text_value
    return f"{text_value[:3]}****{text_value[-4:]}"


def _safe_location(address: Optional[str]) -> str:
    text_value = str(address or "").strip()
    return _district_from_address(text_value) if text_value else ""


def _notification_stats(notifications: list[Notification]) -> dict[str, Any]:
    total = len(notifications)
    read_count = len([row for row in notifications if row.is_read])
    unread_count = max(0, total - read_count)
    return {
        "total": total,
        "read_count": read_count,
        "unread_count": unread_count,
        "read_rate": round(read_count / total * 100, 1) if total else 0,
    }


async def _broadcast_rows(db: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    broadcasts = (
        await db.scalars(select(MonitorBroadcast).order_by(MonitorBroadcast.id.desc()).limit(limit))
    ).all()
    if not broadcasts:
        return []
    broadcast_ids = [int(row.id) for row in broadcasts]
    notifications = (
        await db.scalars(
            select(Notification).where(
                Notification.object_type == "monitor_broadcast",
                Notification.object_id.in_(broadcast_ids),
            )
        )
    ).all()
    grouped: dict[int, list[Notification]] = defaultdict(list)
    for row in notifications:
        grouped[int(row.object_id)].append(row)
    sender_ids = [int(row.sender_user_id) for row in broadcasts if row.sender_user_id]
    senders = (await db.scalars(select(User).where(User.id.in_(sender_ids)))).all() if sender_ids else []
    sender_map = {int(user.id): user for user in senders}
    rows = []
    for row in broadcasts:
        stats = _notification_stats(grouped.get(int(row.id), []))
        sender = sender_map.get(int(row.sender_user_id))
        rows.append(
            {
                "id": int(row.id),
                "title": row.title,
                "content": row.content,
                "priority": row.priority,
                "priority_label": PRIORITY_LABELS.get(row.priority, "常规"),
                "target_type": row.target_type,
                "target_summary": row.target_summary,
                "sender": sender.company_name if sender and sender.company_name else (sender.username if sender else "监管员"),
                "recipient_count": int(row.recipient_count or stats["total"]),
                "sent_at": _iso(row.sent_at),
                **stats,
            }
        )
    return rows


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


def _executive_period_days(days: int) -> int:
    return 30 if int(days or 7) >= 30 else 7


_CN_TZ = ZoneInfo("Asia/Shanghai")
_UTC = timezone.utc


def _china_today_window() -> tuple[date, datetime, datetime, datetime]:
    """北京时间「今日」日历日及其对应 UTC naive 查询区间（库内 timestamp 为 UTC naive）。"""
    now_cn = datetime.now(_CN_TZ)
    today = now_cn.date()
    start_cn = datetime.combine(today, time.min, tzinfo=_CN_TZ)
    end_cn = start_cn + timedelta(days=1)
    start_utc = start_cn.astimezone(_UTC).replace(tzinfo=None)
    end_utc = end_cn.astimezone(_UTC).replace(tzinfo=None)
    return today, now_cn, start_utc, end_utc


def _china_date(dt: Optional[datetime]) -> Optional[date]:
    if not dt:
        return None
    aware = dt.replace(tzinfo=_UTC) if dt.tzinfo is None else dt.astimezone(_UTC)
    return aware.astimezone(_CN_TZ).date()


def _executive_conclusion(
    *,
    pending_risks: int,
    high_risks: int,
    fulfillment_rate: float,
    top_risk_label: str = "",
    period_days: int = 7,
) -> dict[str, str]:
    if high_risks > 0 or fulfillment_rate < 80:
        status, tone = "重点关注", "risk"
    elif pending_risks > 0 or fulfillment_rate < 95:
        status, tone = "总体可控", "watch"
    else:
        status, tone = "运行稳定", "stable"
    if pending_risks <= 0:
        text = f"{status}，当前未发现待处置风险，近 {period_days} 日送达率 {fulfillment_rate:.1f}%"
    else:
        focus = f"，主要集中于{top_risk_label}" if top_risk_label else ""
        text = f"{status}，{pending_risks} 项风险待处置{focus}，近 {period_days} 日送达率 {fulfillment_rate:.1f}%"
    return {"status": status, "tone": tone, "text": text}


def _severity_weight(level: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(level or "", 0)


def _canteen_ranking_rows(
    stats: dict[Optional[int], dict[str, Any]],
    canteen_map: dict[int, ClientCanteen],
) -> list[dict[str, Any]]:
    rows = []
    for canteen_id, values in stats.items():
        canteen = canteen_map.get(canteen_id) if canteen_id else None
        orders = int(values["orders"])
        rows.append(
            {
                "canteen_id": canteen_id,
                "name": canteen.name if canteen else "未指定食堂",
                "address": canteen.address if canteen else "",
                "orders": orders,
                "gmv": round(values["gmv"], 2),
                "fulfillment_rate": _pct(values["delivered"], orders),
                "abnormal_rate": _pct(values["abnormal"], orders),
                "risks": int(values["abnormal"]),
            }
        )
    return sorted(rows, key=lambda row: (row["gmv"], row["orders"]), reverse=True)


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


@router.get("/neural/executive-overview")
async def monitor_executive_overview(
    days: int = Query(default=7, ge=7, le=30),
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    days = _executive_period_days(days)
    today, now_cn, today_start_utc, today_end_utc = _china_today_window()
    period_start = today_start_utc - timedelta(days=days - 1)

    orders = list((await db.scalars(
        select(Order).where(Order.created_at >= period_start).order_by(Order.id.desc())
    )).all())
    order_ids = [int(row.id) for row in orders]
    allocations = list((await db.scalars(
        select(OrderItemAllocation)
        .where(OrderItemAllocation.created_at >= period_start)
        .order_by(OrderItemAllocation.id.desc())
    )).all())
    deliveries = list((await db.scalars(
        select(Delivery).where(Delivery.order_id.in_(order_ids))
    )).all()) if order_ids else []
    alerts = list((await db.scalars(
        select(Alert).where(Alert.created_at >= period_start).order_by(Alert.id.desc())
    )).all())
    tickets = list((await db.scalars(
        select(Ticket).where(Ticket.created_at >= period_start).order_by(Ticket.id.desc())
    )).all())
    quality_reports = list((await db.scalars(
        select(QualityReport).where(QualityReport.created_at >= period_start)
    )).all())
    bills = list((await db.scalars(
        select(Bill).where(Bill.created_at >= period_start)
    )).all())
    audits = list((await db.scalars(
        select(AuditLog).where(
            AuditLog.created_at >= period_start,
            AuditLog.object_type == "order",
        )
    )).all())
    status_logs = list((await db.scalars(
        select(OrderStatusLog).where(OrderStatusLog.created_at >= period_start)
    )).all())
    canteens = list((await db.scalars(select(ClientCanteen))).all())
    canteen_map = {int(row.id): row for row in canteens}

    period_orders = [row for row in orders if row.created_at and row.created_at >= period_start]
    today_orders = [
        row for row in orders
        if row.created_at and today_start_utc <= row.created_at < today_end_utc
    ]
    eligible_orders = [row for row in period_orders if row.status != "取消"]
    delivered_orders = [row for row in eligible_orders if row.status in {"收货", "收货确认", "已结算"}]
    fulfillment_rate = _pct(len(delivered_orders), len(eligible_orders))

    audited_order_ids = {
        int(row.object_id) for row in audits if int(row.object_id or 0) in set(order_ids)
    }
    audited_order_ids.update(
        int(row.order_id) for row in status_logs if int(row.order_id or 0) in set(order_ids)
    )
    audit_coverage_rate = _pct(
        len({int(row.id) for row in period_orders} & audited_order_ids),
        len(period_orders),
    )

    open_alerts = [row for row in alerts if row.status == "open"]
    pending_tickets = [row for row in tickets if row.status != "已关闭"]
    # 批次质检为存证模型（上传即覆盖、无审核）：质检维度的待办 = 「已出库但缺报告」的分单行，
    # 不再把「未审核批次报告」当待办。pending_quality 现承载缺报告分单（含 created_at/supplier_id）。
    quality_coverage = await period_quality_coverage(
        db, allocations, quality_reports, orders, shipped_only=True
    )
    pending_quality = quality_coverage["missing_allocations"]
    pending_bills = [row for row in bills if row.status != "已结算"]
    pending_risk_count = (
        len(open_alerts) + len(pending_tickets) + len(pending_quality) + len(pending_bills)
    )
    unsettled_amount = round(sum(_num(row.amount) for row in pending_bills), 2)

    risk_groups: dict[str, dict[str, Any]] = {}

    def add_risk(key: str, label: str, count: int, level: str, created_values: list[datetime], module: str, detail: str):
        if count <= 0:
            return
        oldest = min((value for value in created_values if value), default=None)
        age_hours = max(0, int((datetime.utcnow() - oldest).total_seconds() // 3600)) if oldest else 0
        risk_groups[key] = {
            "key": key,
            "label": label,
            "count": count,
            "level": level,
            "level_label": {"high": "高风险", "medium": "需关注", "low": "提示"}.get(level, "需关注"),
            "affected": detail,
            "duration_hours": age_hours,
            "module": module,
        }

    high_alerts = [row for row in open_alerts if row.level == "high"]
    add_risk(
        "alerts", "开放预警", len(open_alerts), "high" if high_alerts else "medium",
        [row.created_at for row in open_alerts], "alerts", "规则引擎识别的未闭环异常",
    )
    add_risk(
        "tickets", "待办工单", len(pending_tickets), "medium",
        [row.created_at for row in pending_tickets], "alerts", "配送、售后及账务处置事项",
    )
    add_risk(
        "quality", "质检缺报告", len(pending_quality), "medium",
        [row.created_at for row in pending_quality], "audit", "已出库但尚未补传质检报告的分单",
    )
    add_risk(
        "settlement", "账务未结", len(pending_bills), "low",
        [row.created_at for row in pending_bills], "audit", f"涉及金额 ¥{unsettled_amount:,.2f}",
    )
    top_risks = sorted(
        risk_groups.values(),
        key=lambda row: ({"high": 3, "medium": 2, "low": 1}[row["level"]], row["count"]),
        reverse=True,
    )[:3]
    conclusion = _executive_conclusion(
        pending_risks=pending_risk_count,
        high_risks=len(high_alerts),
        fulfillment_rate=fulfillment_rate,
        top_risk_label=top_risks[0]["label"] if top_risks else "",
        period_days=days,
    )

    allocation_order_ids = {int(row.order_id) for row in allocations}
    shipped_order_ids = {int(row.order_id) for row in allocations if row.status == "已出库"}
    transit_order_ids = {
        int(row.order_id) for row in deliveries
        if row.status in {"运输中", "已到达"} or row.departed_at is not None
    }
    received_order_ids = {
        int(row.id) for row in period_orders if row.status in {"收货", "收货确认", "已结算"}
    }
    quality_order_ids = {int(row.order_id) for row in quality_reports}
    settled_order_ids = {int(row.order_id) for row in bills if row.status == "已结算"}
    stage_defs = [
        ("order", "下单", {int(row.id) for row in period_orders}, 0),
        ("allocation", "分单", allocation_order_ids, len([row for row in allocations if row.status == "待确认"])),
        ("outbound", "出库", shipped_order_ids, len(pending_quality)),
        ("transit", "运输", transit_order_ids, len([row for row in pending_tickets if row.type == "配送异常"])),
        ("receiving", "签收", received_order_ids, len([row for row in period_orders if row.has_abnormal])),
        ("quality", "质检", quality_order_ids, len(pending_quality)),
        ("settlement", "结算", settled_order_ids, len(pending_bills)),
    ]
    period_order_ids = {int(row.id) for row in period_orders}
    lifecycle = [
        {
            "key": key,
            "name": name,
            "count": len(ids & period_order_ids),
            "conversion_rate": _pct(len(ids & period_order_ids), len(period_orders)),
            "risk_count": risk_count,
        }
        for key, name, ids, risk_count in stage_defs
    ]

    alert_by_day = Counter(_china_date(row.created_at) for row in alerts if row.status == "open")
    trends = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        day_orders = [row for row in orders if _china_date(row.created_at) == day]
        day_eligible = [row for row in day_orders if row.status != "取消"]
        day_delivered = [row for row in day_eligible if row.status in {"收货", "收货确认", "已结算"}]
        trends.append({
            "date": day.isoformat(),
            "orders": len(day_orders),
            "gmv": round(sum(_num(row.total_amount) for row in day_orders), 2),
            "fulfillment_rate": _pct(len(day_delivered), len(day_eligible)),
            "risks": int(alert_by_day.get(day, 0)),
        })

    region_rows: dict[str, dict[str, Any]] = defaultdict(lambda: {"orders": 0, "gmv": 0.0, "risks": 0})
    for row in orders:
        canteen = canteen_map.get(int(row.canteen_id)) if row.canteen_id else None
        district = _district_from_address(row.delivery_address or (canteen.address if canteen else ""))
        region_rows[district]["orders"] += 1
        region_rows[district]["gmv"] += _num(row.total_amount)
        region_rows[district]["risks"] += int(bool(row.has_abnormal))
    regions = [
        {"name": name, **values, "gmv": round(values["gmv"], 2)}
        for name, values in sorted(
            region_rows.items(),
            key=lambda item: (item[1]["risks"], item[1]["orders"]),
            reverse=True,
        )[:6]
    ]

    supplier_ids = sorted({int(row.supplier_id) for row in allocations})
    supplier_users = list((await db.scalars(
        select(User).where(User.id.in_(supplier_ids))
    )).all()) if supplier_ids else []
    supplier_name_map = {
        int(row.id): row.company_name or row.username or f"供货商#{row.id}"
        for row in supplier_users
    }
    order_map = {int(row.id): row for row in orders}
    supplier_stats: dict[int, dict[str, int]] = defaultdict(lambda: {"allocations": 0, "risks": 0, "pending_quality": 0})
    quality_supplier_pending = Counter(int(row.supplier_id) for row in pending_quality)
    for row in allocations:
        sid = int(row.supplier_id)
        supplier_stats[sid]["allocations"] += 1
        supplier_stats[sid]["risks"] += int(bool(order_map.get(int(row.order_id)) and order_map[int(row.order_id)].has_abnormal))
    for sid, count in quality_supplier_pending.items():
        supplier_stats[sid]["pending_quality"] = count
        supplier_stats[sid]["risks"] += count
    supplier_risks = [
        {
            "supplier_id": sid,
            "name": supplier_name_map.get(sid, f"供货商#{sid}"),
            **stats,
        }
        for sid, stats in sorted(
            supplier_stats.items(),
            key=lambda item: (item[1]["risks"], item[1]["allocations"]),
            reverse=True,
        )[:6]
    ]

    subject_user_ids = {
        int(uid)
        for row in period_orders
        for uid in (row.delivery_id, row.client_id)
        if uid
    }
    subject_user_ids.update(int(row.supplier_id) for row in allocations if row.supplier_id)
    subject_users = list((await db.scalars(
        select(User).where(User.id.in_(subject_user_ids))
    )).all()) if subject_user_ids else []
    subject_name_map = {
        int(row.id): row.company_name or row.username or f"主体#{row.id}"
        for row in subject_users
    }

    delivery_stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"orders": 0, "gmv": 0.0, "delivered": 0, "abnormal": 0}
    )
    client_stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"orders": 0, "gmv": 0.0, "delivered": 0, "abnormal": 0}
    )
    canteen_stats: dict[int, dict[Optional[int], dict[str, Any]]] = defaultdict(
        lambda: defaultdict(
            lambda: {"orders": 0, "gmv": 0.0, "delivered": 0, "abnormal": 0}
        )
    )
    matrix_stats: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {"orders": 0, "gmv": 0.0, "risks": 0}
    )
    delivered_statuses = {"收货", "收货确认", "已结算"}
    for row in period_orders:
        did = int(row.delivery_id)
        cid = int(row.client_id)
        delivered = int(row.status in delivered_statuses)
        abnormal = int(bool(row.has_abnormal))
        for stats, key in ((delivery_stats, did), (client_stats, cid)):
            stats[key]["orders"] += 1
            stats[key]["gmv"] += _num(row.total_amount)
            stats[key]["delivered"] += delivered
            stats[key]["abnormal"] += abnormal
        canteen = canteen_map.get(int(row.canteen_id)) if row.canteen_id else None
        canteen_id = int(canteen.id) if canteen and int(canteen.school_client_id) == cid else None
        canteen_stats[cid][canteen_id]["orders"] += 1
        canteen_stats[cid][canteen_id]["gmv"] += _num(row.total_amount)
        canteen_stats[cid][canteen_id]["delivered"] += delivered
        canteen_stats[cid][canteen_id]["abnormal"] += abnormal
        matrix_stats[(did, cid)]["orders"] += 1
        matrix_stats[(did, cid)]["gmv"] += _num(row.total_amount)
        matrix_stats[(did, cid)]["risks"] += abnormal

    def subject_ranking(
        stats: dict[int, dict[str, Any]],
        *,
        include_canteens: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": uid,
                "name": subject_name_map.get(uid, f"主体#{uid}"),
                "orders": values["orders"],
                "gmv": round(values["gmv"], 2),
                "fulfillment_rate": _pct(values["delivered"], values["orders"]),
                "abnormal_rate": _pct(values["abnormal"], values["orders"]),
                "risks": values["abnormal"],
                **(
                    {"canteens": _canteen_ranking_rows(canteen_stats[uid], canteen_map)}
                    if include_canteens else {}
                ),
            }
            for uid, values in sorted(
                stats.items(),
                key=lambda item: (item[1]["gmv"], item[1]["orders"]),
                reverse=True,
            )[:8]
        ]

    delivery_rankings = subject_ranking(delivery_stats)
    client_rankings = subject_ranking(client_stats, include_canteens=True)

    allocation_product_ids = sorted({int(row.product_id) for row in allocations})
    products = list((await db.scalars(
        select(Product).where(Product.id.in_(allocation_product_ids))
    )).all()) if allocation_product_ids else []
    category_ids = sorted({int(row.category1_id) for row in products if row.category1_id})
    categories = list((await db.scalars(
        select(Category).where(Category.id.in_(category_ids))
    )).all()) if category_ids else []
    product_map = {int(row.id): row for row in products}
    category_name_map = {int(row.id): row.name for row in categories}

    category_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"gmv": 0.0, "quantity": 0.0, "lines": 0}
    )
    supplier_performance_stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"gmv": 0.0, "allocations": 0, "order_ids": set(), "delivered_ids": set(), "risks": 0}
    )
    for row in allocations:
        amount = _num(row.quantity) * _num(row.unit_price)
        product = product_map.get(int(row.product_id))
        category_name = (
            category_name_map.get(int(product.category1_id))
            if product and product.category1_id else None
        ) or "未归类"
        category_stats[category_name]["gmv"] += amount
        category_stats[category_name]["quantity"] += _num(row.quantity)
        category_stats[category_name]["lines"] += 1

        sid = int(row.supplier_id)
        order = order_map.get(int(row.order_id))
        supplier_performance_stats[sid]["gmv"] += amount
        supplier_performance_stats[sid]["allocations"] += 1
        supplier_performance_stats[sid]["order_ids"].add(int(row.order_id))
        if order and order.status in delivered_statuses:
            supplier_performance_stats[sid]["delivered_ids"].add(int(row.order_id))
        if order and order.has_abnormal:
            supplier_performance_stats[sid]["risks"] += 1

    category_total = sum(row["gmv"] for row in category_stats.values())
    category_mix = [
        {
            "name": name,
            "gmv": round(values["gmv"], 2),
            "quantity": round(values["quantity"], 3),
            "lines": values["lines"],
            "share": _pct(values["gmv"], category_total),
        }
        for name, values in sorted(
            category_stats.items(), key=lambda item: item[1]["gmv"], reverse=True
        )[:8]
    ]

    supplier_performance = []
    for sid, values in supplier_performance_stats.items():
        pending_count = int(quality_supplier_pending.get(sid, 0))
        supplier_performance.append({
            "supplier_id": sid,
            "name": subject_name_map.get(sid, supplier_name_map.get(sid, f"供货商#{sid}")),
            "gmv": round(values["gmv"], 2),
            "allocations": values["allocations"],
            "orders": len(values["order_ids"]),
            "fulfillment_rate": _pct(len(values["delivered_ids"]), len(values["order_ids"])),
            "risks": values["risks"] + pending_count,
            "pending_quality": pending_count,
        })
    supplier_performance.sort(
        key=lambda row: (row["gmv"], row["allocations"]), reverse=True
    )
    supplier_performance = supplier_performance[:8]

    matrix_delivery_ids = [row["id"] for row in delivery_rankings[:6]]
    matrix_client_ids = [row["id"] for row in client_rankings[:8]]
    delivery_client_matrix = {
        "deliveries": [
            {"id": uid, "name": subject_name_map.get(uid, f"配送商#{uid}")}
            for uid in matrix_delivery_ids
        ],
        "clients": [
            {"id": uid, "name": subject_name_map.get(uid, f"客户#{uid}")}
            for uid in matrix_client_ids
        ],
        "cells": [
            {
                "delivery_id": did,
                "client_id": cid,
                "orders": int(matrix_stats[(did, cid)]["orders"]),
                "gmv": round(matrix_stats[(did, cid)]["gmv"], 2),
                "risks": int(matrix_stats[(did, cid)]["risks"]),
            }
            for did in matrix_delivery_ids
            for cid in matrix_client_ids
        ],
    }

    return {
        "generated_at": now_cn.isoformat(),
        "period": {"today": today.isoformat(), "trend_days": days, "health_days": days},
        "conclusion": conclusion,
        "summary": {
            "today_orders": len(today_orders),
            "today_gmv": round(sum(_num(row.total_amount) for row in today_orders), 2),
            "fulfillment_rate": fulfillment_rate,
            "audit_coverage_rate": audit_coverage_rate,
            "pending_risks": pending_risk_count,
            "unsettled_amount": unsettled_amount,
        },
        "lifecycle": lifecycle,
        "trends": trends,
        "top_risks": top_risks,
        "regions": regions,
        "supplier_risks": supplier_risks,
        "delivery_rankings": delivery_rankings,
        "supplier_performance": supplier_performance,
        "category_mix": category_mix,
        "client_rankings": client_rankings,
        "delivery_client_matrix": delivery_client_matrix,
        "quality": {
            # 批次质检存证模型：指标改为「质检覆盖率」= 已出库分单中已被质检覆盖（批次报告存在
            # 或周期报告有效）的占比。total=报告总数（留痕量），shipped/covered/missing 为分单口径。
            "total": len(quality_reports),
            "shipped": quality_coverage["shipped"],
            "covered": quality_coverage["covered"],
            "missing": quality_coverage["missing"],
            "coverage_rate": quality_coverage["coverage_rate"],
            # 兼容前端过渡期旧字段：pending=缺报告行，approval_rate 映射到覆盖率
            "pending": quality_coverage["missing"],
            "approval_rate": quality_coverage["coverage_rate"],
        },
        "settlement": {
            "total": len(bills),
            "settled": len([row for row in bills if row.status == "已结算"]),
            "pending": len(pending_bills),
            "unsettled_amount": unsettled_amount,
            "settlement_rate": _pct(
                len([row for row in bills if row.status == "已结算"]),
                len(bills),
            ),
        },
    }


@router.get("/neural/overview")
async def monitor_neural_overview(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.utcnow().date()
    orders = (await db.scalars(select(Order).order_by(Order.id.desc()).limit(800))).all()
    alerts = (await db.scalars(select(Alert).order_by(Alert.id.desc()).limit(80))).all()
    deliveries = (await db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(500))).all()
    returns = (await db.scalars(select(OrderReturn).order_by(OrderReturn.id.desc()).limit(500))).all()
    tickets = (await db.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(500))).all()
    quality_reports = (
        await db.scalars(select(QualityReport).order_by(QualityReport.id.desc()).limit(500))
    ).all()
    allocations = (
        await db.scalars(
            select(OrderItemAllocation).order_by(OrderItemAllocation.id.desc()).limit(1500)
        )
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
    # 批次质检存证模型：质检待办 = 已出库但缺报告的分单行（非「未审核报告」）
    pending_quality = (
        await period_quality_coverage(db, allocations, quality_reports, orders, shipped_only=True)
    )["missing_allocations"]
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
            "description": "已出库缺质检报告与售后/配送异常工单",
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


def _audit_day(dt: Optional[datetime]) -> Optional[date]:
    return dt.date() if dt else None


def _audit_status(risk_count: int, watch_count: int = 0) -> tuple[str, str]:
    if risk_count > 0:
        return "risk", "存在风险"
    if watch_count > 0:
        return "watch", "持续关注"
    return "stable", "运行稳定"


def _audit_time_label(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return dt.strftime("%H:%M:%S")


def _audit_actor(user_map: dict[int, User], user_id: Optional[int], fallback: str = "系统") -> str:
    if not user_id:
        return fallback
    user = user_map.get(int(user_id))
    if not user:
        return f"账号#{user_id}"
    return user.company_name or user.username or f"账号#{user_id}"


def _audit_item(
    *,
    row_id: str,
    dt: Optional[datetime],
    level: str,
    kind: str,
    actor: str,
    title: str,
    description: str,
    object_type: str,
    object_id: int,
    trace_id: str = "",
) -> dict[str, Any]:
    return {
        "id": row_id,
        "time": _iso(dt),
        "time_label": _audit_time_label(dt),
        "level": level,
        "kind": kind,
        "actor": actor,
        "title": title,
        "description": description,
        "object_type": object_type,
        "object_id": int(object_id or 0),
        "trace_id": trace_id or "",
    }


def _audit_chain_cache_hit() -> Optional[dict[str, Any]]:
    if _AUDIT_CHAIN_CACHE["data"] is None:
        return None
    if _time.monotonic() - _AUDIT_CHAIN_CACHE["ts"] >= _AUDIT_CHAIN_TTL:
        return None
    return _AUDIT_CHAIN_CACHE["data"]


@router.get("/neural/audit-chain")
async def monitor_neural_audit_chain(
    _=Depends(require_role("monitor")),
):
    # 注意：不在此处用 Depends(get_db) 取连接，否则缓存未命中时所有等锁的并发/重试请求
    # 都会各占一条 DB 连接干等，慢冷算(>10s)+前端轮询重试会把连接池占满拖垮全站。
    hit = _audit_chain_cache_hit()
    if hit is not None:
        return hit
    # 并发去重：缓存过期瞬间多个请求都进来时只让 1 个去算（且只有它占一条连接），其余等结果
    async with _AUDIT_CHAIN_LOCK:
        hit = _audit_chain_cache_hit()
        if hit is not None:
            return hit
        async with SessionLocal() as db:
            return await _compute_audit_chain(db)


async def _compute_audit_chain(db: AsyncSession) -> dict[str, Any]:
    # 统一近 7 日时间窗（含今日全天）作为所有 KPI / 节点 / 证据流的样本集
    now = datetime.utcnow()
    today = now.date()
    period_days = 7
    since_dt = datetime.combine(today - timedelta(days=period_days - 1), time.min)

    orders = (
        await db.scalars(
            select(Order).where(Order.created_at >= since_dt).order_by(Order.id.desc())
        )
    ).all()
    order_ids = [int(o.id) for o in orders]
    audits = (
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.created_at >= since_dt)
            .order_by(AuditLog.id.desc())
            .limit(_AUDIT_CHAIN_LOG_LIMIT)
        )
    ).all()
    order_status_logs = (
        await db.scalars(
            select(OrderStatusLog)
            .where(OrderStatusLog.created_at >= since_dt)
            .order_by(OrderStatusLog.id.desc())
            .limit(_AUDIT_CHAIN_LOG_LIMIT)
        )
    ).all()
    allocations = (
        await db.scalars(
            select(OrderItemAllocation).where(OrderItemAllocation.created_at >= since_dt).order_by(OrderItemAllocation.id.desc())
        )
    ).all()
    alloc_ids = [int(a.id) for a in allocations]
    item_status_logs = (
        await db.scalars(
            select(OrderItemStatusLog)
            .where(OrderItemStatusLog.created_at >= since_dt)
            .order_by(OrderItemStatusLog.id.desc())
            .limit(_AUDIT_CHAIN_LOG_LIMIT)
        )
    ).all()
    receiving_result = await db.execute(
        text(
            """
            SELECT id, order_id, line_index, status, draft_kg, confirmed_kg, confirmed_at,
                   confirmed_by_user_id, updated_at, shortage_reason_code, shortage_reason_detail,
                   shortage_ordered_kg, shortage_delta_kg
            FROM order_receiving_lines
            WHERE COALESCE(confirmed_at, updated_at) >= :since
            ORDER BY id DESC
            """
        ),
        {"since": since_dt},
    )
    receiving_lines = [SimpleNamespace(**dict(row._mapping), lock_photo_url=None) for row in receiving_result.fetchall()]
    quality_reports = (
        await db.scalars(
            select(QualityReport).where(QualityReport.created_at >= since_dt).order_by(QualityReport.id.desc())
        )
    ).all()
    bills = (
        await db.scalars(select(Bill).where(Bill.created_at >= since_dt).order_by(Bill.id.desc()))
    ).all()
    alerts = (
        await db.scalars(select(Alert).where(Alert.created_at >= since_dt).order_by(Alert.id.desc()))
    ).all()
    tickets = (
        await db.scalars(select(Ticket).where(Ticket.created_at >= since_dt).order_by(Ticket.id.desc()))
    ).all()
    # Delivery 模型没有 created_at，按 departed_at/arrived_at 任一在窗内或仍未发车的近期 deliveries 统计
    deliveries = (
        await db.scalars(
            select(Delivery)
            .where(
                or_(
                    Delivery.departed_at >= since_dt,
                    Delivery.arrived_at >= since_dt,
                    Delivery.departed_at.is_(None),
                )
            )
            .order_by(Delivery.id.desc())
        )
    ).all()
    canteens = (await db.scalars(select(ClientCanteen))).all()
    canteen_map = {int(c.id): c for c in canteens}

    user_ids: set[int] = set()
    for o in orders:
        for uid in (o.client_id, o.delivery_id, o.supplier_id):
            if uid:
                user_ids.add(int(uid))
    for row in audits:
        if row.actor_user_id:
            user_ids.add(int(row.actor_user_id))
    for row in order_status_logs:
        if row.actor_user_id:
            user_ids.add(int(row.actor_user_id))
    for row in item_status_logs:
        if row.operator_id:
            user_ids.add(int(row.operator_id))
    for row in allocations:
        for uid in (row.delivery_id, row.supplier_id, row.created_by):
            if uid:
                user_ids.add(int(uid))
    for row in tickets:
        if row.created_by:
            user_ids.add(int(row.created_by))
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(u.id): u for u in users}

    order_map = {int(o.id): o for o in orders}
    audits_by_order: dict[int, list[AuditLog]] = defaultdict(list)
    for row in audits:
        if row.object_type == "order" and int(row.object_id or 0) in order_map:
            audits_by_order[int(row.object_id)].append(row)
    status_by_order: dict[int, list[OrderStatusLog]] = defaultdict(list)
    for row in order_status_logs:
        if int(row.order_id or 0) in order_map:
            status_by_order[int(row.order_id)].append(row)
    allocs_by_order: dict[int, list[OrderItemAllocation]] = defaultdict(list)
    for row in allocations:
        if int(row.order_id or 0) in order_map:
            allocs_by_order[int(row.order_id)].append(row)
    receiving_by_order: dict[int, list[OrderReceivingLine]] = defaultdict(list)
    for row in receiving_lines:
        if int(row.order_id or 0) in order_map:
            receiving_by_order[int(row.order_id)].append(row)
    quality_by_order: dict[int, list[QualityReport]] = defaultdict(list)
    for row in quality_reports:
        if int(row.order_id or 0) in order_map:
            quality_by_order[int(row.order_id)].append(row)
    bills_by_order: dict[int, list[Bill]] = defaultdict(list)
    for row in bills:
        if int(row.order_id or 0) in order_map:
            bills_by_order[int(row.order_id)].append(row)
    tickets_by_order: dict[int, list[Ticket]] = defaultdict(list)
    for row in tickets:
        if int(row.order_id or 0) in order_map:
            tickets_by_order[int(row.order_id)].append(row)
    deliveries_by_order: dict[int, list[Delivery]] = defaultdict(list)
    for row in deliveries:
        if int(row.order_id or 0) in order_map:
            deliveries_by_order[int(row.order_id)].append(row)

    audited_order_ids = {
        oid
        for oid in order_ids
        if audits_by_order.get(oid) or status_by_order.get(oid)
    }
    open_alerts = [a for a in alerts if a.status == "open"]
    closed_alerts = [a for a in alerts if a.status == "closed"]
    pending_tickets = [t for t in tickets if t.status != "已关闭"]
    closed_tickets = [t for t in tickets if t.status == "已关闭"]
    # 批次质检存证模型：质检风险 = 已出库但缺报告的分单行（mode 感知，覆盖 batch/periodic）
    _quality_cov = await period_quality_coverage(
        db, allocations, quality_reports, orders, shipped_only=True
    )
    pending_quality = _quality_cov["missing_allocations"]
    passed_quality = [q for q in quality_reports if q.status == "已通过"]
    pending_bills = [b for b in bills if b.status != "已结算"]
    settled_bills = [b for b in bills if b.status == "已结算"]
    today_audits = [a for a in audits if _audit_day(a.created_at) == today]
    today_status_logs = [s for s in order_status_logs if _audit_day(s.created_at) == today]
    today_item_logs = [s for s in item_status_logs if _audit_day(s.created_at) == today]
    today_orders = [o for o in orders if _audit_day(o.created_at) == today]

    shipped_allocs = [a for a in allocations if a.status == "已出库"]
    active_deliveries = [d for d in deliveries if d.status in {"待发车", "运输中"}]
    confirmed_receiving = [r for r in receiving_lines if r.status == "confirmed"]
    shortage_receiving = [r for r in receiving_lines if _num(r.shortage_delta_kg) > 0]
    billed_orders = {int(b.order_id) for b in bills}
    quality_orders = {int(q.order_id) for q in quality_reports}
    closed_ticket_orders = {int(t.order_id) for t in tickets if t.status == "已关闭"}
    # 集合 risk 时只在"已出库的分单"内统计缺质检，避免 risk_count > count；
    # 复用覆盖率判定（mode 感知、分单级），与质检节点口径统一。
    shipped_alloc_order_ids = {int(a.order_id) for a in shipped_allocs}
    shipped_alloc_missing_quality = pending_quality
    # 配送异常工单仅就这次时间窗内的配送计数；保证 risk_count ≤ deliveries count
    delivery_order_ids = {int(d.order_id) for d in deliveries}
    delivery_pending_tickets = [
        t for t in pending_tickets
        if t.type == "配送异常" and int(t.order_id or 0) in delivery_order_ids
    ]
    # 时间窗内被配送状态触达过的订单（出现过"发货/收货"日志）
    shipping_status_logs = [s for s in order_status_logs if s.new_status in {"发货", "收货"}]
    # 异常订单：has_abnormal 或有未关闭工单
    abnormal_order_ids = {int(o.id) for o in orders if o.has_abnormal} | {
        int(t.order_id) for t in pending_tickets if t.order_id
    }
    # AuditLog.action 真实命名口径未必稳定，统一按 category 计数作为"该节点产生的可追溯证据条数"
    audits_by_category = Counter((a.category or "").lower() for a in audits)

    def stage_items_from_orders(rows: list[Order], limit: int = 12) -> list[dict[str, Any]]:
        return [
            {
                "order_id": int(row.id),
                "order_no": row.order_no,
                "status": row.status,
                "client_name": _canteen_name(canteen_map, row, user_map),
                "amount": _num(row.total_amount),
                "updated_at": _iso(row.updated_at or row.created_at),
            }
            for row in rows[:limit]
        ]

    stage_defs = [
        {
            "key": "order_create",
            "name": "采购下单",
            "count": len(orders),
            "risk_count": len(abnormal_order_ids & {int(o.id) for o in orders}),
            "watch_count": 0,
            "description": "订单创建即固化商品、单价、食堂、配送地址和时窗快照。",
            "evidence_count": audits_by_category.get("order", 0) + len(order_status_logs),
            "items": stage_items_from_orders(orders),
        },
        {
            "key": "allocation",
            "name": "智能分单",
            "count": len(allocations),
            "risk_count": len([a for a in allocations if a.status in {"待确认"}]),
            "watch_count": len([a for a in allocations if a.status in {"备货中"}]),
            "description": "配送商按订单行分配供货方，行级状态独立留痕。",
            "evidence_count": len(item_status_logs),
            "items": [
                {
                    "order_no": order_map.get(int(row.order_id)).order_no if int(row.order_id) in order_map else f"订单#{row.order_id}",
                    "line_no": int(row.line_no),
                    "supplier": _audit_actor(user_map, row.supplier_id, "供货商"),
                    "status": row.status,
                    "updated_at": _iso(row.updated_at),
                }
                for row in allocations[:12]
            ],
        },
        {
            "key": "supplier_ship",
            "name": "供货出库",
            "count": len(shipped_allocs),
            # 风险仅指"已出库但缺质检"，子集 ≤ count
            "risk_count": len(shipped_alloc_missing_quality),
            "watch_count": len([a for a in allocations if a.status in {"备货中", "已送达分拣场"}]),
            "description": "供货出库以分单行为最小单元，缺质检自动进入风险视图。",
            "evidence_count": len([s for s in item_status_logs if s.new_status in {"已出库"}]),
            "items": [
                {
                    "order_no": order_map.get(int(row.order_id)).order_no if int(row.order_id) in order_map else f"订单#{row.order_id}",
                    "line_no": int(row.line_no),
                    "supplier": _audit_actor(user_map, row.supplier_id, "供货商"),
                    "status": row.status,
                    "updated_at": _iso(row.updated_at),
                }
                for row in shipped_allocs[:12]
            ],
        },
        {
            "key": "delivery",
            "name": "配送履约",
            "count": len(deliveries),
            # 仅统计本时段配送订单关联的未关闭"配送异常"工单，保证 risk_count ≤ count
            "risk_count": min(len(delivery_pending_tickets), len(deliveries)),
            "watch_count": len(active_deliveries),
            "description": "配送发车、到达、车辆与司机信息进入履约链路。",
            "evidence_count": len(shipping_status_logs),
            "items": [
                {
                    "order_no": order_map.get(int(row.order_id)).order_no if int(row.order_id) in order_map else f"订单#{row.order_id}",
                    "driver_name": row.driver_name,
                    "vehicle_no": row.vehicle_no,
                    "status": row.status,
                    "departed_at": _iso(row.departed_at),
                    "arrived_at": _iso(row.arrived_at),
                }
                for row in deliveries[:12]
            ],
        },
        {
            "key": "receiving",
            "name": "称重收货",
            "count": len(confirmed_receiving),
            # 风险仅指"已确认 + 短收 > 0"的行，子集 ≤ count
            "risk_count": len([r for r in confirmed_receiving if _num(r.shortage_delta_kg) > 0]),
            "watch_count": len([r for r in receiving_lines if r.status == "pending"]),
            "description": "智能秤行级重量、短收原因、双方签字和锁定照片共同构成收货证据。",
            # 收货确认即一条证据；同时算上称重相关 AuditLog
            "evidence_count": len(confirmed_receiving) + len([a for a in audits if (a.action or "").startswith("order_receiving_")]),
            "items": [
                {
                    "order_no": order_map.get(int(row.order_id)).order_no if int(row.order_id) in order_map else f"订单#{row.order_id}",
                    "line_index": int(row.line_index),
                    "confirmed_kg": _num(row.confirmed_kg),
                    "shortage_delta_kg": _num(row.shortage_delta_kg),
                    "confirmed_at": _iso(row.confirmed_at),
                    "has_photo": bool(row.lock_photo_url),
                }
                for row in receiving_lines[:12]
            ],
        },
        {
            "key": "quality",
            "name": "质检留痕",
            "count": len(quality_reports),
            "risk_count": len(pending_quality),
            "watch_count": 0,
            "description": "批次质检报告与图片附件存证留痕（上传即有效），与订单、商品、供货方绑定；风险为已出库缺报告分单。",
            "evidence_count": len(quality_reports) + audits_by_category.get("quality", 0),
            "items": [
                {
                    "report_no": row.report_no,
                    "order_no": order_map.get(int(row.order_id)).order_no if int(row.order_id) in order_map else f"订单#{row.order_id}",
                    "supplier": _audit_actor(user_map, row.supplier_id, "供货商"),
                    "status": "已留痕",
                    "created_at": _iso(row.created_at),
                }
                for row in quality_reports[:12]
            ],
        },
        {
            "key": "billing",
            "name": "账务结算",
            "count": len(bills),
            "risk_count": len(pending_bills),
            "watch_count": 0,
            "description": "账单基于收货快照生成，历史结算不受后续商品或订单修改影响。",
            "evidence_count": len(bills) + audits_by_category.get("bill", 0),
            "items": [
                {
                    "order_no": order_map.get(int(row.order_id)).order_no if int(row.order_id) in order_map else f"订单#{row.order_id}",
                    "role": row.role,
                    "bill_type": row.bill_type,
                    "status": row.status,
                    "amount": _num(row.amount),
                    "created_at": _iso(row.created_at),
                }
                for row in bills[:12]
            ],
        },
        {
            "key": "closure",
            "name": "监管闭环",
            # count = 区间内已闭环的预警 + 已关闭的工单；和 risk 是 (closed, open) 互补集合
            "count": len(closed_alerts) + len(closed_tickets),
            "risk_count": len(open_alerts) + len(pending_tickets),
            "watch_count": len(pending_quality) + len(pending_bills),
            "description": "预警、工单、广播、账务与质检形成监管可追踪闭环。",
            "evidence_count": audits_by_category.get("system", 0) + len(closed_alerts) + len(closed_tickets),
            "items": [
                {
                    "type": row.type,
                    "level": row.level,
                    "status": row.status,
                    "description": row.description,
                    "created_at": _iso(row.created_at),
                }
                for row in alerts[:12]
            ],
        },
    ]
    stages = []
    for stage in stage_defs:
        status, label = _audit_status(int(stage["risk_count"]), int(stage.get("watch_count") or 0))
        stages.append({**stage, "status": status, "status_label": label})

    # ── evidence level 真实判定：异常订单 / 超时 / 已关闭工单为否 → risk；质检/未完成 → watch；其余 → stable
    def _audit_level_for(row, order: Optional[Order]) -> str:
        detail = (row.detail or "")
        # 文案中包含"超时/异常/失败"等风险关键词 → 风险
        if any(k in detail for k in ("超时", "异常", "失败", "缺失", "无法", "缺质检")):
            return "risk"
        if order and int(order.id) in abnormal_order_ids:
            return "risk"
        if (row.category or "").lower() == "quality":
            return "watch"
        return "stable"

    evidence_flow: list[dict[str, Any]] = []
    for row in audits[:80]:
        order = order_map.get(int(row.object_id or 0)) if row.object_type == "order" else None
        title = row.detail or row.action
        if order and row.action == "order_create":
            title = f"订单 {order.order_no} 创建并固化业务快照"
        evidence_flow.append(
            _audit_item(
                row_id=f"audit-{row.id}",
                dt=row.created_at,
                level=_audit_level_for(row, order),
                kind={"order": "订单", "quality": "质检", "bill": "账务", "system": "系统"}.get(row.category, row.category),
                actor=_audit_actor(user_map, row.actor_user_id),
                title=title,
                description=row.detail or f"{row.action} 已写入审计日志",
                object_type=row.object_type,
                object_id=int(row.object_id or 0),
                trace_id=row.trace_id,
            )
        )
    for row in order_status_logs[:80]:
        order = order_map.get(int(row.order_id))
        # 状态从正常流转入"已取消"等 → 风险；其他 → 稳定
        is_cancel = (row.new_status or "") in {"已取消", "取消", "异常"}
        level = "risk" if is_cancel or (order and int(order.id) in abnormal_order_ids) else "stable"
        evidence_flow.append(
            _audit_item(
                row_id=f"status-{row.id}",
                dt=row.created_at,
                level=level,
                kind="状态",
                actor=_audit_actor(user_map, row.actor_user_id),
                title=f"订单 {order.order_no if order else row.order_id} 状态流转",
                description=f"{row.old_status} -> {row.new_status}，状态机校验后自动留痕。",
                object_type="order",
                object_id=int(row.order_id),
            )
        )
    for row in receiving_lines[:40]:
        if not row.confirmed_at and not row.updated_at:
            continue
        order = order_map.get(int(row.order_id))
        shortage = _num(row.shortage_delta_kg)
        evidence_flow.append(
            _audit_item(
                row_id=f"receiving-{row.id}",
                dt=row.confirmed_at or row.updated_at,
                level="risk" if shortage > 0 else "stable",
                kind="称重",
                actor=_audit_actor(user_map, row.confirmed_by_user_id, "收货端"),
                title=f"订单 {order.order_no if order else row.order_id} 行{row.line_index}称重确认",
                description=(
                    f"实收 {float(row.confirmed_kg or row.draft_kg or 0):.3f}kg"
                    + (f"，短收 {shortage:.3f}kg，原因已记录。" if shortage > 0 else "，行级重量已锁定。")
                ),
                object_type="order",
                object_id=int(row.order_id),
            )
        )
    for row in alerts[:40]:
        evidence_flow.append(
            _audit_item(
                row_id=f"alert-{row.id}",
                dt=row.created_at,
                level="risk" if row.status == "open" else "stable",
                kind="预警",
                actor="监管规则引擎",
                title=f"{row.type} 预警",
                description=row.description,
                object_type="alert",
                object_id=int(row.id),
            )
        )
    evidence_flow.sort(key=lambda item: item.get("time") or "", reverse=True)

    trend_7d = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        trend_7d.append(
            {
                "date": day.isoformat(),
                "orders": len([o for o in orders if _audit_day(o.created_at) == day]),
                "evidence": len([a for a in audits if _audit_day(a.created_at) == day])
                + len([s for s in order_status_logs if _audit_day(s.created_at) == day])
                + len([s for s in item_status_logs if _audit_day(s.created_at) == day]),
                "risks": len([a for a in alerts if _audit_day(a.created_at) == day]),
            }
        )

    def completed_stage_count(order: Order) -> int:
        oid = int(order.id)
        checks = [
            bool(audits_by_order.get(oid) or status_by_order.get(oid)),
            bool(allocs_by_order.get(oid)),
            any(a.status == "已出库" for a in allocs_by_order.get(oid, [])),
            bool(deliveries_by_order.get(oid)) or order.status in {"发货", "收货", "收货确认", "已结算"},
            bool(receiving_by_order.get(oid)) or order.status in {"收货确认", "已结算"},
            bool(quality_by_order.get(oid)),
            oid in billed_orders or order.status == "已结算",
            not order.has_abnormal and not tickets_by_order.get(oid),
        ]
        return len([ok for ok in checks if ok])

    representative_orders = []
    for row in sorted(orders, key=lambda o: (bool(o.has_abnormal), o.updated_at or o.created_at), reverse=True)[:8]:
        oid = int(row.id)
        risk_count = int(bool(row.has_abnormal)) + len([t for t in tickets_by_order.get(oid, []) if t.status != "已关闭"])
        representative_orders.append(
            {
                "order_id": oid,
                "order_no": row.order_no,
                "status": row.status,
                "client_name": _canteen_name(canteen_map, row, user_map),
                "amount": _num(row.total_amount),
                "risk_count": risk_count,
                "completed_stage_count": completed_stage_count(row),
                "updated_at": _iso(row.updated_at or row.created_at),
            }
        )

    total_alerts = len(alerts)
    total_tickets = len(tickets)
    pending_attention = len(open_alerts) + len(pending_tickets) + len(pending_quality) + len(pending_bills)
    period_evidence = len(audits) + len(order_status_logs) + len(item_status_logs)
    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "period": {
            "days": period_days,
            "since": since_dt.isoformat(),
            "until": now.isoformat(),
        },
        "summary": {
            # 近 7 日窗口指标
            "period_chain_orders": len(orders),
            "today_chain_orders": len(today_orders),
            "audit_coverage_rate": _pct(len(audited_order_ids), len(orders)),
            # 闭环不再用单一百分比，拆成 (已闭环, 待闭环) 让领导一眼看清绝对值
            "closure_done": len(closed_alerts) + len(closed_tickets),
            "closure_pending": len(open_alerts) + len(pending_tickets),
            "closure_rate": (
                _pct(
                    len(closed_alerts) + len(closed_tickets),
                    total_alerts + total_tickets,
                )
                if (total_alerts + total_tickets) > 0
                else None
            ),
            # 待办拆分四类（开放预警 / 待办工单 / 待审质检 / 未结账单）
            "pending_attention": pending_attention,
            "pending_alerts": len(open_alerts),
            "pending_tickets": len(pending_tickets),
            "pending_quality": len(pending_quality),
            "pending_bills": len(pending_bills),
            # 证据量：区间 vs 今日
            "period_evidence_count": period_evidence,
            "today_evidence_count": len(today_audits) + len(today_status_logs) + len(today_item_logs),
        },
        "stages": stages,
        "evidence_flow": evidence_flow[:60],
        "representative_orders": representative_orders,
        "trend_7d": trend_7d,
    }
    _AUDIT_CHAIN_CACHE["data"] = result
    _AUDIT_CHAIN_CACHE["ts"] = _time.monotonic()
    return result


@router.get("/neural/order-audit/{order_id}")
async def monitor_neural_order_audit(
    order_id: int,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """单订单完整审计档案：基础信息 + 各节点链路完成度 + 关联证据全量。"""
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    canteens = (await db.scalars(select(ClientCanteen))).all()
    canteen_map = {int(c.id): c for c in canteens}

    audits = list(
        (await db.scalars(
            select(AuditLog)
            .where(AuditLog.object_type == "order", AuditLog.object_id == order_id)
            .order_by(AuditLog.id.desc())
        )).all()
    )
    status_logs = list(
        (await db.scalars(
            select(OrderStatusLog).where(OrderStatusLog.order_id == order_id).order_by(OrderStatusLog.id.desc())
        )).all()
    )
    allocations = list(
        (await db.scalars(
            select(OrderItemAllocation).where(OrderItemAllocation.order_id == order_id).order_by(OrderItemAllocation.id.desc())
        )).all()
    )
    # OrderItemStatusLog 通过 allocation_id 间接关联订单
    alloc_ids = [int(a.id) for a in allocations]
    item_logs = list(
        (await db.scalars(
            select(OrderItemStatusLog)
            .where(OrderItemStatusLog.allocation_id.in_(alloc_ids))
            .order_by(OrderItemStatusLog.id.desc())
        )).all()
    ) if alloc_ids else []
    receiving_result = await db.execute(
        text(
            """
            SELECT id, order_id, line_index, status, draft_kg, confirmed_kg, confirmed_at,
                   confirmed_by_user_id, updated_at, shortage_reason_code, shortage_reason_detail,
                   shortage_ordered_kg, shortage_delta_kg
            FROM order_receiving_lines
            WHERE order_id = :oid
            ORDER BY line_index ASC
            """
        ),
        {"oid": order_id},
    )
    receiving_lines = [SimpleNamespace(**dict(row._mapping), lock_photo_url=None) for row in receiving_result.fetchall()]
    quality_reports = list(
        (await db.scalars(
            select(QualityReport).where(QualityReport.order_id == order_id).order_by(QualityReport.id.desc())
        )).all()
    )
    bills = list(
        (await db.scalars(select(Bill).where(Bill.order_id == order_id).order_by(Bill.id.desc()))).all()
    )
    tickets = list(
        (await db.scalars(select(Ticket).where(Ticket.order_id == order_id).order_by(Ticket.id.desc()))).all()
    )
    deliveries = list(
        (await db.scalars(select(Delivery).where(Delivery.order_id == order_id).order_by(Delivery.id.desc()))).all()
    )

    user_ids: set[int] = set()
    for uid in (order.client_id, order.delivery_id, order.supplier_id):
        if uid:
            user_ids.add(int(uid))
    for row in audits:
        if row.actor_user_id:
            user_ids.add(int(row.actor_user_id))
    for row in status_logs:
        if row.actor_user_id:
            user_ids.add(int(row.actor_user_id))
    for row in item_logs:
        if row.operator_id:
            user_ids.add(int(row.operator_id))
    for row in allocations:
        for uid in (row.delivery_id, row.supplier_id, row.created_by):
            if uid:
                user_ids.add(int(uid))
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(u.id): u for u in users}

    shipped = [a for a in allocations if a.status == "已出库"]
    confirmed_receiving = [r for r in receiving_lines if r.status == "confirmed"]
    pending_tickets = [t for t in tickets if t.status != "已关闭"]
    risk_count = int(bool(order.has_abnormal)) + len(pending_tickets)
    stage_checks = [
        bool(audits or status_logs),
        bool(allocations),
        bool(shipped),
        bool(deliveries) or order.status in {"发货", "收货", "收货确认", "已结算"},
        bool(receiving_lines) or order.status in {"收货确认", "已结算"},
        bool(quality_reports),
        bool(bills) or order.status == "已结算",
        not order.has_abnormal and not pending_tickets,
    ]
    completed_stage_count = sum(1 for ok in stage_checks if ok)

    evidence_flow: list[dict[str, Any]] = []
    for row in audits:
        evidence_flow.append(
            _audit_item(
                row_id=f"audit-{row.id}",
                dt=row.created_at,
                level="risk" if (row.detail or "") and any(k in row.detail for k in ("超时", "异常", "失败", "缺")) else (
                    "watch" if (row.category or "").lower() == "quality" else "stable"
                ),
                kind={"order": "订单", "quality": "质检", "bill": "账务", "system": "系统"}.get(row.category, row.category or ""),
                actor=_audit_actor(user_map, row.actor_user_id),
                title=row.detail or row.action,
                description=row.detail or f"{row.action} 已写入审计日志",
                object_type="order",
                object_id=order_id,
                trace_id=row.trace_id,
            )
        )
    for row in status_logs:
        evidence_flow.append(
            _audit_item(
                row_id=f"status-{row.id}",
                dt=row.created_at,
                level="risk" if (row.new_status or "") in {"已取消", "取消", "异常"} else "stable",
                kind="状态",
                actor=_audit_actor(user_map, row.actor_user_id),
                title=f"状态流转 {row.old_status} → {row.new_status}",
                description=f"订单 {order.order_no} 状态机校验后留痕",
                object_type="order",
                object_id=order_id,
            )
        )
    for row in receiving_lines:
        if not row.confirmed_at and not row.updated_at:
            continue
        shortage = _num(row.shortage_delta_kg)
        evidence_flow.append(
            _audit_item(
                row_id=f"receiving-{row.id}",
                dt=row.confirmed_at or row.updated_at,
                level="risk" if shortage > 0 else "stable",
                kind="称重",
                actor=_audit_actor(user_map, row.confirmed_by_user_id, "收货端"),
                title=f"行 {row.line_index} 称重确认",
                description=(
                    f"实收 {float(row.confirmed_kg or row.draft_kg or 0):.3f}kg"
                    + (f"，短收 {shortage:.3f}kg" if shortage > 0 else "，行级重量已锁定")
                ),
                object_type="order",
                object_id=order_id,
            )
        )
    for row in tickets:
        evidence_flow.append(
            _audit_item(
                row_id=f"ticket-{row.id}",
                dt=row.created_at,
                level="risk" if row.status != "已关闭" else "stable",
                kind="工单",
                actor=_audit_actor(user_map, row.created_by),
                title=f"{row.type} 工单 · {row.status}",
                description=row.description or "",
                object_type="order",
                object_id=order_id,
            )
        )
    evidence_flow.sort(key=lambda item: item.get("time") or "", reverse=True)

    return {
        "order_id": order_id,
        "order_no": order.order_no,
        "status": order.status,
        "client_name": _canteen_name(canteen_map, order, user_map),
        "amount": _num(order.total_amount),
        "risk_count": risk_count,
        "completed_stage_count": completed_stage_count,
        "created_at": _iso(order.created_at),
        "updated_at": _iso(order.updated_at or order.created_at),
        "supplier_name": _audit_actor(user_map, order.supplier_id, "—"),
        "delivery_name": _audit_actor(user_map, order.delivery_id, "—"),
        "allocations_count": len(allocations),
        "shipped_count": len(shipped),
        "receiving_count": len(confirmed_receiving),
        "quality_count": len(quality_reports),
        "bills_count": len(bills),
        "pending_tickets_count": len(pending_tickets),
        "evidence_flow": evidence_flow,
    }


@router.get("/neural/logistics")
async def monitor_neural_logistics(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    today, now_cn, start_dt, end_dt = _china_today_window()
    now_utc = datetime.utcnow()

    orders = (
        await db.scalars(
            select(Order)
            .where(
                Order.expected_delivery_date == today,
                Order.status != "取消",
            )
            .order_by(Order.id.desc())
            .limit(1200)
        )
    ).all()
    # 二次过滤，避免脏数据或类型不一致导致非今日配送日订单混入
    orders = [o for o in orders if o.expected_delivery_date == today]
    order_ids = [int(o.id) for o in orders]
    order_id_set = set(order_ids)

    trips = (
        await db.scalars(
            select(DeliveryDispatchTrip)
            .where(DeliveryDispatchTrip.planning_date == today)
            .order_by(DeliveryDispatchTrip.id.desc())
            .limit(300)
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
            select(OrderItemAllocation).where(
                OrderItemAllocation.order_id.in_(order_ids or [-1]),
            )
        )
    ).all() if order_ids else []
    allocation_ids = [int(a.id) for a in allocations]
    scan_records = (
        await db.scalars(
            select(DeliverySortScanRecord).where(DeliverySortScanRecord.allocation_id.in_(allocation_ids))
        )
    ).all() if allocation_ids else []

    # Alert 无 order_id 列，关联订单写在 payload_json.order_id
    alert_candidates = (
        await db.scalars(
            select(Alert)
            .where(Alert.status == "open")
            .order_by(Alert.id.desc())
            .limit(240)
        )
    ).all()
    order_id_set_for_alerts = set(order_ids)
    alerts: list[Alert] = []
    for alert in alert_candidates:
        in_window = alert.created_at >= start_dt and alert.created_at < end_dt
        linked_order = False
        if order_id_set_for_alerts and isinstance(alert.payload_json, dict):
            try:
                linked_order = int(alert.payload_json.get("order_id") or 0) in order_id_set_for_alerts
            except (TypeError, ValueError):
                linked_order = False
        if in_window or linked_order:
            alerts.append(alert)
        if len(alerts) >= 120:
            break
    tickets = (
        await db.scalars(
            select(Ticket)
            .where(
                Ticket.status != "已关闭",
                or_(
                    Ticket.order_id.in_(order_ids or [-1]),
                    and_(Ticket.created_at >= start_dt, Ticket.created_at < end_dt),
                ),
            )
            .order_by(Ticket.id.desc())
            .limit(200)
        )
    ).all()
    recent_status_logs = (
        await db.scalars(
            select(OrderStatusLog)
            .where(
                OrderStatusLog.created_at >= start_dt,
                OrderStatusLog.created_at < end_dt,
                OrderStatusLog.order_id.in_(order_ids or [-1]),
            )
            .order_by(OrderStatusLog.id.desc())
            .limit(120)
        )
    ).all() if order_ids else []

    canteens = (await db.scalars(select(ClientCanteen))).all()
    canteen_map = {int(c.id): c for c in canteens}
    user_ids = {
        int(uid)
        for o in orders
        for uid in (o.client_id, o.delivery_id, o.supplier_id)
        if uid is not None
    }
    user_ids.update(int(t.delivery_id) for t in trips if t.delivery_id)
    user_ids.update(int(i.supplier_id) for i in items if i.supplier_id)
    user_ids.update(int(a.supplier_id) for a in allocations if a.supplier_id)
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(u.id): u for u in users}

    product_ids = {
        int(pid)
        for pid in [*(a.product_id for a in allocations if a.product_id), *(i.product_id for i in items if i.product_id)]
    }
    products = (await db.scalars(select(Product).where(Product.id.in_(product_ids)))).all() if product_ids else []
    product_map = {int(p.id): p for p in products}

    vehicle_ids = [int(t.vehicle_id) for t in trips if t.vehicle_id]
    vehicles = (
        await db.scalars(select(DeliveryVehicle).where(DeliveryVehicle.id.in_(vehicle_ids)))
    ).all() if vehicle_ids else []
    vehicle_map = {int(v.id): v for v in vehicles}

    device_rows = (
        await db.execute(
            select(DeliveryVehicleDeviceBinding.vehicle_id, DeliveryDevice)
            .join(DeliveryDevice, DeliveryDevice.id == DeliveryVehicleDeviceBinding.device_id)
            .where(DeliveryVehicleDeviceBinding.vehicle_id.in_(vehicle_ids))
        )
    ).all() if vehicle_ids else []
    device_by_vehicle: dict[int, list[DeliveryDevice]] = defaultdict(list)
    for vehicle_id, device in device_rows:
        device_by_vehicle[int(vehicle_id)].append(device)

    from services.beidou_client import beidou_reported_at_display, enrich_beidou_devices_live

    all_beidou_devices = [
        d for devs in device_by_vehicle.values() for d in devs if str(d.vendor or "").lower() == "beidou"
    ]
    if all_beidou_devices:
        await enrich_beidou_devices_live(all_beidou_devices, db=db, persist=False)

    order_map = {int(o.id): o for o in orders}
    scans_by_alloc = {int(s.allocation_id): s for s in scan_records}
    allocs_by_order: dict[int, list[OrderItemAllocation]] = defaultdict(list)
    for alloc in allocations:
        allocs_by_order[int(alloc.order_id)].append(alloc)
    stops_by_trip: dict[int, list[DeliveryDispatchStop]] = defaultdict(list)
    for stop in stops:
        stops_by_trip[int(stop.trip_id)].append(stop)
    items_by_trip: dict[int, list[DeliveryDispatchItem]] = defaultdict(list)
    for item in items:
        items_by_trip[int(item.trip_id)].append(item)
    item_by_alloc: dict[int, DeliveryDispatchItem] = {}
    for item in items:
        item_by_alloc.setdefault(int(item.allocation_id), item)
    route_by_order: dict[int, str] = {}
    stop_by_order: dict[int, DeliveryDispatchStop] = {}
    for stop in stops:
        stop_by_order[int(stop.order_id)] = stop
    trip_by_id = {int(t.id): t for t in trips}
    for trip_id, trip_stops in stops_by_trip.items():
        trip = trip_by_id.get(int(trip_id))
        for stop in trip_stops:
            if trip and trip.route_no:
                route_by_order.setdefault(int(stop.order_id), trip.route_no)

    shipped_alloc_ids = {int(a.id) for a in allocations if str(a.status) == "已出库"}
    scanned_alloc_ids = set(scans_by_alloc.keys())
    loaded_statuses = {"已装车"}
    not_loaded_statuses = {"滞留未装", "取消随车", "供应商迟到", "质量问题", "现场缺货"}
    loaded_alloc_ids = {int(i.allocation_id) for i in items if str(i.status) in loaded_statuses}
    not_loaded_items = [i for i in items if str(i.status) in not_loaded_statuses]

    total_orders = len([o for o in orders if o.status != "取消"])
    delivered_orders = len([o for o in orders if o.status in {"收货", "收货确认", "已结算"}])
    in_transit_orders = len([o for o in orders if o.status == "发货"])
    total_allocations = len(allocations)
    not_shipped_count = len([a for a in allocations if str(a.status) != "已出库"])
    not_scanned_count = len([a for a in allocations if str(a.status) == "已出库" and int(a.id) not in scanned_alloc_ids])
    scanned_count = len([a for a in allocations if int(a.id) in scanned_alloc_ids])
    blocked_allocations = not_shipped_count + not_scanned_count + len(not_loaded_items)

    def _client_name(order: Order) -> str:
        return _user_name(user_map, order.client_id, "客户")

    def _order_canteen_name(order: Order) -> str:
        if order.canteen_id and int(order.canteen_id) in canteen_map:
            return canteen_map[int(order.canteen_id)].name or ""
        return _client_name(order)

    def _product_name(product_id: Optional[int]) -> str:
        product = product_map.get(int(product_id or 0))
        return product.name if product else "商品未识别"

    def _product_spec_unit(product_id: Optional[int]) -> tuple[str, str]:
        product = product_map.get(int(product_id or 0))
        if not product:
            return "", ""
        return product.spec or "", product.unit or ""

    def _scan_time(allocation_id: int) -> Optional[str]:
        record = scans_by_alloc.get(int(allocation_id))
        return _iso(record.scanned_at) if record else None

    def _allocation_business_status(alloc: OrderItemAllocation) -> tuple[str, str]:
        if str(alloc.status) != "已出库":
            return "未出库", "供货商/厂家尚未完成出库登记"
        if int(alloc.id) not in scanned_alloc_ids:
            return "未分检", "配送商分检端尚未扫码确认"
        item = item_by_alloc.get(int(alloc.id))
        if item and str(item.status) in not_loaded_statuses:
            return "未随车", item.reason_detail or item.status or "异常发车留置"
        if item and str(item.status) in loaded_statuses:
            return "已装车", "已进入车次装车清单"
        return "已分检", "PDA 已扫码分检完成"

    orders_detail: list[dict[str, Any]] = []
    for order in orders:
        order_allocs = allocs_by_order.get(int(order.id), [])
        scanned_for_order = len([a for a in order_allocs if int(a.id) in scanned_alloc_ids])
        route_no = route_by_order.get(int(order.id), "")
        orders_detail.append(
            {
                "order_id": int(order.id),
                "order_no": order.order_no,
                "client_name": _client_name(order),
                "canteen_name": _order_canteen_name(order),
                "delivery_name": _user_name(user_map, order.delivery_id, "配送商"),
                "expected_delivery_date": order.expected_delivery_date.isoformat() if order.expected_delivery_date else "",
                "expected_delivery_slot": order.expected_delivery_slot or "",
                "status": order.status,
                "amount": round(_num(order.total_amount), 2),
                "sort_progress": f"{scanned_for_order}/{len(order_allocs)}",
                "route_no": route_no or "暂未绑定车次",
            }
        )

    allocations_detail: list[dict[str, Any]] = []
    for alloc in allocations:
        if int(alloc.order_id) not in order_id_set:
            continue
        order = order_map.get(int(alloc.order_id))
        spec, product_unit = _product_spec_unit(alloc.product_id)
        item = item_by_alloc.get(int(alloc.id))
        business_status, reason = _allocation_business_status(alloc)
        allocations_detail.append(
            {
                "allocation_id": int(alloc.id),
                "allocation_no": f"{order.order_no if order else '订单'}-A{int(alloc.id)}",
                "order_id": int(alloc.order_id),
                "order_no": order.order_no if order else f"订单#{alloc.order_id}",
                "client_name": _client_name(order) if order else "",
                "canteen_name": _order_canteen_name(order) if order else "",
                "supplier_id": int(alloc.supplier_id),
                "supplier_name": _user_name(user_map, alloc.supplier_id, "供应商"),
                "product_name": item.product_name if item and item.product_name else _product_name(alloc.product_id),
                "spec_unit": item.spec_unit if item and item.spec_unit else f"{spec}/{product_unit}".strip("/"),
                "quantity": float(alloc.quantity or 0),
                "unit": item.unit if item and item.unit else product_unit,
                "shipment_status": "已出库" if str(alloc.status) == "已出库" else "未出库",
                "sort_status": "已分检" if int(alloc.id) in scanned_alloc_ids else "未分检",
                "scan_time": _scan_time(int(alloc.id)) or "未扫码",
                "load_status": item.status if item else "未进入车次",
                "not_loaded_reason": item.reason_detail or item.reason_code if item and str(item.status) in not_loaded_statuses else "",
                "business_status": business_status,
                "reason": reason,
                "route_no": route_by_order.get(int(alloc.order_id), "暂未绑定车次"),
            }
        )

    funnel = [
        {"key": "orders", "label": "今日订单", "count": total_orders, "total": total_orders},
        {"key": "allocated", "label": "已分单", "count": len({int(a.order_id) for a in allocations}), "total": total_orders},
        {"key": "shipped", "label": "已出库", "count": len(shipped_alloc_ids), "total": total_allocations},
        {"key": "sorted", "label": "已分检", "count": scanned_count, "total": total_allocations},
        {"key": "loaded", "label": "已装车/可发", "count": len(loaded_alloc_ids) or sum(int(t.ready_count or 0) for t in trips), "total": total_allocations},
        {"key": "departed", "label": "已发车", "count": len([t for t in trips if t.status == "运输中" or t.departed_at]), "total": len(trips)},
        {"key": "arrived", "label": "已送达", "count": delivered_orders, "total": total_orders},
    ]
    for row in funnel:
        row["percent"] = _pct(row["count"], row["total"])

    supplier_blocks: dict[int, dict[str, Any]] = {}
    def ensure_supplier(supplier_id: int, supplier_name: str) -> dict[str, Any]:
        row = supplier_blocks.setdefault(
            int(supplier_id or 0),
            {
                "supplier_id": int(supplier_id or 0),
                "supplier_name": supplier_name or "供应商未识别",
                "not_shipped": 0,
                "not_sorted": 0,
                "not_loaded": 0,
                "affected_orders": set(),
                "affected_clients": set(),
                "affected_trips": set(),
            },
        )
        if supplier_name and row["supplier_name"] == "供应商未识别":
            row["supplier_name"] = supplier_name
        return row

    for alloc in allocations:
        if str(alloc.status) == "已出库" and int(alloc.id) in scanned_alloc_ids:
            continue
        order = order_map.get(int(alloc.order_id))
        row = ensure_supplier(int(alloc.supplier_id), _user_name(user_map, alloc.supplier_id, "供应商"))
        if str(alloc.status) != "已出库":
            row["not_shipped"] += 1
        elif int(alloc.id) not in scanned_alloc_ids:
            row["not_sorted"] += 1
        row["affected_orders"].add(int(alloc.order_id))
        if order:
            row["affected_clients"].add(_canteen_name(canteen_map, order, user_map))
    for item in not_loaded_items:
        order = order_map.get(int(item.order_id))
        row = ensure_supplier(int(item.supplier_id), item.supplier_name or _user_name(user_map, item.supplier_id, "供应商"))
        row["not_loaded"] += 1
        row["affected_orders"].add(int(item.order_id))
        row["affected_trips"].add(int(item.trip_id))
        if order:
            row["affected_clients"].add(_canteen_name(canteen_map, order, user_map))

    supplier_block_rows = []
    for row in supplier_blocks.values():
        total_block = int(row["not_shipped"] + row["not_sorted"] + row["not_loaded"])
        if total_block <= 0:
            continue
        supplier_block_rows.append(
            {
                "supplier_id": row["supplier_id"],
                "supplier_name": row["supplier_name"],
                "not_shipped": int(row["not_shipped"]),
                "not_sorted": int(row["not_sorted"]),
                "not_loaded": int(row["not_loaded"]),
                "blocked_count": total_block,
                "affected_orders": len(row["affected_orders"]),
                "affected_clients": list(sorted(row["affected_clients"]))[:4],
                "affected_trips": len(row["affected_trips"]),
                "orders": [
                    detail
                    for detail in orders_detail
                    if int(detail["order_id"]) in row["affected_orders"]
                ][:30],
                "allocations": [
                    detail
                    for detail in allocations_detail
                    if int(detail["supplier_id"]) == int(row["supplier_id"])
                    and detail["business_status"] in {"未出库", "未分检", "未随车"}
                ][:30],
            }
        )
    supplier_block_rows.sort(key=lambda r: r["blocked_count"], reverse=True)

    trip_cards = []
    for trip in trips:
        trip_stops = sorted(stops_by_trip.get(int(trip.id), []), key=lambda s: (int(s.sequence), int(s.id)))
        # 仅保留今日配送日订单对应的站点（排除排线日=今天但订单配送日≠今天的脏数据）
        trip_stops = [
            stop for stop in trip_stops
            if int(stop.order_id) in order_id_set
            or (stop.expected_delivery_date and stop.expected_delivery_date == today)
        ]
        trip_items = [i for i in items_by_trip.get(int(trip.id), []) if int(i.order_id) in order_id_set]
        vehicle_devices = device_by_vehicle.get(int(trip.vehicle_id or 0), [])
        beidou_count = len([d for d in vehicle_devices if str(d.vendor) == "beidou"])
        camera_count = len([d for d in vehicle_devices if str(d.vendor) == "ys7" and str(d.device_type) == "camera"])
        stop_rows = [
            {
                "sequence": int(stop.sequence),
                "order_no": stop.order_no,
                "client_name": stop.client_name,
                "canteen_name": stop.canteen_name,
                "address": stop.address,
                "expected_delivery_date": stop.expected_delivery_date.isoformat() if stop.expected_delivery_date else "",
                "expected_delivery_slot": stop.expected_delivery_slot,
                "planned_arrive_time": stop.planned_arrive_time,
                "status": stop.status,
                "affected": bool(stop.affected),
            }
            for stop in trip_stops
        ]
        item_rows = [
            {
                "order_no": order_map.get(int(item.order_id)).order_no if int(item.order_id) in order_map else f"订单#{item.order_id}",
                "supplier_name": item.supplier_name,
                "product_name": item.product_name,
                "spec_unit": item.spec_unit,
                "quantity": float(item.quantity or 0),
                "unit": item.unit,
                "status": item.status,
                "reason": item.reason_detail or item.reason_code or "",
            }
            for item in trip_items[:60]
        ]
        trip_cards.append(
            {
                "id": int(trip.id),
                "route_no": trip.route_no,
                "planning_date": trip.planning_date.isoformat() if trip.planning_date else "",
                "source": trip.source,
                "status": trip.status,
                "depart_mode": trip.depart_mode,
                "delivery_name": _user_name(user_map, trip.delivery_id, "配送商"),
                "vehicle_no": trip.vehicle_no,
                "driver_name": trip.driver_name,
                "departure_time": trip.departure_time,
                "departed_at": _iso(trip.departed_at),
                "completed_at": _iso(trip.completed_at),
                "total_orders": int(trip.total_orders or len({int(s.order_id) for s in trip_stops})),
                "total_allocations": int(trip.total_allocations or len(trip_items)),
                "ready_count": int(trip.ready_count or 0),
                "blocked_count": int(trip.blocked_count or 0),
                "not_loaded_count": int(trip.not_loaded_count or 0),
                "stop_count": len(trip_stops),
                "affected_stop_count": len([s for s in trip_stops if s.affected or s.status in {"有阻塞", "未随车"}]),
                "distance_km": round(_num(trip.distance_km), 2),
                "duration_minutes": int(trip.duration_minutes or 0),
                "risk_count": len(trip.risk_alerts_json or []),
                "beidou_count": beidou_count,
                "camera_count": camera_count,
                "items": len(trip_items),
                "stops": stop_rows,
                "item_details": item_rows,
                "risk_alerts": [
                    str((item.get("message") or item.get("reason") or item) if isinstance(item, dict) else item)
                    for item in (trip.risk_alerts_json or [])
                ][:12],
            }
        )

    in_transit_cards = []
    for trip in trips:
        if str(trip.status) != "运输中":
            continue
        vehicle_devices = device_by_vehicle.get(int(trip.vehicle_id or 0), [])
        beidou = next((d for d in vehicle_devices if str(d.vendor) == "beidou"), None)
        raw = beidou.raw_payload_json if beidou and isinstance(beidou.raw_payload_json, dict) else {}
        reported_at = beidou_reported_at_display(raw) if raw else ""
        trip_stops = sorted(stops_by_trip.get(int(trip.id), []), key=lambda s: (int(s.sequence), int(s.id)))
        trip_stops = [stop for stop in trip_stops if int(stop.order_id) in order_id_set]
        for stop in trip_stops:
            order = order_map.get(int(stop.order_id))
            in_transit_cards.append(
                {
                    "trip_id": int(trip.id),
                    "route_no": trip.route_no,
                    "order_id": int(stop.order_id),
                    "order_no": stop.order_no or (order.order_no if order else ""),
                    "client_name": stop.client_name or (order and _canteen_name(canteen_map, order, user_map)) or "",
                    "canteen_name": stop.canteen_name,
                    "delivery_name": _user_name(user_map, trip.delivery_id, "配送商"),
                    "vehicle_no": trip.vehicle_no,
                    "driver_name": trip.driver_name,
                    "status": stop.status,
                    "expected_delivery_date": stop.expected_delivery_date.isoformat() if stop.expected_delivery_date else None,
                    "expected_delivery_slot": stop.expected_delivery_slot,
                    "planned_arrive_time": stop.planned_arrive_time,
                    "beidou_reported_at": str(reported_at or ""),
                    "has_beidou": bool(beidou),
                    "risk": "缺少北斗定位" if not beidou else ("北斗未上报时间" if not reported_at else ""),
                }
            )

    risk_events: list[dict[str, Any]] = []
    def _risk_level_label(level: str) -> str:
        return {"high": "高风险", "medium": "需关注", "low": "提示"}.get(str(level or ""), "需关注")

    for row in supplier_block_rows[:12]:
        level = "high" if row["blocked_count"] >= 5 else "medium"
        risk_events.append(
            {
                "id": f"supplier-{row['supplier_id']}",
                "level": level,
                "level_label": _risk_level_label(level),
                "business_type": "供应商履约阻塞",
                "type": "供应商阻塞",
                "title": row["supplier_name"],
                "description": f"未出库 {row['not_shipped']} · 未分检 {row['not_sorted']} · 未随车 {row['not_loaded']}，影响 {row['affected_orders']} 单",
                "created_at": None,
                "related_orders": row["orders"][:8],
                "related_items": row["allocations"][:12],
                "suggestion": "请优先联系该供应商确认出库、分检或未随车原因，必要时协调异常发车或补送。",
            }
        )
    for trip in trips:
        if str(trip.status) == "运输中" and trip.departed_at and (now_utc - trip.departed_at).total_seconds() > 4 * 3600:
            related_orders = [
                detail
                for detail in orders_detail
                if int(detail["order_id"]) in {int(s.order_id) for s in stops_by_trip.get(int(trip.id), [])}
            ][:8]
            risk_events.append(
                {
                    "id": f"trip-late-{trip.id}",
                    "trip_id": int(trip.id),
                    "vehicle_no": trip.vehicle_no or "",
                    "level": "high",
                    "level_label": _risk_level_label("high"),
                    "business_type": "配送在途超时",
                    "type": "在途超时",
                    "title": trip.route_no,
                    "description": f"{trip.vehicle_no or '-'} 已发车超过 4 小时仍未完成",
                    "created_at": _iso(trip.departed_at),
                    "related_orders": related_orders,
                    "related_items": [],
                    "suggestion": "请联系配送商或司机核实车辆位置、预计到达时间，并同步客户/食堂。",
                }
            )
        if trip.vehicle_id and not any(str(d.vendor) == "beidou" for d in device_by_vehicle.get(int(trip.vehicle_id), [])):
            risk_events.append(
                {
                    "id": f"trip-no-beidou-{trip.id}",
                    "trip_id": int(trip.id),
                    "vehicle_no": trip.vehicle_no or "",
                    "level": "medium",
                    "level_label": _risk_level_label("medium"),
                    "business_type": "车辆定位缺失",
                    "type": "定位缺失",
                    "title": trip.route_no,
                    "description": f"{trip.vehicle_no or '-'} 未绑定有效北斗设备",
                    "created_at": _iso(trip.created_at),
                    "related_orders": [
                        detail
                        for detail in orders_detail
                        if int(detail["order_id"]) in {int(s.order_id) for s in stops_by_trip.get(int(trip.id), [])}
                    ][:8],
                    "related_items": [],
                    "suggestion": "请在车辆管理中核对北斗设备绑定，避免监管地图无法呈现车辆实时位置。",
                }
            )
    for item in not_loaded_items[:20]:
        level = "high" if str(item.status) in {"质量问题", "现场缺货"} else "medium"
        related_order = order_map.get(int(item.order_id))
        risk_events.append(
            {
                "id": f"not-loaded-{item.id}",
                "level": level,
                "level_label": _risk_level_label(level),
                "business_type": "异常发车未随车",
                "type": "未随车",
                "title": item.product_name,
                "description": f"{item.supplier_name} · {item.quantity:g}{item.unit or ''} · {item.reason_detail or item.status}",
                "created_at": _iso(item.updated_at),
                "related_orders": [
                    detail for detail in orders_detail if int(detail["order_id"]) == int(item.order_id)
                ][:1],
                "related_items": [
                    detail for detail in allocations_detail if int(detail["allocation_id"]) == int(item.allocation_id)
                ][:1],
                "suggestion": "请确认该商品是否需要补送、退货或在客户收货时按实收数量处理。",
            }
        )
    for alert in alerts:
        if "配送" in str(alert.type) or "车辆" in str(alert.type) or "履约" in str(alert.type):
            level = str(alert.level or "medium")
            risk_events.append(
                {
                    "id": f"alert-{alert.id}",
                    "level": level,
                    "level_label": _risk_level_label(level),
                    "business_type": "系统预警",
                    "type": alert.type,
                    "title": f"{alert.type}预警",
                    "description": alert.description,
                    "created_at": _iso(alert.created_at),
                    "related_orders": [],
                    "related_items": [],
                    "suggestion": "请进入预警中心查看处理状态，必要时转派运营或配送商跟进。",
                }
            )
    for ticket in tickets:
        if ticket.type == "配送异常":
            risk_events.append(
                {
                    "id": f"ticket-{ticket.id}",
                    "level": "medium",
                    "level_label": _risk_level_label("medium"),
                    "business_type": "配送异常工单",
                    "type": "配送异常工单",
                    "title": f"工单 #{ticket.id}",
                    "description": ticket.description,
                    "created_at": _iso(ticket.created_at),
                    "related_orders": [
                        detail for detail in orders_detail if ticket.order_id and int(detail["order_id"]) == int(ticket.order_id)
                    ][:1],
                    "related_items": [],
                    "suggestion": "请关注工单是否已响应和关闭，超时未处理时应督促责任方。",
                }
            )
    risk_events.sort(key=lambda r: ({"high": 3, "medium": 2, "low": 1}.get(str(r.get("level")), 0), str(r.get("created_at") or "")), reverse=True)

    status_events = [
        {
            "id": f"status-{row.id}",
            "order_id": int(row.order_id),
            "title": f"{row.old_status} → {row.new_status}",
            "description": order_map.get(int(row.order_id)).order_no if int(row.order_id) in order_map else f"订单#{row.order_id}",
            "created_at": _iso(row.created_at),
        }
        for row in recent_status_logs[:20]
    ]

    summary = {
        "date": today.isoformat(),
        "today_orders": total_orders,
        "pending_trips": len([t for t in trips if t.status in {"待发车", "有阻塞"}]),
        "in_transit_trips": len([t for t in trips if t.status == "运输中"]),
        "arrived_orders": delivered_orders,
        "in_transit_orders": in_transit_orders,
        "blocked_allocations": blocked_allocations,
        "not_shipped": not_shipped_count,
        "not_sorted": not_scanned_count,
        "not_loaded": len(not_loaded_items),
        "risk_count": len(risk_events),
        "arrival_rate": _pct(delivered_orders, total_orders),
        "sort_rate": _pct(scanned_count, total_allocations),
        "ship_rate": _pct(len(shipped_alloc_ids), total_allocations),
    }

    return {
        "generated_at": now_cn.isoformat(),
        "timezone": "Asia/Shanghai",
        "date": today.isoformat(),
        "data_scope": f"expected_delivery_date={today.isoformat()} · planning_date={today.isoformat()}",
        "summary": summary,
        "funnel": funnel,
        "supplier_blocks": supplier_block_rows[:20],
        "orders_detail": orders_detail[:120],
        "allocations_detail": allocations_detail[:240],
        "trips": trip_cards[:80],
        "in_transit": in_transit_cards[:80],
        "risk_events": risk_events[:40],
        "status_events": status_events,
    }


@router.get("/neural/beijing-demo/vehicles")
async def monitor_neural_beijing_demo_vehicles(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """北京驾驶舱演示：全量车辆 id/车牌（仅监管端），用于地图模拟定位/轨迹。"""
    total = int(await db.scalar(select(func.count(DeliveryVehicle.id))) or 0)
    # 多列 select 须用 execute；scalars() 只取第一列，会得到 int 列表导致下面 r.vehicle_no 500
    result = await db.execute(
        select(DeliveryVehicle.id, DeliveryVehicle.vehicle_no).order_by(DeliveryVehicle.id)
    )
    rows = result.all()
    vehicles = [{"id": int(r.id), "vehicle_no": str(r.vehicle_no or "")} for r in rows]
    return {"total": total, "vehicles": vehicles}


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
            LIMIT 1200
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


@router.get("/neural/broadcast")
async def monitor_neural_broadcast(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    today = now.date()
    orders = (await db.scalars(select(Order).order_by(Order.id.desc()).limit(80))).all()
    alerts = (await db.scalars(select(Alert).order_by(Alert.id.desc()).limit(80))).all()
    deliveries = (await db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(80))).all()
    quality_reports = (
        await db.scalars(select(QualityReport).order_by(QualityReport.id.desc()).limit(80))
    ).all()
    tickets = (await db.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(80))).all()
    bills = (await db.scalars(select(Bill).order_by(Bill.id.desc()).limit(80))).all()
    related_order_ids: set[int] = {int(row.order_id) for row in tickets if row.order_id}
    related_order_ids.update(int(row.order_id) for row in bills if row.order_id)
    related_order_ids.update(int(row.order_id) for row in quality_reports if row.order_id)
    for alert in alerts:
        payload = alert.payload_json if isinstance(alert.payload_json, dict) else {}
        raw_order_id = payload.get("order_id")
        if str(raw_order_id or "").isdigit():
            related_order_ids.add(int(raw_order_id))
    known_order_ids = {int(row.id) for row in orders}
    missing_order_ids = related_order_ids - known_order_ids
    if missing_order_ids:
        extra_orders = (
            await db.scalars(select(Order).where(Order.id.in_(missing_order_ids)))
        ).all()
        orders = list(orders) + list(extra_orders)
    known_delivery_order_ids = {int(row.order_id) for row in deliveries}
    missing_delivery_order_ids = related_order_ids - known_delivery_order_ids
    if missing_delivery_order_ids:
        extra_deliveries = (
            await db.scalars(select(Delivery).where(Delivery.order_id.in_(missing_delivery_order_ids)))
        ).all()
        deliveries = list(deliveries) + list(extra_deliveries)
    users = (
        await db.scalars(
            select(User).where(User.role.in_(BUSINESS_BROADCAST_ROLES), User.status == "active")
        )
    ).all()
    canteens = (await db.scalars(select(ClientCanteen))).all()
    product_ids = [int(row.product_id) for row in quality_reports if row.product_id]
    products = (await db.scalars(select(Product).where(Product.id.in_(product_ids)))).all() if product_ids else []
    user_ids = {
        int(uid)
        for row in orders
        for uid in (row.client_id, row.delivery_id, row.supplier_id)
        if uid is not None
    }
    user_ids.update(int(row.supplier_id) for row in quality_reports if row.supplier_id)
    user_ids.update(int(row.created_by) for row in tickets if row.created_by)
    user_ids.update(int(user_row.id) for user_row in users)
    all_users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(row.id): row for row in all_users}
    canteen_map = {int(row.id): row for row in canteens}
    product_map = {int(row.id): row for row in products}
    order_map = {int(row.id): row for row in orders}
    delivery_by_order: dict[int, Delivery] = {}
    for delivery_row in deliveries:
        delivery_by_order[int(delivery_row.order_id)] = delivery_row
    statement_ids = {int(row.billing_statement_id) for row in tickets if getattr(row, "billing_statement_id", None)}
    statements = (
        await db.scalars(select(BillingStatement).where(BillingStatement.id.in_(statement_ids)))
    ).all() if statement_ids else []
    statement_map = {int(row.id): row for row in statements}
    broadcasts = await _broadcast_rows(db, limit=12)
    today_commands = len(
        [row for row in broadcasts if row.get("sent_at") and datetime.fromisoformat(row["sent_at"]).date() == today]
    )
    unread_receipts = sum(int(row.get("unread_count") or 0) for row in broadcasts)
    pending_alerts = len([row for row in alerts if row.status == "open"])

    def order_detail(row: Order) -> dict[str, Any]:
        client = user_map.get(int(row.client_id)) if row.client_id else None
        delivery = user_map.get(int(row.delivery_id)) if row.delivery_id else None
        canteen = canteen_map.get(int(row.canteen_id or 0))
        return {
            "id": int(row.id),
            "order_no": row.order_no,
            "status": row.status,
            "amount": round(_num(row.total_amount), 2),
            "client": client.company_name if client else "",
            "canteen": canteen.name if canteen else "",
            "delivery": delivery.company_name if delivery else "",
            "location": _safe_location(row.delivery_address),
            "updated_at": _iso(row.updated_at or row.created_at),
            "route": f"/monitor/orders?order_no={row.order_no}",
        }

    def alert_detail(row: Alert) -> dict[str, Any]:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        raw_order_id = payload.get("order_id")
        order = order_map.get(int(raw_order_id)) if str(raw_order_id or "").isdigit() else None
        if not order and payload.get("order_no"):
            order = next((item for item in orders if item.order_no == payload.get("order_no")), None)
        order_info = order_detail(order) if order else {}
        delivery_row = delivery_by_order.get(int(order.id)) if order else None
        return {
            "alert_no": f"AL{int(row.id):06d}",
            "alert_level": {"high": "高", "medium": "中", "low": "低"}.get(row.level, row.level),
            "alert_type": _alert_type_label(row.type),
            "order_no": order_info.get("order_no") or payload.get("order_no") or "",
            "client": order_info.get("client") or "",
            "canteen": order_info.get("canteen") or "",
            "delivery": order_info.get("delivery") or "",
            "driver": delivery_row.driver_name if delivery_row else "",
            "vehicle_no": delivery_row.vehicle_no if delivery_row else "",
            "order_status": order_info.get("status") or payload.get("status") or "",
            "expected_delivery": " ".join(
                [str(payload.get("expected_delivery_date") or ""), str(payload.get("expected_delivery_slot") or "")]
            ).strip(),
            "issue": _clean_alert_text(row.description),
            "created_at": _iso(row.created_at),
        }

    def quality_detail(row: QualityReport) -> dict[str, Any]:
        supplier = user_map.get(int(row.supplier_id)) if row.supplier_id else None
        product = product_map.get(int(row.product_id)) if row.product_id else None
        order = order_map.get(int(row.order_id)) if row.order_id else None
        order_info = order_detail(order) if order else {}
        return {
            "id": int(row.id),
            "report_no": row.report_no,
            "order_no": order_info.get("order_no") or (f"订单#{row.order_id}" if row.order_id else "—"),
            "supplier": supplier.company_name if supplier else "",
            "product": product.name if product else f"商品#{row.product_id}",
            "client": order_info.get("client") or "",
            "canteen": order_info.get("canteen") or "",
            "report_status": row.status,
            "created_at": _iso(row.created_at),
            "route": "/monitor/reports",
        }

    def bill_detail(row: Bill) -> dict[str, Any]:
        snap = row.order_snapshot_json if isinstance(row.order_snapshot_json, dict) else {}
        order = order_map.get(int(row.order_id)) if row.order_id else None
        order_info = order_detail(order) if order else {}
        return {
            "id": int(row.id),
            "role": _role_label(row.role),
            "bill_type": row.bill_type,
            "bill_status": row.status,
            "amount": round(_num(row.amount), 2),
            "order_no": order_info.get("order_no") or snap.get("order_no") or (f"订单#{row.order_id}" if row.order_id else "—"),
            "client": order_info.get("client") or "",
            "canteen": order_info.get("canteen") or "",
            "created_at": _iso(row.created_at),
            "route": "/monitor/reports",
        }

    def delivery_detail(row: Delivery) -> dict[str, Any]:
        order = next((item for item in orders if int(item.id) == int(row.order_id)), None)
        return {
            "id": int(row.id),
            "order_no": order.order_no if order else f"订单#{row.order_id}",
            "driver": row.driver_name,
            "vehicle_no": row.vehicle_no,
            "status": row.status,
            "departed_at": _iso(row.departed_at),
            "arrived_at": _iso(row.arrived_at),
            "route": "/monitor/logistics",
        }

    def _ticket_subtype(row: Ticket) -> str:
        desc = row.description or ""
        if desc.startswith("【质检缺失】"):
            return "质检缺失"
        if desc.startswith("【配送超时】"):
            return "配送超时"
        if desc.startswith("【合约范围异常】"):
            return "合约范围异常"
        return row.type

    def _user_display(user_id: Optional[int]) -> str:
        if not user_id:
            return ""
        u = user_map.get(int(user_id))
        return (u.company_name or u.username) if u else ""

    def _complaint_block(row: Ticket, order: Optional[Order]) -> dict[str, Any]:
        phase = complaint_phase(row)
        assigned_id = getattr(row, "assigned_delivery_id", None)
        assigned_name = _user_display(assigned_id) or (order_detail(order).get("delivery") if order else "")
        flow: list[dict[str, Any]] = []
        for entry in (getattr(row, "flow_logs_json", None) or []):
            if not isinstance(entry, dict):
                continue
            role = entry.get("role") or ""
            action = entry.get("action")
            note = entry.get("note") or ""
            if action == "auto_dispatch":
                note = f"已派发至 {assigned_name}" if assigned_name else "已自动派发承接配送商"
            flow.append(
                {
                    "action_label": FLOW_ACTION_LABELS.get(action, action or "处理"),
                    "role_label": FLOW_ROLE_LABELS.get(role, role or "系统"),
                    "actor_name": _user_display(entry.get("actor_user_id")),
                    "note": note,
                    "at": entry.get("at"),
                }
            )
        return {
            "reason": row.description,
            "phase": phase,
            "phase_label": COMPLAINT_PHASE_LABELS.get(phase, phase or ""),
            "images": [str(u).strip() for u in (getattr(row, "attachments_json", None) or []) if str(u).strip()],
            "assigned_delivery_name": assigned_name,
            "delivery_response": getattr(row, "delivery_response", None),
            "delivery_responded_at": _iso(getattr(row, "delivery_responded_at", None)),
            "operation_resolution": getattr(row, "operation_resolution", None),
            "operation_resolved_at": _iso(getattr(row, "operation_resolved_at", None)),
            "flow": flow,
        }

    def _billing_block(row: Ticket) -> dict[str, Any]:
        st = statement_map.get(int(row.billing_statement_id)) if getattr(row, "billing_statement_id", None) else None
        if not st:
            return {}
        snap = st.source_snapshot_json if isinstance(st.source_snapshot_json, dict) else {}
        return {
            "statement_no": st.statement_no,
            "amount": round(_num(st.amount), 2),
            "status": st.status,
            "direction": st.direction,
            "counterparty": snap.get("counterparty_name") or _user_display(st.counterparty_user_id),
        }

    def ticket_detail(row: Ticket) -> dict[str, Any]:
        order = order_map.get(int(row.order_id)) if row.order_id else None
        order_info = order_detail(order) if order else {}
        delivery_row = delivery_by_order.get(int(order.id)) if order else None
        detail: dict[str, Any] = {
            "id": int(row.id),
            "ticket_no": f"GD{int(row.id):06d}",
            "type": row.type,
            "subtype": _ticket_subtype(row),
            "process_status": row.status,
            "order_no": order_info.get("order_no") or (f"订单#{row.order_id}" if row.order_id else "—"),
            "order_status": order_info.get("status") or "",
            "client": order_info.get("client") or "",
            "canteen": order_info.get("canteen") or "",
            "delivery": order_info.get("delivery") or "",
            "driver": delivery_row.driver_name if delivery_row else "",
            "vehicle_no": delivery_row.vehicle_no if delivery_row else "",
            "amount": order_info.get("amount"),
            "location": order_info.get("location") or "",
            "issue": row.description,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "route": order_info.get("route") or "",
        }
        if row.type == "配送异常" and order is not None:
            slot = (order.expected_delivery_slot or "").strip()
            date_str = order.expected_delivery_date.isoformat() if order.expected_delivery_date else ""
            detail["expected_delivery"] = " ".join([date_str, slot]).strip()
            detail["departed_at"] = _iso(delivery_row.departed_at) if delivery_row else None
            detail["arrived_at"] = _iso(delivery_row.arrived_at) if delivery_row else None
        if row.type == "售后投诉":
            detail["complaint"] = _complaint_block(row, order)
        if getattr(row, "billing_statement_id", None):
            block = _billing_block(row)
            if block:
                detail["billing"] = block
        return detail

    order_items = [order_detail(row) for row in orders if row.status not in {"已结算", "取消"}]
    alert_items = [alert_detail(row) for row in sorted([item for item in alerts if item.status == "open"], key=lambda item: _severity_weight(item.level), reverse=True)]
    # 批次质检存证模型：质检「工单」= 已出库缺报告、需督促供货商补传的订单（非「待审核报告」）
    broadcast_alloc_rows = (
        await db.scalars(
            select(OrderItemAllocation).where(
                OrderItemAllocation.order_id.in_(list(order_map.keys()))
            )
        )
    ).all() if order_map else []
    quality_missing_order_ids: list[int] = []
    _seen_q: set[int] = set()
    for _a in (
        await period_quality_coverage(
            db, broadcast_alloc_rows, quality_reports, list(order_map.values()), shipped_only=True
        )
    )["missing_allocations"]:
        oid = int(_a.order_id)
        if oid in order_map and oid not in _seen_q:
            _seen_q.add(oid)
            quality_missing_order_ids.append(oid)
    quality_items = [order_detail(order_map[oid]) for oid in quality_missing_order_ids]
    bill_items = [bill_detail(row) for row in bills if row.status == "待结算"]
    delivery_items = [delivery_detail(row) for row in deliveries if row.status not in {"已送达", "已完成"}]
    role_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for user_row in users:
        role_groups[user_row.role].append(
            {
                "id": int(user_row.id),
                "role": user_row.role,
                "role_label": _role_label(user_row.role),
                "company_name": user_row.company_name,
                "username": user_row.username,
                "contact_phone": _mask_phone(user_row.contact_phone),
                "location": _safe_location(user_row.address),
            }
        )

    broadcast_ids = [int(row["id"]) for row in broadcasts]
    receipt_notifications = (
        await db.scalars(
            select(Notification).where(
                Notification.object_type == "monitor_broadcast",
                Notification.object_id.in_(broadcast_ids),
            )
        )
    ).all() if broadcast_ids else []
    broadcast_map = {int(row["id"]): row for row in broadcasts}
    receipt_user_ids = [int(row.target_user_id) for row in receipt_notifications if row.target_user_id]
    receipt_users = (await db.scalars(select(User).where(User.id.in_(receipt_user_ids)))).all() if receipt_user_ids else []
    receipt_user_map = {int(row.id): row for row in receipt_users}
    unread_receipt_items = []
    for row in receipt_notifications:
        if row.is_read:
            continue
        recipient = receipt_user_map.get(int(row.target_user_id))
        broadcast = broadcast_map.get(int(row.object_id), {})
        unread_receipt_items.append(
            {
                "broadcast_id": int(row.object_id),
                "title": broadcast.get("title") or row.title,
                "target_summary": broadcast.get("target_summary") or "",
                "role": _role_label(row.role),
                "company_name": recipient.company_name if recipient else "",
                "username": recipient.username if recipient else "",
                "sent_at": broadcast.get("sent_at") or _iso(row.created_at),
            }
        )

    today_command_items = [row for row in broadcasts if row.get("sent_at") and datetime.fromisoformat(row["sent_at"]).date() == today]
    target_group_items = [
        {
            "role": _role_label(role),
            "count": len(rows),
            "recent_targets": "、".join([item["company_name"] or item["username"] for item in rows[:4]]),
        }
        for role, rows in role_groups.items()
    ]

    kpi_details = {
        "today_commands": {"title": "今日指令", "items": today_command_items},
        "pending_alerts": {"title": "待处理预警", "items": alert_items},
        "unread_receipts": {"title": "未读回执", "items": unread_receipt_items},
        "active_terminals": {"title": "可达账号", "items": target_group_items},
    }

    channels = [
        {"key": "orders", "title": "订单链路", "count": len(order_items), "status": "live", "description": "未完结订单状态、分单和履约变更", "items": order_items[:40]},
        {"key": "risk", "title": "风险预警", "count": pending_alerts, "status": "warn" if pending_alerts else "steady", "description": "开放预警和高优先级异常", "items": alert_items[:40]},
        {"key": "quality", "title": "质检工单", "count": len(quality_items), "status": "review", "description": "已出库但缺质检报告、需督促供货商补传", "items": quality_items[:40]},
        {"key": "finance", "title": "账务结算", "count": len(bill_items), "status": "pending", "description": "客户、供应商、配送商待结算账单", "items": bill_items[:40]},
        {"key": "delivery", "title": "配送履约", "count": len(delivery_items), "status": "live", "description": "在途、待发车、异常配送链路", "items": delivery_items[:40]},
    ]

    event_flow: list[dict[str, Any]] = []
    for row in orders[:16]:
        detail = order_detail(row)
        event_flow.append({"id": f"order-{row.id}", "kind": "订单", "level": "normal", "title": f"订单 {row.order_no}", "description": f"状态：{row.status}，金额 ￥{_num(row.total_amount):,.2f}", "created_at": _iso(row.updated_at or row.created_at), "object_type": "order", "object_id": int(row.id), "route": detail["route"], "detail": detail})
    for row in alerts[:16]:
        if row.status == "open":
            detail = alert_detail(row)
            event_flow.append({"id": f"alert-{row.id}", "kind": "预警", "level": row.level or "medium", "title": detail.get("alert_type") or _alert_type_label(row.type), "description": f"{detail.get('order_no') or ''} {detail.get('client') or ''} {detail.get('delivery') or ''} {detail.get('issue') or _clean_alert_text(row.description)}".strip(), "created_at": _iso(row.created_at), "object_type": "alert", "object_id": int(row.id), "route": "", "detail": detail})
    for row in quality_reports[:12]:
        detail = quality_detail(row)
        event_flow.append({"id": f"quality-{row.id}", "kind": "质检", "level": "normal", "title": f"质检报告 {row.report_no}", "description": "供应商已上传质检报告并存证留痕", "created_at": _iso(row.created_at), "object_type": "quality_report", "object_id": int(row.id), "route": detail["route"], "detail": detail})
    for row in tickets[:12]:
        if row.status != "已关闭":
            detail = ticket_detail(row)
            event_flow.append({"id": f"ticket-{row.id}", "kind": row.type, "level": "high" if row.type == "配送异常" else "medium", "title": f"工单 #{row.id}", "description": row.description, "created_at": _iso(row.updated_at or row.created_at), "object_type": "ticket", "object_id": int(row.id), "route": "", "detail": detail})
    for row in bills[:12]:
        if row.status == "待结算":
            detail = bill_detail(row)
            event_flow.append({"id": f"bill-{row.id}", "kind": "账务", "level": "low", "title": f"{row.role} {row.bill_type}账单", "description": f"待结算 ￥{_num(row.amount):,.2f}", "created_at": _iso(row.created_at), "object_type": "bill", "object_id": int(row.id), "route": detail["route"], "detail": detail})
    event_flow.sort(key=lambda item: item.get("created_at") or "", reverse=True)

    return {
        "generated_at": now.isoformat(),
        "kpi": {"today_commands": today_commands, "pending_alerts": pending_alerts, "unread_receipts": unread_receipts, "active_terminals": len(users)},
        "kpi_details": kpi_details,
        "channels": channels,
        "event_flow": event_flow[:24],
        "broadcasts": broadcasts,
    }


@router.get("/broadcast/targets")
async def list_broadcast_targets(
    role: str = Query(default=""),
    q: str = Query(default=""),
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.status == "active", User.role.in_(BUSINESS_BROADCAST_ROLES))
    if role in BUSINESS_BROADCAST_ROLES:
        stmt = stmt.where(User.role == role)
    keyword = q.strip()
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(User.username.like(like), User.company_name.like(like), User.contact_phone.like(like)))
    rows = (await db.scalars(stmt.order_by(User.role.asc(), User.id.asc()).limit(120))).all()
    return [
        {
            "id": int(row.id),
            "username": row.username,
            "role": row.role,
            "role_label": _role_label(row.role),
            "company_name": row.company_name,
            "contact_phone": row.contact_phone,
            "label": f"{row.company_name or row.username} / {_role_label(row.role)} / {row.username}",
        }
        for row in rows
    ]


async def _resolve_broadcast_recipients(db: AsyncSession, payload: MonitorBroadcastIn) -> tuple[str, list[str], list[User]]:
    target_type = payload.target_type if payload.target_type in {"all", "roles", "users"} else "all"
    roles = [role for role in payload.roles if role in BUSINESS_BROADCAST_ROLES]
    stmt = select(User).where(User.status == "active", User.role.in_(BUSINESS_BROADCAST_ROLES))
    if target_type == "roles":
        if not roles:
            raise HTTPException(status_code=400, detail="请选择至少一个目标端")
        stmt = stmt.where(User.role.in_(roles))
    elif target_type == "users":
        ids = sorted({int(i) for i in payload.user_ids if int(i) > 0})
        if not ids:
            raise HTTPException(status_code=400, detail="请选择至少一个接收用户")
        stmt = stmt.where(User.id.in_(ids))
    recipients = (await db.scalars(stmt.order_by(User.role.asc(), User.id.asc()))).all()
    if not recipients:
        raise HTTPException(status_code=400, detail="当前目标范围没有可接收用户")
    return target_type, roles, recipients


@router.post("/broadcasts")
async def create_monitor_broadcast(
    payload: MonitorBroadcastIn,
    user=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="指令内容不能为空")
    title = payload.title.strip() or "监管指令"
    priority = _broadcast_priority(payload.priority)
    target_type, roles, recipients = await _resolve_broadcast_recipients(db, payload)
    broadcast = MonitorBroadcast(
        title=title,
        content=content,
        priority=priority,
        target_type=target_type,
        target_summary=_broadcast_target_summary(target_type, roles, recipients),
        sender_user_id=int(user.id),
        recipient_count=len(recipients),
        sent_at=datetime.utcnow(),
    )
    db.add(broadcast)
    await db.flush()

    notifications = [
        Notification(
            event_type="monitor_broadcast",
            title=f"[监管指令] {title}",
            content=content,
            role=recipient.role,
            target_user_id=int(recipient.id),
            object_type="monitor_broadcast",
            object_id=int(broadcast.id),
            route=_broadcast_route_for_role(recipient.role),
            is_read=False,
        )
        for recipient in recipients
    ]
    db.add_all(notifications)
    await db.commit()
    await db.refresh(broadcast)

    by_role: dict[str, list[int]] = defaultdict(list)
    for recipient in recipients:
        by_role[recipient.role].append(int(recipient.id))
    for role_name, user_ids in by_role.items():
        await ws_manager.broadcast_users(
            role_name,
            user_ids,
            {
                "type": "notification",
                "event_type": "monitor_broadcast",
                "title": f"[监管指令] {title}",
                "content": content,
                "route": _broadcast_route_for_role(role_name),
                "object_type": "monitor_broadcast",
                "object_id": int(broadcast.id),
                "target_user_ids": user_ids,
            },
        )

    return {"id": int(broadcast.id), "title": broadcast.title, "priority": broadcast.priority, "target_type": broadcast.target_type, "target_summary": broadcast.target_summary, "recipient_count": int(broadcast.recipient_count), "sent_at": _iso(broadcast.sent_at), "read_count": 0, "unread_count": int(broadcast.recipient_count), "read_rate": 0}


@router.get("/broadcasts")
async def list_monitor_broadcasts(
    limit: int = Query(default=30, ge=1, le=100),
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    return await _broadcast_rows(db, limit=limit)


@router.get("/broadcasts/{broadcast_id}/recipients")
async def list_monitor_broadcast_recipients(
    broadcast_id: int,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    broadcast = await db.get(MonitorBroadcast, broadcast_id)
    if not broadcast:
        raise HTTPException(status_code=404, detail="广播不存在")
    rows = (
        await db.scalars(
            select(Notification)
            .where(Notification.object_type == "monitor_broadcast", Notification.object_id == broadcast_id)
            .order_by(Notification.role.asc(), Notification.id.asc())
        )
    ).all()
    user_ids = [int(row.target_user_id) for row in rows if row.target_user_id]
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(user.id): user for user in users}
    return {
        "broadcast": {"id": int(broadcast.id), "title": broadcast.title, "content": broadcast.content, "priority": broadcast.priority, "target_summary": broadcast.target_summary, "sent_at": _iso(broadcast.sent_at), "recipient_count": int(broadcast.recipient_count)},
        "recipients": [
            {
                "notification_id": int(row.id),
                "user_id": int(row.target_user_id),
                "role": row.role,
                "role_label": _role_label(row.role),
                "username": user_map.get(int(row.target_user_id)).username if int(row.target_user_id) in user_map else "",
                "company_name": user_map.get(int(row.target_user_id)).company_name if int(row.target_user_id) in user_map else "",
                "is_read": bool(row.is_read),
                "read_at": _iso(row.read_at),
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ],
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
    page: int = 1,
    page_size: int = 50,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Alert).order_by(Alert.id.desc())
    if level:
        stmt = stmt.where(Alert.level == level)
    if status:
        stmt = stmt.where(Alert.status == status)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    page_size = max(1, min(page_size, 200))
    offset = (max(1, page) - 1) * page_size
    items = (await db.scalars(stmt.offset(offset).limit(page_size))).all()

    # 批量关联订单 → 配送商、食堂
    order_ids = list({
        int(a.payload_json["order_id"])
        for a in items
        if isinstance(a.payload_json, dict) and a.payload_json.get("order_id")
    })
    order_meta: dict[int, dict] = {}
    if order_ids:
        DeliveryUser = aliased(User)
        ClientUser = aliased(User)
        rows = (await db.execute(
            select(
                Order.id,
                DeliveryUser.company_name.label("delivery_name"),
                ClientUser.company_name.label("client_name"),
                ClientCanteen.name.label("canteen_name"),
            )
            .outerjoin(DeliveryUser, Order.delivery_id == DeliveryUser.id)
            .outerjoin(ClientUser, Order.client_id == ClientUser.id)
            .outerjoin(ClientCanteen, Order.canteen_id == ClientCanteen.id)
            .where(Order.id.in_(order_ids))
        )).all()
        order_meta = {
            r.id: {"delivery_name": r.delivery_name, "client_name": r.client_name, "canteen_name": r.canteen_name}
            for r in rows
        }

    def _serialize(a: Alert) -> dict:
        meta = order_meta.get(int((a.payload_json or {}).get("order_id", 0) or 0), {})
        return {
            "id": a.id,
            "level": a.level,
            "level_label": ALERT_LEVEL_LABELS.get(a.level, a.level),
            "type": a.type,
            "type_label": _alert_type_label(a.type),
            "description": _clean_alert_text(a.description),
            "status": a.status,
            "status_label": ALERT_STATUS_LABELS.get(a.status, a.status),
            "facts": _alert_facts(a.payload_json),
            "payload_json": a.payload_json,
            "created_at": a.created_at,
            "delivery_name": meta.get("delivery_name"),
            "client_name": meta.get("client_name"),
            "canteen_name": meta.get("canteen_name"),
        }

    return {"total": total, "page": page, "page_size": page_size, "items": [_serialize(a) for a in items]}


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


class MonitorFleetHistoryTrackIn(BaseModel):
    start_time: int
    end_time: int
    force_demo: bool = False


@router.get("/dispatch-trips/{trip_id}")
async def monitor_dispatch_trip_detail(
    trip_id: int,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    trip = await db.get(DeliveryDispatchTrip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="车次不存在")
    return await _load_trip_payload(db, trip)


@router.get("/fleet-monitor/vehicles")
async def monitor_fleet_monitor_vehicles(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    return await build_fleet_monitor_vehicles(db)


@router.get("/fleet-monitor/warehouses")
async def monitor_fleet_monitor_warehouses(
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    return await build_fleet_monitor_warehouses(db)


@router.get("/fleet-monitor/cameras/{device_id}/live-url")
async def monitor_fleet_monitor_camera_live_url(
    device_id: int,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    row = await load_camera_device_or_404(db, device_id)
    return await build_camera_live_url_payload(row)


@router.post("/fleet-monitor/cameras/{device_id}/camera-ptz")
async def monitor_fleet_monitor_camera_ptz(
    device_id: int,
    body: CameraPtzIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    row = await load_camera_device_or_404(db, device_id)
    return await control_ys7_camera_ptz(
        row, action=body.action, direction=body.direction, speed=body.speed
    )


@router.post("/fleet-monitor/vehicles/{vehicle_id}/beidou-history-track")
async def monitor_fleet_monitor_vehicle_history_track(
    vehicle_id: int,
    body: MonitorFleetHistoryTrackIn,
    _=Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    dev = await load_vehicle_beidou_device_or_404(db, vehicle_id)
    return await build_beidou_history_track_payload(
        dev,
        start_time=body.start_time,
        end_time=body.end_time,
        force_demo=body.force_demo,
    )
