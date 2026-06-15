"""订单详情聚合（运营 / 客户端 / 配送商同口径字段）。

供 operation_order_detail 与 GET /orders/{id}（client/delivery）共用。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.beidou_client import (
    beidou_location_for_amap,
    beidou_online_status_from_raw,
    beidou_reported_at_display,
    enrich_beidou_devices_live,
)
from models import (
    AuditLog,
    Category,
    ClientCanteen,
    Contract,
    Delivery,
    DeliveryDevice,
    DeliveryDispatchStop,
    DeliveryDispatchTrip,
    DeliveryVehicleDeviceBinding,
    Order,
    OrderItemAllocation,
    OrderItemStatusLog,
    OrderReceivingLine,
    OrderReturn,
    OrderReturnLine,
    OrderStatusLog,
    Product,
    QualityReport,
    SortRecord,
    Ticket,
    User,
)
from services.delivery_workflow import compute_delivery_stage, delivery_stage_aggregates
from services.order_quality_missing import missing_quality_allocations
from services.receiving_billing import build_receiving_billing_snapshot
from services.periodic_quality_reports import (
    approved_periodic_report_map,
    periodic_report_payload,
    quality_cover_date_for_order,
)
from services.storage.minio_client import normalize_public_image_url, normalize_public_image_urls
from services.quality_report_attachments import file_urls_from_row
from services.ticket_service import complaint_ticket_public_dict

ORDER_STATUS_FLOW = ["下单", "配货", "发货", "收货", "收货确认", "已结算"]

ROLE_LABELS = {
    "client": "客户",
    "delivery": "配送商",
    "supplier": "供货商",
    "factory": "厂家",
    "operation": "运营",
    "monitor": "监管",
}

STATUS_ACTION_TITLES = {
    "下单": "提交订单",
    "配货": "确认分单/进入配货",
    "发货": "配送商取货配送",
    "收货": "配送商已送达",
    "收货确认": "客户确认收货",
    "已结算": "完成结算",
    "取消": "取消订单",
}

AUDIT_ACTION_TITLES = {
    "supplier_print_order_label": "整单分拣完成",
    "supplier_print_allocation_label": "打印分单标签",
    "order_receiving_draft": "记录称重草稿",
    "order_receiving_confirm_line": "确认称重行",
    "order_receiving_reopen_line": "撤销称重确认",
    "order_receiving_lock_photo": "上传称重留痕",
    "bill_create_on_receive": "生成账单",
    "bill_settle": "完成账单结算",
    "quality_missing_marked": "质检异常标记",
    "quality_missing_cleared": "质检异常解除",
    "order_pickup_confirm": "配送商确认取货",
    "delivery_overdue_detected": "配送超时预警",
    "driver_stop_deliver": "司机确认送达",
    "order_receiving_return_photo": "上传少收/退货证据照片",
    "order_receiving_signature_photo": "上传收货签字照片",
}

RECEIVING_REASON_LABELS = {
    "lack": "缺货",
    "quality": "质量问题",
    "other": "其他",
}

RETURN_STATUS_LABELS = {
    "pending_delivery_review": "待配送商审核",
    "confirmed": "已确认",
    "rejected": "已驳回",
    "draft": "草稿",
    "cancelled": "已取消",
}

CLIENT_TIMELINE_EVENT_TYPES = {"order_status", "audit"}
CLIENT_TIMELINE_AUDIT_ACTIONS = {
    "order_receiving_confirm_line",
    "order_receiving_return_photo",
    "order_receiving_signature_photo",
    "driver_stop_deliver",
    "bill_create_on_receive",
    "bill_settle",
    "order_pickup_confirm",
}


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _to_float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _device_location(raw_payload: dict[str, Any], vendor: str) -> tuple[Optional[float], Optional[float]]:
    raw = _as_dict(raw_payload)
    if str(vendor or "").lower() == "beidou":
        lng, lat, _stale = beidou_location_for_amap(raw)
        return lng, lat
    camera = _as_dict(raw.get("camera"))
    device = _as_dict(raw.get("device"))
    lng = (
        _to_float_or_none(camera.get("longitude"))
        or _to_float_or_none(device.get("longitude"))
        or _to_float_or_none(camera.get("lng"))
        or _to_float_or_none(device.get("lng"))
    )
    lat = (
        _to_float_or_none(camera.get("latitude"))
        or _to_float_or_none(device.get("latitude"))
        or _to_float_or_none(camera.get("lat"))
        or _to_float_or_none(device.get("lat"))
    )
    return lng, lat


def _device_online_status(raw_payload: dict[str, Any], vendor: str) -> str:
    raw = _as_dict(raw_payload)
    vendor = str(vendor or "").lower()
    explicit_keys = ("online", "is_online", "isOnline", "onlineStatus", "status")
    if vendor != "beidou":
        for src in (_as_dict(raw.get("camera")), _as_dict(raw.get("device")), raw):
            for key in explicit_keys:
                val = src.get(key)
                if val is None:
                    continue
                text = str(val).strip().lower()
                if text in {"1", "true", "online", "on"}:
                    return "online"
                if text in {"0", "false", "offline", "off"}:
                    return "offline"
        return "offline"
    return beidou_online_status_from_raw(raw)


def _join_names(names: list[str]) -> str:
    uniq = [name for idx, name in enumerate(names) if name and name not in names[:idx]]
    if not uniq:
        return ""
    if len(uniq) <= 3:
        return "、".join(uniq)
    return "、".join(uniq[:3]) + f"等 {len(uniq)} 家"


def user_brief(user: Optional[User]) -> dict:
    if not user:
        return {}
    return {
        "id": int(user.id),
        "username": user.username,
        "company_name": user.company_name,
        "contact_phone": user.contact_phone,
        "address": user.address,
        "lng": float(user.lng) if user.lng is not None else None,
        "lat": float(user.lat) if user.lat is not None else None,
        "role": user.role,
    }


def _actor_brief(actor_user_id: int, users: dict[int, User]) -> dict:
    uid = int(actor_user_id or 0)
    user = users.get(uid)
    if not user:
        return {
            "actor_user_id": uid,
            "actor_name": "系统自动记录" if uid == 0 else f"用户 #{uid}",
            "actor_role": "system" if uid == 0 else "",
            "actor_role_label": "系统" if uid == 0 else "",
        }
    return {
        "actor_user_id": uid,
        "actor_name": user.company_name or user.username or f"用户 #{uid}",
        "actor_role": user.role,
        "actor_role_label": ROLE_LABELS.get(str(user.role), str(user.role or "")),
    }


def _status_description(old_status: str, new_status: str) -> str:
    if old_status and old_status not in {"N/A", "None"}:
        return f"订单状态由「{old_status}」流转为「{new_status}」。"
    if new_status == "下单":
        return "客户提交订单，订单进入履约流程。"
    return f"订单进入「{new_status}」状态。"


def calc_order_float_rate(
    order: Order,
    *,
    product_ref_by_id: Optional[dict[int, float]] = None,
) -> Optional[float]:
    """实付相对指导价：实际成交额/指导价基准额−1（用于 order_realized_float_rate；指导价优先快照，否则商品表，再否则由成交价与快照品类上浮反推）。"""
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    if not items:
        return None
    ref_map = product_ref_by_id or {}
    reference_total = 0.0
    actual_total = 0.0
    for idx, item in enumerate(items):
        snap = snaps[idx] if idx < len(snaps) and isinstance(snaps[idx], dict) else {}
        pid = int((item or {}).get("product_id") or snap.get("product_id") or 0)
        qty = float((item or {}).get("quantity") or snap.get("order_quantity") or 0)
        actual_unit_price = float((item or {}).get("unit_price") or snap.get("order_unit_price") or 0)
        raw_rate = (snap or {}).get("category_float_rate")
        has_rate = raw_rate is not None
        try:
            r = float(raw_rate) if has_rate else 0.0
        except (TypeError, ValueError):
            has_rate, r = False, 0.0
        if has_rate and r > -0.999999 and actual_unit_price > 0:
            # 与下单计价一致：用成交价÷(1+品类上浮)，避免快照 reference_price 四舍五入导致整单偏差（如 22% 显示成 21.99%）
            reference_unit = actual_unit_price / (1.0 + r)
        else:
            # 快照缺 category_float_rate 时不可当成 0% 上浮（否则实付较指导价恒为 0），回退用指导价
            reference_unit = float((snap or {}).get("reference_price") or 0)
            if reference_unit <= 0 and pid in ref_map:
                reference_unit = float(ref_map[pid])
        if qty <= 0:
            continue
        actual_total += qty * actual_unit_price
        reference_total += qty * reference_unit
    if reference_total <= 0:
        return None
    return round(actual_total / reference_total - 1, 6)


def _contract_category_rate_map(contract: Contract) -> tuple[dict[int, float], float]:
    """与下单侧一致：品类 id -> 上浮率；fallback 为合约整单上浮率。"""
    rate_map: dict[int, float] = {}
    for i in contract.category_rates_json or []:
        if i.get("category_id") is not None:
            try:
                rate_map[int(i["category_id"])] = float(i.get("float_rate", 0))
            except (TypeError, ValueError):
                continue
    return rate_map, float(contract.price_float_rate or 0)


def amount_weighted_contract_float_rate(
    order: Order,
    rate_map: dict[int, float],
    fallback_rate: float,
    product_meta_map: Optional[dict[int, dict]] = None,
) -> Optional[float]:
    """本单综合上浮：Σ(指导价金额×该行一级品类在合约中的上浮率)/Σ指导价金额。"""
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    if not items:
        return None
    meta = product_meta_map or {}
    reference_total = 0.0
    weighted = 0.0
    for idx, item in enumerate(items):
        snap = snaps[idx] if idx < len(snaps) and isinstance(snaps[idx], dict) else {}
        pid = int((item or {}).get("product_id") or snap.get("product_id") or 0)
        qty = float((item or {}).get("quantity") or snap.get("order_quantity") or 0)
        raw_up = (item or {}).get("unit_price")
        if raw_up is None or raw_up == "":
            raw_up = snap.get("order_unit_price", 0)
        try:
            up = float(raw_up or 0)
        except (TypeError, ValueError):
            up = 0.0
        snapshot_rate = float((snap or {}).get("category_float_rate") or 0)
        if snapshot_rate > -0.999999 and up > 0:
            reference_unit = up / (1.0 + snapshot_rate)
        else:
            reference_unit = float((snap or {}).get("reference_price") or 0)
            if reference_unit <= 0 and pid in meta:
                reference_unit = float((meta.get(pid) or {}).get("reference_price") or 0)
        reference_amt = qty * reference_unit
        c1 = snap.get("category1_id")
        if c1 is None and pid in meta:
            c1 = (meta.get(pid) or {}).get("category1_id")
        try:
            cid = int(c1) if c1 is not None else None
        except (TypeError, ValueError):
            cid = None
        r = float(rate_map.get(int(cid), fallback_rate)) if cid is not None else float(fallback_rate)
        if reference_amt <= 0:
            continue
        weighted += reference_amt * r
        reference_total += reference_amt
    if reference_total <= 0:
        return None
    return round(weighted / reference_total, 6)


def _point_payload(
    *,
    point_type: str,
    label: str,
    lng: Optional[float],
    lat: Optional[float],
    address: str = "",
) -> Optional[dict]:
    if lng is None or lat is None:
        return None
    return {
        "type": point_type,
        "label": label,
        "lng": float(lng),
        "lat": float(lat),
        "address": address,
    }


def _customer_point(order: Order, canteen: Optional[ClientCanteen], client: Optional[User]) -> tuple[Optional[float], Optional[float], str, str]:
    if order.delivery_lng is not None and order.delivery_lat is not None:
        return (
            float(order.delivery_lng),
            float(order.delivery_lat),
            (canteen.name if canteen else "") or "客户收货点",
            order.delivery_address or (canteen.address if canteen else "") or "",
        )
    if canteen and canteen.lng is not None and canteen.lat is not None:
        return (
            float(canteen.lng),
            float(canteen.lat),
            canteen.name or "客户收货点",
            canteen.address or order.delivery_address or "",
        )
    if client and client.lng is not None and client.lat is not None:
        return (
            float(client.lng),
            float(client.lat),
            client.company_name or client.username or "客户收货点",
            order.delivery_address or client.address or "",
        )
    return None, None, (canteen.name if canteen else "") or "客户收货点", order.delivery_address or (canteen.address if canteen else "") or ""


def _customer_stage_label(status: str, stage: dict) -> str:
    s = str(status or "")
    code = str(stage.get("code") or "")
    if s == "下单":
        return "商家已接单"
    if code == "await_split":
        return "配送商配货中"
    if code == "await_ship":
        return "等待供货商出库"
    if code == "await_sort":
        return "等待分检完成"
    if code == "await_pickup":
        return "待发车"
    if code == "delivering":
        return "配送中"
    if code == "await_receive":
        return "已送达"
    if code == "await_settle":
        return "已确认收货"
    if code == "done":
        return "已完成结算"
    if code == "cancelled":
        return "订单已取消"
    return stage.get("label") or s or "履约中"


def _client_actor_label(role: str) -> str:
    return {
        "client": "客户",
        "delivery": "配送商",
        "operation": "运营",
        "monitor": "监管",
        "system": "系统",
    }.get(str(role or ""), "系统")


def _receiving_reason_label(code: Any) -> str:
    return RECEIVING_REASON_LABELS.get(str(code or "").strip(), str(code or "").strip() or "—")


def _return_status_label(status: Any) -> str:
    return RETURN_STATUS_LABELS.get(str(status or "").strip(), str(status or "").strip() or "—")


def _fmt_kg(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _fmt_amount(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _amount_text(value: Optional[float], unit: str, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    n = float(value)
    prefix = "+" if signed and n > 0 else ""
    return f"{prefix}{_fmt_amount(n)} {unit or 'kg'}"


def _receiving_line_payload(
    line: OrderReceivingLine,
    billing_by_line: dict[int, dict[str, Any]],
    item_by_line: Optional[dict[int, dict[str, Any]]] = None,
) -> dict[str, Any]:
    idx = int(line.line_index)
    billing = billing_by_line.get(idx) or {}
    item = (item_by_line or {}).get(idx) or {}
    unit = str(billing.get("measure_unit") or item.get("unit") or "kg")
    is_standard = bool(billing.get("is_standard"))
    ordered_kg = _to_float_or_none(billing.get("ordered_kg"))
    if ordered_kg is None:
        ordered_kg = _to_float_or_none(line.shortage_ordered_kg)
    received_kg = _to_float_or_none(line.confirmed_quantity if is_standard else line.confirmed_kg)
    if received_kg is None:
        received_kg = _to_float_or_none(billing.get("received_kg"))
    diff_signed = None
    if ordered_kg is not None and received_kg is not None:
        diff_signed = round(received_kg - ordered_kg, 3)
    elif line.shortage_delta_kg is not None:
        diff_signed = -abs(float(line.shortage_delta_kg))
    if diff_signed is None or abs(diff_signed) < 0.0005:
        diff_type = "normal"
        diff_label = _amount_text(0, unit)
        diff_signed = 0.0 if diff_signed is not None else None
    elif diff_signed < 0:
        diff_type = "shortage"
        diff_label = _amount_text(diff_signed, unit)
    else:
        diff_type = "overage"
        diff_label = _amount_text(diff_signed, unit, signed=True)
    return {
        "line_index": idx,
        "product_name": item.get("product_name") or "",
        "spec": item.get("spec") or "",
        "unit": item.get("unit") or "",
        "is_standard": is_standard,
        "measure_unit": unit,
        "status": str(line.status),
        "draft_kg": float(line.draft_kg) if line.draft_kg is not None else None,
        "confirmed_kg": float(line.confirmed_kg) if line.confirmed_kg is not None else None,
        "confirmed_quantity": float(line.confirmed_quantity) if line.confirmed_quantity is not None else None,
        "confirmed_unit": line.confirmed_unit,
        "sample_kg": float(line.sample_kg) if line.sample_kg is not None else None,
        "received_kg": received_kg,
        "ordered_kg": ordered_kg,
        "ordered_qty": ordered_kg,
        "received_qty": received_kg,
        "ordered_text": _amount_text(ordered_kg, unit),
        "received_text": _amount_text(received_kg, unit),
        "diff_kg_signed": diff_signed,
        "diff_type": diff_type,
        "diff_label": diff_label,
        "confirmed_at": line.confirmed_at.isoformat() if line.confirmed_at else None,
        "shortage_reason_code": line.shortage_reason_code,
        "reason_label": _receiving_reason_label(line.shortage_reason_code),
        "shortage_reason_detail": line.shortage_reason_detail,
        "shortage_ordered_kg": float(line.shortage_ordered_kg) if line.shortage_ordered_kg is not None else ordered_kg,
        "shortage_delta_kg": float(line.shortage_delta_kg) if line.shortage_delta_kg is not None else None,
        "return_photo_urls": normalize_public_image_urls(line.return_photo_urls_json or []),
        "return_note": line.return_note,
        "lock_photo_url": normalize_public_image_url(line.lock_photo_url),
        "lock_photo_taken_at": line.lock_photo_taken_at.isoformat() if line.lock_photo_taken_at else None,
        "lock_photo_device_id": line.lock_photo_device_id,
    }


def _return_line_payload(line: OrderReturnLine) -> dict[str, Any]:
    delta = float(line.delta_kg)
    return {
        "line_index": int(line.line_index),
        "product_id": int(line.product_id) if line.product_id is not None else None,
        "product_name": line.product_name,
        "ordered_kg": float(line.ordered_kg),
        "received_kg": float(line.received_kg),
        "delta_kg": delta,
        "diff_kg_signed": -abs(delta) if delta else 0.0,
        "diff_type": "shortage" if delta else "normal",
        "diff_label": f"-{_fmt_kg(abs(delta))} kg" if delta else "0 kg",
        "reason_code": line.reason_code,
        "reason_label": _receiving_reason_label(line.reason_code),
        "reason_detail": line.reason_detail,
        "photo_urls": normalize_public_image_urls(line.photo_urls_json or []),
        "deduction_amount": float(line.deduction_amount) if line.deduction_amount is not None else None,
    }


def _audit_action_title(action: Any) -> str:
    return AUDIT_ACTION_TITLES.get(str(action or ""), "流程留痕")


def _audit_description(action: Any, detail: Any) -> str:
    text = str(detail or "").strip()
    text = (
        text.replace("role=warehouse", "签字方：食堂签收人")
        .replace("role=carrier", "签字方：送货方")
        .replace("order_status", "订单状态")
        .replace("quality_missing", "质检缺失")
        .replace("receive_shortage", "收货少收")
    )
    action_key = str(action or "")
    if action_key == "order_receiving_signature_photo":
        if "warehouse" in text:
            return "上传食堂签收人签字照片"
        if "carrier" in text:
            return "上传送货方签字照片"
        return "上传收货签字照片"
    if action_key == "order_receiving_return_photo":
        return "上传少收/退货证据照片"
    if action_key == "driver_stop_deliver":
        return text or "司机端确认货品已送达客户收货点。"
    return text or _audit_action_title(action_key)


def _sanitize_client_timeline(events: list[dict]) -> list[dict]:
    safe: list[dict] = []
    for ev in events:
        et = str(ev.get("event_type") or "")
        if et not in CLIENT_TIMELINE_EVENT_TYPES:
            continue
        action = str(ev.get("action") or "")
        if et == "audit" and action not in CLIENT_TIMELINE_AUDIT_ACTIONS:
            continue
        role = str(ev.get("actor_role") or "")
        if role in {"supplier", "factory"}:
            role = "delivery"
        item = {
            "event_type": et,
            "from_status": ev.get("from_status") or "",
            "to_status": ev.get("to_status") or "",
            "actor_role": role or "system",
            "actor_role_label": _client_actor_label(role or "system"),
            "actor_name": _client_actor_label(role or "system"),
            "action_title": ev.get("action_title") or ev.get("to_status") or "流程记录",
            "description": ev.get("description") or "",
            "created_at": ev.get("created_at"),
        }
        if et == "audit":
            if action == "order_receiving_confirm_line":
                item["action_title"] = "收货称重已记录"
                item["description"] = "收货端已记录称重或到货留痕。"
            elif action == "bill_create_on_receive":
                item["action_title"] = "账单已生成"
                item["description"] = "系统已根据收货结果生成账单。"
            elif action == "bill_settle":
                item["action_title"] = "账单已结算"
                item["description"] = "订单相关账单已完成结算。"
            elif action == "order_pickup_confirm":
                item["action_title"] = "配送商已取货"
                item["description"] = "配送商已完成取货，订单进入配送阶段。"
            elif action == "order_receiving_return_photo":
                item["action_title"] = "上传少收/退货证据照片"
                item["description"] = "收货方已上传少收或退货现场照片。"
            elif action == "order_receiving_signature_photo":
                item["action_title"] = "上传收货签字照片"
                item["description"] = _audit_description(action, ev.get("description"))
            elif action == "driver_stop_deliver":
                item["action_title"] = "司机确认送达"
                item["description"] = "司机端已确认货品送达客户收货点。"
        safe.append(item)
    return safe


def _collapse_repeated_timeline_events(events: list[dict]) -> list[dict]:
    collapsed: list[dict] = []
    overdue_groups: dict[str, dict] = {}
    for ev in events:
        if ev.get("event_type") != "audit" or ev.get("action") != "delivery_overdue_detected":
            collapsed.append(ev)
            continue
        detail_key = str(ev.get("description") or ev.get("action_title") or "")
        group = overdue_groups.setdefault(
            detail_key,
            {
                **ev,
                "_count": 0,
                "_first_at": ev.get("created_at"),
                "_last_at": ev.get("created_at"),
            },
        )
        group["_count"] += 1
        group["_last_at"] = ev.get("created_at") or group.get("_last_at")
        group["created_at"] = group.get("_last_at")
    for ev in overdue_groups.values():
        count = int(ev.pop("_count", 1) or 1)
        first_at = ev.pop("_first_at", None)
        last_at = ev.pop("_last_at", None)
        if count > 1:
            ev["description"] = f"{ev.get('description') or '订单存在配送超时风险'}（系统已累计检测 {count} 次，首次 {first_at or '-'}，最近 {last_at or '-'}）"
        collapsed.append(ev)
    collapsed.sort(key=lambda x: x.get("created_at") or "")
    return collapsed


async def _build_logistics_tracking(
    db: AsyncSession,
    order: Order,
    *,
    delivery_user: Optional[User],
    client_user: Optional[User],
    canteen: Optional[ClientCanteen],
    delivery_record: Optional[Delivery],
) -> dict:
    agg = (await delivery_stage_aggregates(db, [int(order.id)])).get(int(order.id), {})
    stage = compute_delivery_stage(
        str(order.status),
        int(agg.get("alloc_total", 0)),
        int(agg.get("alloc_shipped", 0)),
        bool(agg.get("all_shipped", False)),
        bool(agg.get("sort_all_done", True)),
    )
    customer_lng, customer_lat, customer_label, customer_addr = _customer_point(order, canteen, client_user)
    points: list[dict] = []
    delivery_point = _point_payload(
        point_type="delivery_origin",
        label=(delivery_user.company_name or delivery_user.username or "配送商") if delivery_user else "配送商",
        lng=float(delivery_user.lng) if delivery_user and delivery_user.lng is not None else None,
        lat=float(delivery_user.lat) if delivery_user and delivery_user.lat is not None else None,
        address=(delivery_user.address if delivery_user else "") or "",
    )
    customer_point = _point_payload(
        point_type="customer_destination",
        label=customer_label,
        lng=customer_lng,
        lat=customer_lat,
        address=customer_addr,
    )
    if delivery_point:
        points.append(delivery_point)
    if customer_point:
        points.append(customer_point)

    dispatch_row = (
        await db.execute(
            select(DeliveryDispatchTrip, DeliveryDispatchStop)
            .join(DeliveryDispatchStop, DeliveryDispatchStop.trip_id == DeliveryDispatchTrip.id)
            .where(
                DeliveryDispatchStop.order_id == int(order.id),
                DeliveryDispatchTrip.status.in_(["待发车", "有阻塞", "运输中", "已完成"]),
            )
            .order_by(DeliveryDispatchTrip.id.desc())
            .limit(1)
        )
    ).first()
    dispatch_trip = dispatch_row[0] if dispatch_row else None
    route_no = dispatch_trip.route_no if dispatch_trip else ""
    vehicle = {
        "vehicle_no": (dispatch_trip.vehicle_no if dispatch_trip else "") or (delivery_record.vehicle_no if delivery_record else ""),
        "driver_name": (dispatch_trip.driver_name if dispatch_trip else "") or (delivery_record.driver_name if delivery_record else ""),
        "source": "",
        "online_status": "",
        "reported_at": "",
        "speed": None,
        "course": "",
    }

    vehicle_point = None
    if dispatch_trip and dispatch_trip.vehicle_id is not None:
        devices = (
            await db.scalars(
                select(DeliveryDevice)
                .join(DeliveryVehicleDeviceBinding, DeliveryVehicleDeviceBinding.device_id == DeliveryDevice.id)
                .where(
                    DeliveryVehicleDeviceBinding.vehicle_id == int(dispatch_trip.vehicle_id),
                    DeliveryVehicleDeviceBinding.delivery_id == int(order.delivery_id),
                )
                .order_by(DeliveryDevice.id.asc())
            )
        ).all()
        sorted_devices = sorted(devices, key=lambda d: (0 if str(d.vendor) == "beidou" else 1, int(d.id)))
        if sorted_devices:
            await enrich_beidou_devices_live(list(sorted_devices), db=db, persist=False)
        for device in sorted_devices:
            raw = device.raw_payload_json if isinstance(device.raw_payload_json, dict) else {}
            lng, lat = _device_location(raw, str(device.vendor))
            if lng is None or lat is None:
                continue
            vendor = str(device.vendor or "").lower()
            vehicle.update(
                {
                    "source": str(device.vendor or ""),
                    "online_status": _device_online_status(raw, vendor),
                    "reported_at": beidou_reported_at_display(raw)
                    if vendor == "beidou"
                    else str(raw.get("reported_at") or raw.get("updatetime") or ""),
                    "speed": raw.get("speed"),
                    "course": raw.get("course") or raw.get("direction") or "",
                }
            )
            vehicle_point = _point_payload(
                point_type="vehicle",
                label=vehicle["vehicle_no"] or "配送车辆",
                lng=lng,
                lat=lat,
                address="北斗实时位置" if str(device.vendor) == "beidou" else "设备上报位置",
            )
            break
    if vehicle_point is None and delivery_record and delivery_record.current_lng is not None and delivery_record.current_lat is not None:
        vehicle.update({"source": "delivery_record"})
        vehicle_point = _point_payload(
            point_type="vehicle",
            label=vehicle["vehicle_no"] or "配送车辆",
            lng=float(delivery_record.current_lng),
            lat=float(delivery_record.current_lat),
            address="配送记录位置",
        )
    status_label = _customer_stage_label(str(order.status), stage)
    status_hint = stage.get("hint") or ""
    if str(order.status) == "发货":
        mode = "in_transit"
        status_label = "配送中"
        status_hint = "配送车辆正在前往客户收货点。"
        map_center = vehicle_point or customer_point or delivery_point
        points = [p for p in [delivery_point, vehicle_point, customer_point] if p]
    elif str(order.status) in {"收货", "收货确认", "已结算"}:
        mode = "arrived"
        status_label = "已送达"
        status_hint = "货品已送达客户收货点。"
        map_center = customer_point or delivery_point
        points = [p for p in [delivery_point, customer_point] if p]
    elif str(order.status) == "取消":
        mode = "unavailable"
        map_center = delivery_point or customer_point
        points = [p for p in [delivery_point, customer_point] if p]
    else:
        mode = "pre_departure"
        status_label = status_label or "配送商备货中"
        map_center = delivery_point or customer_point
        points = [p for p in [delivery_point, customer_point] if p]

    if mode == "in_transit" and not vehicle_point:
        status_hint = "车辆已发车，当前暂无北斗实时坐标，可查看车牌与司机信息。"

    return {
        "mode": mode,
        "status_label": status_label,
        "status_hint": status_hint,
        "map_center": map_center,
        "vehicle": vehicle,
        "delivery": {
            "departed_at": delivery_record.departed_at.isoformat() if delivery_record and delivery_record.departed_at else (dispatch_trip.departed_at.isoformat() if dispatch_trip and dispatch_trip.departed_at else None),
            "arrived_at": delivery_record.arrived_at.isoformat() if delivery_record and delivery_record.arrived_at else None,
            "route_no": route_no,
        },
        "points": points,
    }


async def build_order_logistics_tracking(
    db: AsyncSession,
    order: Order,
    *,
    viewer_role: Optional[str] = None,
    viewer_user_id: Optional[int] = None,
) -> dict:
    """返回订单物流地图卡片所需的轻量追踪数据。"""
    user_ids: set[int] = {int(order.client_id), int(order.delivery_id)}
    users = (await db.scalars(select(User).where(User.id.in_(list(user_ids))))).all()
    user_map = {int(u.id): u for u in users}
    canteen = None
    if order.canteen_id is not None:
        canteen = await db.scalar(select(ClientCanteen).where(ClientCanteen.id == int(order.canteen_id)))
    delivery_record = await db.scalar(
        select(Delivery).where(Delivery.order_id == order.id).order_by(Delivery.id.desc())
    )
    return await _build_logistics_tracking(
        db,
        order,
        delivery_user=user_map.get(int(order.delivery_id)),
        client_user=user_map.get(int(order.client_id)),
        canteen=canteen,
        delivery_record=delivery_record,
    )


async def _signed_contract_for_order_on_date(
    db: AsyncSession, client_id: int, delivery_id: int, on_date: date
) -> Optional[Contract]:
    return await db.scalar(
        select(Contract)
        .where(
            Contract.client_id == client_id,
            Contract.delivery_id == delivery_id,
            Contract.status == "已中标",
            Contract.period_start <= on_date,
            Contract.period_end >= on_date,
        )
        .order_by(Contract.id.desc())
    )


async def build_order_detail_extensions(
    db: AsyncSession,
    order: Order,
    *,
    viewer_role: Optional[str] = None,
    viewer_user_id: Optional[int] = None,
) -> dict[str, Any]:
    """返回需合并进订单详情 payload 的扩展字段（不含 Order ORM 本体 json）。"""
    user_ids: set[int] = {int(order.client_id), int(order.delivery_id)}
    if order.supplier_id is not None:
        user_ids.add(int(order.supplier_id))
    users = (await db.scalars(select(User).where(User.id.in_(list(user_ids))))).all()
    user_map = {int(u.id): u for u in users}

    out: dict[str, Any] = {}
    out["client"] = user_brief(user_map.get(int(order.client_id)))
    out["delivery"] = user_brief(user_map.get(int(order.delivery_id)))
    canteen = None
    if order.canteen_id is not None:
        canteen = await db.scalar(select(ClientCanteen).where(ClientCanteen.id == int(order.canteen_id)))
    if canteen:
        school_user = user_map.get(int(order.client_id))
        out["canteen"] = {
            "id": int(canteen.id),
            "name": canteen.name,
            "address": canteen.address or "",
            "lng": float(canteen.lng) if canteen.lng is not None else None,
            "lat": float(canteen.lat) if canteen.lat is not None else None,
            "contact_name": (
                (school_user.company_name or school_user.username) if school_user else None
            ),
            "contact_phone": (school_user.contact_phone if school_user else None),
        }
    else:
        out["canteen"] = None
    # 不再使用「主单供货商」语义；详情仅展示 allocation_suppliers（分单去重）
    out["supplier"] = None

    item_snapshot_map: dict[int, dict] = {}
    for idx, snap in enumerate(order.items_snapshot_json or [], 1):
        if isinstance(snap, dict):
            item_snapshot_map[idx] = snap
    product_ids_from_order = {
        int(i.get("product_id") or 0)
        for i in (order.items_json or [])
        if int(i.get("product_id") or 0) > 0
    }
    product_meta_map: dict[int, dict] = {}
    if product_ids_from_order:
        product_rows = (
            await db.scalars(
                select(Product).where(Product.id.in_(list(product_ids_from_order)))
            )
        ).all()
        product_meta_map = {
            int(p.id): {
                "unit": p.unit or "",
                "spec": p.spec or "",
                "name": p.name or f"商品#{int(p.id)}",
                "reference_price": float(p.reference_price or 0),
                "category1_id": int(p.category1_id) if p.category1_id is not None else None,
                "is_designated_factory": bool(p.is_designated_factory),
                "designated_factory_id": int(p.designated_factory_id) if p.designated_factory_id else None,
                "quality_report_mode": str(p.quality_report_mode or "batch"),
            }
            for p in product_rows
        }

    on_date = order.expected_delivery_date or order.created_at.date()
    contract = await _signed_contract_for_order_on_date(
        db, int(order.client_id), int(order.delivery_id), on_date
    )
    contract_payload: Optional[dict] = None
    if contract:
        cat_ids = [int(x) for x in (contract.category_ids_json or [])]
        cat_rows = (
            (await db.scalars(select(Category).where(Category.id.in_(cat_ids)))).all()
            if cat_ids
            else []
        )
        cat_name_map = {int(c.id): c.name for c in cat_rows}
        category_rates = []
        for entry in contract.category_rates_json or []:
            try:
                cid = int(entry.get("category_id")) if entry.get("category_id") is not None else None
            except (TypeError, ValueError):
                cid = None
            category_rates.append(
                {
                    "category_id": cid,
                    "category_name": cat_name_map.get(cid, "") if cid is not None else "",
                    "float_rate": float(entry.get("float_rate") or 0),
                }
            )
        ref_by_pid = {
            int(pid): float(m.get("reference_price") or 0) for pid, m in product_meta_map.items()
        }
        rate_map, fallback_rt = _contract_category_rate_map(contract)
        contract_payload = {
            "id": int(contract.id),
            "contract_no": contract.contract_no,
            "period_start": contract.period_start.isoformat(),
            "period_end": contract.period_end.isoformat(),
            "status": contract.status,
            "price_float_rate": float(contract.price_float_rate or 0),
            # 本单综合上浮率：按本单指导价金额加权，与「实付÷指导价−1」保持同口径。
            "order_float_rate": amount_weighted_contract_float_rate(
                order, rate_map, fallback_rt, product_meta_map
            ),
            "order_realized_float_rate": calc_order_float_rate(order, product_ref_by_id=ref_by_pid),
            "category_rates": category_rates,
            "category_ids": cat_ids,
            "category_names": [cat_name_map.get(cid, str(cid)) for cid in cat_ids],
        }
    out["contract"] = contract_payload

    order_items: list[dict] = []
    for idx, item in enumerate(order.items_json or [], 1):
        snap = item_snapshot_map.get(idx, {})
        pid = int(item.get("product_id") or snap.get("product_id") or 0)
        pmeta = product_meta_map.get(pid, {})
        qty = float(item.get("quantity") or 0)
        unit_price = float(item.get("unit_price") or 0)
        order_items.append(
            {
                "line_no": idx,
                "product_id": pid,
                "product_name": snap.get("product_name") or pmeta.get("name") or f"商品#{pid}",
                "spec": snap.get("spec") or pmeta.get("spec") or "",
                "unit": snap.get("unit") or pmeta.get("unit") or "",
                "standard_type": snap.get("standard_type") or pmeta.get("standard_type") or "standard",
                "unit_weight_kg": snap.get("unit_weight_kg") or pmeta.get("unit_weight_kg"),
                "quantity": qty,
                "unit_price": unit_price,
                "amount": round(qty * unit_price, 2),
                "category1_id": snap.get("category1_id"),
                "category1_name": snap.get("category1_name") or "",
                "category2_id": snap.get("category2_id"),
                "category2_name": snap.get("category2_name") or "",
                "is_designated_factory": pmeta.get("is_designated_factory", False),
                "designated_factory_id": pmeta.get("designated_factory_id"),
            }
        )
    out["order_items"] = order_items

    alloc_rows = (
        await db.scalars(
            select(OrderItemAllocation)
            .where(OrderItemAllocation.order_id == order.id)
            .order_by(OrderItemAllocation.line_no.asc(), OrderItemAllocation.id.asc())
        )
    ).all()
    alloc_supplier_ids = sorted({int(a.supplier_id) for a in alloc_rows})
    supplier_name_map: dict[int, str] = {}
    supplier_user_map: dict[int, User] = {}
    if alloc_supplier_ids:
        supplier_rows = (
            await db.scalars(select(User).where(User.id.in_(alloc_supplier_ids)))
        ).all()
        supplier_user_map = {int(u.id): u for u in supplier_rows}
        supplier_name_map = {
            int(u.id): (u.company_name or u.username or f"供货商#{u.id}") for u in supplier_rows
        }
    # 交易主体「供货商」按分单去重展示；无分单时前端仍回退 order.supplier（主单字段）
    out["allocation_suppliers"] = [
        user_brief(supplier_user_map[sid]) for sid in alloc_supplier_ids if sid in supplier_user_map
    ]

    qr_rows = (
        await db.scalars(
            select(QualityReport).where(QualityReport.order_id == order.id)
        )
    ).all()
    qr_by_alloc: dict[int, dict] = {}
    qr_legacy: dict[tuple[int, int], dict] = {}
    for q in qr_rows:
        qpayload = {
            "id": int(q.id),
            "report_no": q.report_no,
            "file_url": q.file_url,
            "file_urls": file_urls_from_row(q),
            "status": q.status,
            "supplier_id": int(q.supplier_id),
            "product_id": int(q.product_id),
            "allocation_id": int(q.allocation_id) if q.allocation_id is not None else None,
            "created_at": q.created_at.isoformat() if getattr(q, "created_at", None) else None,
        }
        if q.allocation_id is not None:
            qr_by_alloc[int(q.allocation_id)] = qpayload
        else:
            qr_legacy.setdefault((int(q.product_id), int(q.supplier_id)), qpayload)

    cover_date = quality_cover_date_for_order(order)
    periodic_by_key = await approved_periodic_report_map(db, alloc_rows, cover_date=cover_date)
    allocations: list[dict] = []
    line_split_count: dict[int, int] = {}
    for row in alloc_rows:
        ln = int(row.line_no)
        line_split_count[ln] = line_split_count.get(ln, 0) + 1
    for row in alloc_rows:
        ln = int(row.line_no)
        snap = item_snapshot_map.get(ln, {})
        pmeta = product_meta_map.get(int(row.product_id), {})
        report = qr_by_alloc.get(int(row.id))
        if not report:
            report = qr_legacy.get((int(row.product_id), int(row.supplier_id)))
        qmode = str(pmeta.get("quality_report_mode") or "batch")
        periodic_report = None
        covered_by = "batch" if report else None
        if qmode == "periodic":
            periodic_report = periodic_report_payload(
                periodic_by_key.get((int(row.product_id), int(row.supplier_id)))
            )
            if periodic_report:
                covered_by = "periodic"
        is_missing = covered_by is None
        allocations.append(
            {
                "id": int(row.id),
                "line_no": ln,
                "product_id": int(row.product_id),
                "product_name": snap.get("product_name") or pmeta.get("name") or f"商品#{int(row.product_id)}",
                "spec": snap.get("spec") or pmeta.get("spec") or "",
                "unit": snap.get("unit") or pmeta.get("unit") or "",
                "quantity": float(row.quantity),
                "unit_price": float(row.unit_price),
                "amount": round(float(row.quantity) * float(row.unit_price), 2),
                "supplier_id": int(row.supplier_id),
                "supplier_name": supplier_name_map.get(int(row.supplier_id), f"供货商#{int(row.supplier_id)}"),
                "status": row.status,
                "allocation_batch_no": row.allocation_batch_no,
                "is_split_line": bool(line_split_count.get(ln, 0) > 1),
                "split_line_count": int(line_split_count.get(ln, 0)),
                "quality_report_mode": qmode,
                "quality_report": report,
                "periodic_quality_report": periodic_report,
                "quality_covered_by": covered_by,
                "missing_quality": is_missing,
                "missing_quality_shipped": is_missing and str(row.status) == "已出库",
            }
        )
    out["allocations"] = allocations

    canteen_payable = round(float(order.total_amount or 0), 2)
    supplier_payable = round(sum(float(a.get("amount") or 0) for a in allocations), 2)
    delivery_profit = round(canteen_payable - supplier_payable, 2)
    out["order_settlement"] = {
        "canteen_payable_amount": canteen_payable,
        "supplier_payable_amount": supplier_payable,
        "delivery_profit_amount": delivery_profit,
    }
    if out.get("contract") is not None:
        out["contract"]["canteen_payable_amount"] = canteen_payable
        out["contract"]["supplier_payable_amount"] = supplier_payable
        out["contract"]["delivery_profit_amount"] = delivery_profit

    line_alloc_groups: list[dict] = []
    for it in order_items:
        ln = int(it["line_no"])
        line_allocs = [a for a in allocations if int(a["line_no"]) == ln]
        line_alloc_groups.append(
            {
                "line_no": ln,
                "product_name": it["product_name"],
                "spec": it["spec"],
                "unit": it["unit"],
                "ordered_quantity": float(it["quantity"]),
                "ordered_amount": float(it["amount"]),
                "is_split": bool(len(line_allocs) > 1),
                "is_designated_factory": bool(it.get("is_designated_factory")),
                "allocations": line_allocs,
            }
        )
    out["line_alloc_groups"] = line_alloc_groups

    recv_rows = (
        await db.scalars(
            select(OrderReceivingLine)
            .where(OrderReceivingLine.order_id == order.id)
            .order_by(OrderReceivingLine.line_index.asc())
        )
    ).all()
    receiving_billing = await build_receiving_billing_snapshot(db, order)
    receiving_billing_lines = {
        int(x.get("line_index") or 0): x for x in (receiving_billing.get("lines") or [])
    }
    order_item_by_line = {int(it["line_no"]): it for it in order_items}
    out["receiving_lines"] = [
        _receiving_line_payload(r, receiving_billing_lines, order_item_by_line) for r in recv_rows
    ]
    out["receiving_total_lines"] = len(order_items)
    out["receiving_confirmed_count"] = len([r for r in recv_rows if str(r.status) == "confirmed"])
    out["receiving_billing"] = receiving_billing
    out["receiving_total_kg"] = receiving_billing.get("received_kg")
    out["receiving_amount"] = receiving_billing.get("received_amount")
    out["receiving_deduction_amount"] = receiving_billing.get("deduction_amount")
    shortage_ct = len(
        [r for r in out["receiving_lines"] if str(r.get("diff_type")) == "shortage"]
    )
    out["shortage_line_count"] = shortage_ct

    ret_hdr = await db.scalar(
        select(OrderReturn).where(OrderReturn.order_id == order.id, OrderReturn.source == "receive_shortage")
    )
    if ret_hdr:
        ret_lns = (
            await db.scalars(
                select(OrderReturnLine).where(OrderReturnLine.order_return_id == int(ret_hdr.id))
            )
        ).all()
        return_lines = []
        for line in ret_lns:
            payload = _return_line_payload(line)
            line_billing = receiving_billing_lines.get(int(line.line_index)) or {}
            unit = str(line_billing.get("measure_unit") or "kg")
            payload["is_standard"] = bool(line_billing.get("is_standard"))
            payload["measure_unit"] = unit
            payload["ordered_qty"] = line_billing.get("ordered_qty", payload.get("ordered_kg"))
            payload["received_qty"] = line_billing.get("received_qty", payload.get("received_kg"))
            payload["ordered_text"] = _amount_text(payload.get("ordered_qty"), unit)
            payload["received_text"] = _amount_text(payload.get("received_qty"), unit)
            payload["diff_label"] = _amount_text(
                -abs(float(line_billing.get("diff_qty_signed") or payload.get("delta_kg") or 0)),
                unit,
            )
            if line_billing.get("deduction_amount") is not None:
                payload["deduction_amount"] = float(line_billing.get("deduction_amount") or 0)
            return_lines.append(payload)
        out["order_return"] = {
            "id": int(ret_hdr.id),
            "return_no": ret_hdr.return_no,
            "status": str(ret_hdr.status),
            "status_label": _return_status_label(ret_hdr.status),
            "reviewed_by_user_id": int(ret_hdr.reviewed_by_user_id) if ret_hdr.reviewed_by_user_id is not None else None,
            "reviewed_at": ret_hdr.reviewed_at.isoformat() if ret_hdr.reviewed_at else None,
            "review_note": ret_hdr.review_note,
            "source": "receive_shortage",
            "source_label": "收货少收退货单",
            "lines": return_lines,
        }
    else:
        out["order_return"] = None

    delivery_record = await db.scalar(
        select(Delivery).where(Delivery.order_id == order.id).order_by(Delivery.id.desc())
    )
    out["delivery_record"] = (
        {
            "id": int(delivery_record.id),
            "driver_name": delivery_record.driver_name,
            "vehicle_no": delivery_record.vehicle_no,
            "status": str(delivery_record.status),
            "departed_at": delivery_record.departed_at.isoformat() if delivery_record.departed_at else None,
            "arrived_at": delivery_record.arrived_at.isoformat() if delivery_record.arrived_at else None,
            "current_lng": float(delivery_record.current_lng) if delivery_record.current_lng is not None else None,
            "current_lat": float(delivery_record.current_lat) if delivery_record.current_lat is not None else None,
        }
        if delivery_record
        else None
    )
    dispatch_row = (
        await db.execute(
            select(DeliveryDispatchTrip, DeliveryDispatchStop)
            .join(DeliveryDispatchStop, DeliveryDispatchStop.trip_id == DeliveryDispatchTrip.id)
            .where(
                DeliveryDispatchStop.order_id == int(order.id),
                DeliveryDispatchTrip.status.in_(["待发车", "有阻塞", "运输中", "已完成"]),
            )
            .order_by(DeliveryDispatchTrip.id.desc())
            .limit(1)
        )
    ).first()
    dispatch_trip = dispatch_row[0] if dispatch_row else None
    out["dispatch_trip"] = (
        {
            "id": int(dispatch_trip.id),
            "route_no": dispatch_trip.route_no,
            "status": dispatch_trip.status,
            "depart_mode": dispatch_trip.depart_mode,
            "vehicle_no": dispatch_trip.vehicle_no,
            "driver_name": dispatch_trip.driver_name,
            "departure_time": dispatch_trip.departure_time,
            "departed_at": dispatch_trip.departed_at.isoformat() if dispatch_trip.departed_at else None,
        }
        if dispatch_trip
        else None
    )
    out["logistics_tracking"] = await build_order_logistics_tracking(
        db, order, viewer_role=viewer_role, viewer_user_id=viewer_user_id
    )

    log_rows = (
        await db.scalars(
            select(OrderStatusLog)
            .where(OrderStatusLog.order_id == order.id)
            .order_by(OrderStatusLog.id.asc())
        )
    ).all()
    item_log_rows = (
        await db.execute(
            select(OrderItemStatusLog, OrderItemAllocation)
            .join(OrderItemAllocation, OrderItemAllocation.id == OrderItemStatusLog.allocation_id)
            .where(OrderItemAllocation.order_id == order.id)
            .order_by(OrderItemStatusLog.id.asc())
        )
    ).all()
    audit_rows = (
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.object_type == "order", AuditLog.object_id == order.id)
            .order_by(AuditLog.id.asc())
        )
    ).all()
    sort_rows = (
        await db.scalars(
            select(SortRecord)
            .where(SortRecord.order_id == order.id)
            .order_by(SortRecord.id.asc())
        )
    ).all()
    actor_ids = {int(order.client_id)}
    actor_ids.update(int(l.actor_user_id or 0) for l in log_rows if int(l.actor_user_id or 0) > 0)
    actor_ids.update(int(l.operator_id or 0) for l, _ in item_log_rows if int(l.operator_id or 0) > 0)
    actor_ids.update(int(l.actor_user_id or 0) for l in audit_rows if int(l.actor_user_id or 0) > 0)
    actor_ids.update(int(l.operator_id or 0) for l in sort_rows if int(l.operator_id or 0) > 0)
    actor_ids.update(int(q.supplier_id or 0) for q in qr_rows if int(q.supplier_id or 0) > 0)
    actor_ids.update(int(a.supplier_id or 0) for a in alloc_rows if int(a.supplier_id or 0) > 0)
    actor_rows = (
        (await db.scalars(select(User).where(User.id.in_(sorted(actor_ids))))).all()
        if actor_ids
        else []
    )
    actor_map = {int(u.id): u for u in actor_rows}

    def _status_event(old_status: str, new_status: str, actor_user_id: int, created_at: Any) -> dict:
        old_status = "" if old_status in {"N/A", "None"} else old_status
        return {
            "event_type": "order_status",
            "from_status": old_status,
            "to_status": new_status,
            **_actor_brief(actor_user_id, actor_map),
            "action_title": STATUS_ACTION_TITLES.get(new_status, f"状态变更为{new_status}"),
            "description": _status_description(old_status, new_status),
            "created_at": created_at.isoformat() if created_at else None,
        }

    timeline = [
        _status_event(str(l.old_status), str(l.new_status), int(l.actor_user_id), l.created_at)
        for l in log_rows
    ]
    has_create_event = any(
        str(ev.get("to_status")) == "下单" and str(ev.get("from_status") or "") in {"", "N/A"}
        for ev in timeline
    )
    if not has_create_event:
        timeline.insert(0, _status_event("", "下单", int(order.client_id), order.created_at))
    out["status_timeline"] = timeline
    out["status_flow"] = list(ORDER_STATUS_FLOW)

    process_timeline = list(timeline)
    allocation_groups: dict[tuple[int, str, str], dict] = {}
    for item_log, alloc in item_log_rows:
        ts = item_log.created_at.replace(microsecond=0).isoformat() if item_log.created_at else ""
        key = (int(item_log.operator_id), str(item_log.new_status), ts)
        group = allocation_groups.setdefault(
            key,
            {
                "actor_user_id": int(item_log.operator_id),
                "new_status": str(item_log.new_status),
                "created_at": item_log.created_at,
                "count": 0,
                "supplier_ids": set(),
            },
        )
        group["count"] += 1
        group["supplier_ids"].add(int(alloc.supplier_id))
    for group in allocation_groups.values():
        actor = _actor_brief(int(group["actor_user_id"]), actor_map)
        supplier_names = [
            supplier_name_map.get(int(sid), f"供货商#{int(sid)}")
            for sid in sorted(group["supplier_ids"])
        ]
        supplier_text = _join_names(supplier_names)
        new_status = str(group["new_status"])
        if new_status == "已分配":
            title = "配送商已分配供货商"
            desc = f"配送商已将本订单 {int(group['count'])} 条商品分配给{supplier_text}。"
        else:
            title = f"分包状态更新为{new_status}"
            desc = f"{supplier_text}的分包状态更新为「{new_status}」，共 {int(group['count'])} 条商品。"
        process_timeline.append(
            {
                "event_type": "allocation_status",
                **actor,
                "action_title": title,
                "description": desc,
                "created_at": group["created_at"].isoformat() if group["created_at"] else None,
            }
        )
    for row in sort_rows:
        actor = _actor_brief(int(row.operator_id), actor_map)
        process_timeline.append(
            {
                "event_type": "supplier_action",
                **actor,
                "action_title": "供货商已分拣",
                "description": f"{actor['actor_name']}已完成本订单分拣。"
                + (" 已打印标签。" if row.label_printed else ""),
                "created_at": row.sorted_at.isoformat() if row.sorted_at else None,
            }
        )
    quality_groups: dict[tuple[int, str], dict] = {}
    for q in qr_rows:
        ts = q.created_at.replace(microsecond=0).isoformat() if getattr(q, "created_at", None) else ""
        key = (int(q.supplier_id), ts)
        group = quality_groups.setdefault(
            key,
            {"supplier_id": int(q.supplier_id), "created_at": q.created_at, "count": 0},
        )
        group["count"] += 1
    for group in quality_groups.values():
        actor = _actor_brief(int(group["supplier_id"]), actor_map)
        process_timeline.append(
            {
                "event_type": "supplier_action",
                **actor,
                "action_title": "供货商已上传质检",
                "description": f"{actor['actor_name']}已上传 {int(group['count'])} 份质检报告。",
                "created_at": group["created_at"].isoformat() if group["created_at"] else None,
            }
        )
    shipped_groups: dict[tuple[int, str], dict] = {}
    for alloc in alloc_rows:
        if str(alloc.status) != "已出库":
            continue
        ts = alloc.updated_at.replace(microsecond=0).isoformat() if alloc.updated_at else ""
        key = (int(alloc.supplier_id), ts)
        group = shipped_groups.setdefault(
            key,
            {"supplier_id": int(alloc.supplier_id), "created_at": alloc.updated_at, "count": 0},
        )
        group["count"] += 1
    for group in shipped_groups.values():
        actor = _actor_brief(int(group["supplier_id"]), actor_map)
        process_timeline.append(
            {
                "event_type": "supplier_action",
                **actor,
                "action_title": "供货商已出库",
                "description": f"{actor['actor_name']}已将本订单 {int(group['count'])} 条商品出库，等待配送商取货。",
                "created_at": group["created_at"].isoformat() if group["created_at"] else None,
            }
        )
    for audit in audit_rows:
        if audit.action in {
            "order_create",
            "order_status_change",
            "supplier_print_order_label",
            "supplier_print_allocation_label",
        }:
            continue
        title = _audit_action_title(audit.action)
        process_timeline.append(
            {
                "event_type": "audit",
                **_actor_brief(int(audit.actor_user_id), actor_map),
                "action_title": title,
                "description": _audit_description(audit.action, audit.detail),
                "created_at": audit.created_at.isoformat() if audit.created_at else None,
                "action": audit.action,
            }
        )
    process_timeline.sort(key=lambda x: x.get("created_at") or "")
    process_timeline = _collapse_repeated_timeline_events(process_timeline)
    out["process_timeline"] = process_timeline

    complaint_ticket_rows = (
        await db.scalars(
            select(Ticket)
            .where(Ticket.order_id == order.id, Ticket.type == "售后投诉")
            .order_by(Ticket.id.desc())
        )
    ).all()

    def _delivery_can_see_ticket(ct: Ticket) -> bool:
        if viewer_role != "delivery" or viewer_user_id is None:
            return True
        aid = getattr(ct, "assigned_delivery_id", None)
        effective_delivery = int(aid) if aid is not None else int(order.delivery_id)
        if str(ct.status) == "已关闭":
            return effective_delivery == int(viewer_user_id)
        return effective_delivery == int(viewer_user_id)

    complaint_attachments: list[dict] = []
    complaint_tickets: list[dict] = []
    my_complaint_ticket: Optional[dict] = None

    for ct in complaint_ticket_rows:
        if viewer_role == "delivery" and viewer_user_id is not None and not _delivery_can_see_ticket(ct):
            continue
        imgs = list(ct.attachments_json or []) if isinstance(ct.attachments_json, list) else []
        imgs = [str(u).strip() for u in imgs if str(u).strip()][:5]
        desc = (ct.description or "").strip()
        if imgs or desc or viewer_role != "delivery":
            complaint_attachments.append(
                {
                    "ticket_id": int(ct.id),
                    "status": str(ct.status),
                    "description": ct.description,
                    "created_at": ct.created_at.isoformat() if ct.created_at else None,
                    "images": imgs,
                }
            )
        full = complaint_ticket_public_dict(ct)
        complaint_tickets.append(full)
        if (
            viewer_role == "delivery"
            and viewer_user_id is not None
            and str(ct.status) != "已关闭"
            and _delivery_can_see_ticket(ct)
        ):
            if my_complaint_ticket is None or int(ct.id) > int(my_complaint_ticket.get("ticket_id") or 0):
                my_complaint_ticket = full

    out["complaint_attachments"] = complaint_attachments
    out["complaint_tickets"] = complaint_tickets
    out["my_complaint_ticket"] = my_complaint_ticket if viewer_role == "delivery" else None

    missing_shipped = await missing_quality_allocations(db, int(order.id), shipped_only=True)
    missing_all = sum(1 for a in allocations if a.get("missing_quality"))
    out["abnormal_flags"] = {
        "missing_quality_count": int(missing_all),
        "missing_quality_shipped_count": len(missing_shipped),
        "missing_quality_shipped": bool(missing_shipped),
        "missing_quality_after_ship": bool(missing_shipped),
        "shortage_line_count": int(shortage_ct),
        "has_order_return": bool(ret_hdr is not None),
        "has_abnormal": bool(order.has_abnormal),
    }

    # 客户视角脱敏：客户的结算/商务对手方是配送商，不应看到供货商身份与配送商毛利。
    # 质检报告按商品行保留（客户关心食安），但隐去是哪家供货商供的货及分单金额拆解。
    if viewer_role == "client":
        out["process_timeline"] = _sanitize_client_timeline(out.get("process_timeline") or [])
        out["status_timeline"] = _sanitize_client_timeline(out.get("status_timeline") or [])
        out["allocation_suppliers"] = []
        for a in out.get("allocations", []) or []:
            a.pop("supplier_id", None)
            a.pop("supplier_name", None)
        for grp in out.get("line_alloc_groups", []) or []:
            for a in grp.get("allocations", []) or []:
                a.pop("supplier_id", None)
                a.pop("supplier_name", None)
        if isinstance(out.get("order_settlement"), dict):
            out["order_settlement"].pop("supplier_payable_amount", None)
            out["order_settlement"].pop("delivery_profit_amount", None)
        if isinstance(out.get("contract"), dict):
            out["contract"].pop("supplier_payable_amount", None)
            out["contract"].pop("delivery_profit_amount", None)
            out["contract"].pop("order_realized_float_rate", None)

    return out
