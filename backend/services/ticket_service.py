"""工单服务：缺质检、配送超时、售后投诉三类工单的建立/关闭与去重。

设计要点：
- 不改 Ticket.type Enum，沿用 异常订单 / 售后投诉 / 配送异常。
- 缺质检与「合约范围异常」共享 `异常订单` 类型，靠 description 前缀区分：
  - 缺质检前缀「【质检缺失】」
  - 配送超时前缀「【配送超时】」（属配送异常类型）
- 同订单 + 同 type + 同 description 前缀 + 未关闭的工单只允许一张。
- 配送超时工单：配送端确认送达（订单进入「收货」）后自动关闭。
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Alert, Order, Ticket, User

QUALITY_MISSING_PREFIX = "【质检缺失】"
DELIVERY_OVERDUE_PREFIX = "【配送超时】"


async def _find_open_ticket(
    db: AsyncSession, order_id: int, ticket_type: str, description_prefix: Optional[str] = None
) -> Optional[Ticket]:
    stmt = select(Ticket).where(
        Ticket.order_id == order_id,
        Ticket.type == ticket_type,
        Ticket.status != "已关闭",
    )
    if description_prefix:
        stmt = stmt.where(Ticket.description.like(f"{description_prefix}%"))
    return await db.scalar(stmt.order_by(Ticket.id.desc()).limit(1))


async def ensure_quality_missing_ticket(
    db: AsyncSession,
    order: Order,
    actor_user_id: int,
    missing_count: int,
) -> Optional[Ticket]:
    """缺质检触发：保证一张未关闭的「异常订单·质检缺失」工单存在；存在则更新描述。"""
    desc = (
        f"{QUALITY_MISSING_PREFIX}订单 {order.order_no}：{int(missing_count)} "
        f"条已出库分单缺质检报告"
    )
    existing = await _find_open_ticket(
        db, int(order.id), "异常订单", QUALITY_MISSING_PREFIX
    )
    if existing:
        existing.description = desc
        existing.updated_at = datetime.utcnow()
        return existing
    ticket = Ticket(
        order_id=int(order.id),
        type="异常订单",
        description=desc,
        status="待处理",
        created_by=int(actor_user_id),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(ticket)
    await db.flush()
    return ticket


async def close_quality_missing_ticket_if_clear(
    db: AsyncSession, order: Order
) -> Optional[Ticket]:
    """所有分单质检齐时关闭「质检缺失」工单（仅匹配前缀，避免误关合约异常单）。"""
    existing = await _find_open_ticket(
        db, int(order.id), "异常订单", QUALITY_MISSING_PREFIX
    )
    if not existing:
        return None
    existing.status = "已关闭"
    existing.updated_at = datetime.utcnow()
    return existing


async def ensure_delivery_overdue_ticket(
    db: AsyncSession,
    order: Order,
    actor_user_id: int,
) -> Optional[Ticket]:
    """配送超时触发：保证一张未关闭的「配送异常·配送超时」工单存在。"""
    slot = (order.expected_delivery_slot or "").strip() or "—"
    date_str = order.expected_delivery_date.isoformat() if order.expected_delivery_date else "—"
    desc = f"{DELIVERY_OVERDUE_PREFIX}订单 {order.order_no}：约定 {date_str} {slot} 仍未送达"
    existing = await _find_open_ticket(
        db, int(order.id), "配送异常", DELIVERY_OVERDUE_PREFIX
    )
    if existing:
        existing.description = desc
        existing.updated_at = datetime.utcnow()
        return existing
    ticket = Ticket(
        order_id=int(order.id),
        type="配送异常",
        description=desc,
        status="待处理",
        created_by=int(actor_user_id),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(ticket)
    await db.flush()
    return ticket


async def close_delivery_overdue_ticket_if_delivered(
    db: AsyncSession, order: Order
) -> Optional[Ticket]:
    """订单已送达（进入「收货」）后，自动关闭未处理的「配送异常·配送超时」工单。"""
    existing = await _find_open_ticket(
        db, int(order.id), "配送异常", DELIVERY_OVERDUE_PREFIX
    )
    if not existing:
        return None
    existing.status = "已关闭"
    existing.updated_at = datetime.utcnow()
    return existing


async def find_open_delivery_overdue_alert(
    db: AsyncSession, order_id: int
) -> Optional[Alert]:
    """查未关闭的「配送超时」预警；同 type 下匹配 payload_json.order_id。

    Alert.payload_json 是 JSON 字段；活跃 open alerts 量级有限，先按 type+status
    粗筛再内存里按 order_id 精筛，避免依赖 MySQL JSON_EXTRACT 语法。
    """
    rows = await db.scalars(
        select(Alert)
        .where(Alert.type == "delivery_overdue", Alert.status == "open")
        .order_by(Alert.id.desc())
    )
    for alert in rows.all():
        payload = alert.payload_json if isinstance(alert.payload_json, dict) else {}
        try:
            if int(payload.get("order_id") or 0) == int(order_id):
                return alert
        except (TypeError, ValueError):
            continue
    return None


async def close_delivery_overdue_alert_if_delivered(
    db: AsyncSession, order: Order
) -> Optional[Alert]:
    """订单送达后关闭所有未关闭的 delivery_overdue 预警；返回最近一条以便日志。

    历史上线前积累的同订单多条 open 重复 alert 也会一并关闭，避免遗留 open。
    """
    rows = await db.scalars(
        select(Alert)
        .where(Alert.type == "delivery_overdue", Alert.status == "open")
        .order_by(Alert.id.desc())
    )
    closed_now: Optional[Alert] = None
    now_iso = datetime.utcnow().isoformat()
    target_id = int(order.id)
    for alert in rows.all():
        payload = alert.payload_json if isinstance(alert.payload_json, dict) else {}
        try:
            if int(payload.get("order_id") or 0) != target_id:
                continue
        except (TypeError, ValueError):
            continue
        alert.status = "closed"
        new_payload = dict(payload)
        new_payload["closed_at"] = now_iso
        alert.payload_json = new_payload
        if closed_now is None:
            closed_now = alert
    return closed_now


async def find_open_complaint_ticket(
    db: AsyncSession, order_id: int
) -> Optional[Ticket]:
    """查询订单是否已有未关闭的售后投诉工单（用于客户端按钮置灰判断）。"""
    return await _find_open_ticket(db, int(order_id), "售后投诉", description_prefix=None)


def complaint_phase(ticket: Ticket) -> Optional[str]:
    """售后投诉工单阶段：delivery_handling | operation_review | closed"""
    if str(ticket.type) != "售后投诉":
        return None
    if str(ticket.status) == "已关闭":
        return "closed"
    dr = (getattr(ticket, "delivery_response", None) or "").strip()
    if dr:
        return "operation_review"
    return "delivery_handling"


def complaint_ticket_public_dict(ticket: Ticket) -> dict[str, Any]:
    raw = ticket.attachments_json
    imgs = list(raw) if isinstance(raw, list) else []
    imgs = [str(u).strip() for u in imgs if str(u).strip()][:5]
    logs = getattr(ticket, "flow_logs_json", None)
    return {
        "ticket_id": int(ticket.id),
        "order_id": int(ticket.order_id),
        "status": str(ticket.status),
        "phase": complaint_phase(ticket),
        "description": ticket.description,
        "attachments_json": imgs,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "assigned_delivery_id": int(ticket.assigned_delivery_id)
        if getattr(ticket, "assigned_delivery_id", None) is not None
        else None,
        "delivery_response": getattr(ticket, "delivery_response", None),
        "delivery_responded_at": ticket.delivery_responded_at.isoformat()
        if getattr(ticket, "delivery_responded_at", None)
        else None,
        "operation_resolution": getattr(ticket, "operation_resolution", None),
        "operation_resolved_at": ticket.operation_resolved_at.isoformat()
        if getattr(ticket, "operation_resolved_at", None)
        else None,
        "flow_logs_json": list(logs) if isinstance(logs, list) else [],
    }


def _append_flow_log(ticket: Ticket, entry: dict) -> None:
    logs = list(getattr(ticket, "flow_logs_json", None) or [])
    if not isinstance(logs, list):
        logs = []
    logs.append(entry)
    ticket.flow_logs_json = logs


async def create_customer_complaint_ticket(
    db: AsyncSession,
    order: Order,
    client_user: User,
    reason: str,
    image_urls: list[str],
) -> Ticket:
    """客户端发起售后投诉：自动派发订单所属配送商，进入「配送商处理中」。"""
    if not order.delivery_id:
        raise HTTPException(400, "订单未绑定配送商，无法发起售后投诉")
    safe_urls = [str(u).strip() for u in (image_urls or []) if str(u).strip()][:5]
    now = datetime.utcnow()
    now_iso = now.isoformat()
    ticket = Ticket(
        order_id=int(order.id),
        type="售后投诉",
        description=(reason or "").strip(),
        status="处理中",
        attachments_json=safe_urls,
        assigned_delivery_id=int(order.delivery_id),
        created_by=int(client_user.id),
        created_at=now,
        updated_at=now,
        flow_logs_json=[
            {
                "action": "created",
                "role": "client",
                "actor_user_id": int(client_user.id),
                "at": now_iso,
            },
            {
                "action": "auto_dispatch",
                "role": "system",
                "note": f"delivery_id={int(order.delivery_id)}",
                "at": now_iso,
            },
        ],
    )
    db.add(ticket)
    await db.flush()
    return ticket


async def submit_delivery_complaint_response(
    db: AsyncSession,
    ticket: Ticket,
    delivery_user: User,
    response_text: str,
) -> Ticket:
    if str(ticket.type) != "售后投诉":
        raise HTTPException(400, "非售后投诉工单")
    order = await db.scalar(select(Order).where(Order.id == ticket.order_id))
    if not order:
        raise HTTPException(404, "关联订单不存在")
    aid = getattr(ticket, "assigned_delivery_id", None)
    effective = int(aid) if aid is not None else int(order.delivery_id)
    if int(delivery_user.id) != int(effective):
        raise HTTPException(403, "非本配送商工单")
    if complaint_phase(ticket) != "delivery_handling":
        raise HTTPException(400, "当前阶段不可提交配送处理意见")
    text = (response_text or "").strip()
    if not text:
        raise HTTPException(400, "请填写处理意见")
    now = datetime.utcnow()
    ticket.delivery_response = text
    ticket.delivery_responded_at = now
    ticket.updated_at = now
    _append_flow_log(
        ticket,
        {
            "action": "delivery_response",
            "role": "delivery",
            "actor_user_id": int(delivery_user.id),
            "note": text[:500],
            "at": now.isoformat(),
        },
    )
    await db.flush()
    return ticket


async def submit_operation_complaint_resolution(
    db: AsyncSession,
    ticket: Ticket,
    op_user: User,
    resolution_text: str,
) -> Ticket:
    if str(ticket.type) != "售后投诉":
        raise HTTPException(400, "非售后投诉工单")
    if complaint_phase(ticket) != "operation_review":
        raise HTTPException(400, "请先等待配送商提交处理意见后再结案")
    text = (resolution_text or "").strip()
    if not text:
        raise HTTPException(400, "请填写运营结案意见")
    now = datetime.utcnow()
    ticket.operation_resolution = text
    ticket.operation_resolved_at = now
    ticket.status = "已关闭"
    ticket.updated_at = now
    _append_flow_log(
        ticket,
        {
            "action": "operation_resolve",
            "role": "operation",
            "actor_user_id": int(op_user.id),
            "note": text[:500],
            "at": now.isoformat(),
        },
    )
    await db.flush()
    return ticket
