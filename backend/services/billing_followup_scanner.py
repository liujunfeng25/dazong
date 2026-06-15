"""账单临期通知与超期工单扫描。"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models import BillingCycle, BillingStatement, Notification, Ticket, User
from services.billing_service import compute_billing_period

SCAN_INTERVAL_SECONDS = 86_400
BILLING_CONFIRM_OVERDUE_PREFIX = "【账单超期未确认】"
BILLING_PAYMENT_OVERDUE_PREFIX = "【账单超期未付款】"


async def _operation_user(db: AsyncSession) -> User | None:
    return await db.scalar(select(User).where(User.role == "operation").order_by(User.id.asc()))


async def _notify_once(
    db: AsyncSession,
    *,
    event_type: str,
    title: str,
    content: str,
    target: User,
    statement_id: int,
) -> None:
    today = date.today()
    existing = await db.scalar(
        select(Notification.id)
        .where(
            Notification.event_type == event_type,
            Notification.object_type == "billing_statement",
            Notification.object_id == int(statement_id),
            Notification.target_user_id == int(target.id),
            func.date(Notification.created_at) == today,
        )
        .limit(1)
    )
    if existing:
        return
    db.add(
        Notification(
            event_type=event_type,
            title=title,
            content=content,
            role=str(target.role),
            target_user_id=int(target.id),
            canteen_id=None,
            object_type="billing_statement",
            object_id=int(statement_id),
            route=f"/{target.role}/bills" if target.role in {"client", "delivery", "supplier", "factory"} else "/operation/billing-overview",
            is_read=False,
        )
    )


async def _ensure_billing_ticket(
    db: AsyncSession,
    *,
    statement: BillingStatement,
    prefix: str,
    description: str,
    actor_user_id: int,
) -> Ticket:
    existing = await db.scalar(
        select(Ticket)
        .where(
            Ticket.billing_statement_id == int(statement.id),
            Ticket.type == "账务异常",
            Ticket.status != "已关闭",
            Ticket.description.like(f"{prefix}%"),
        )
        .order_by(Ticket.id.desc())
        .limit(1)
    )
    if existing:
        existing.description = description
        existing.updated_at = datetime.utcnow()
        return existing
    ticket = Ticket(
        order_id=None,
        billing_statement_id=int(statement.id),
        type="账务异常",
        description=description,
        status="待处理",
        created_by=int(actor_user_id),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(ticket)
    await db.flush()
    return ticket


async def close_billing_overdue_tickets_if_settled(db: AsyncSession, statement_id: int) -> None:
    rows = (
        await db.scalars(
            select(Ticket).where(
                Ticket.billing_statement_id == int(statement_id),
                Ticket.type == "账务异常",
                Ticket.status != "已关闭",
            )
        )
    ).all()
    for row in rows:
        row.status = "已关闭"
        row.updated_at = datetime.utcnow()


async def close_billing_confirm_overdue_tickets_if_confirmed(db: AsyncSession, statement_id: int) -> None:
    rows = (
        await db.scalars(
            select(Ticket).where(
                Ticket.billing_statement_id == int(statement_id),
                Ticket.type == "账务异常",
                Ticket.status != "已关闭",
                Ticket.description.like(f"{BILLING_CONFIRM_OVERDUE_PREFIX}%"),
            )
        )
    ).all()
    for row in rows:
        row.status = "已关闭"
        row.updated_at = datetime.utcnow()


async def scan_billing_followups_once() -> None:
    async with SessionLocal() as db:
        today = date.today()
        op = await _operation_user(db)
        op_id = int(op.id) if op else 0
        cycles = (await db.scalars(select(BillingCycle))).all()
        cycle_map = {int(c.id): c for c in cycles}
        rows = (
            await db.scalars(
                select(BillingStatement)
                .where(BillingStatement.direction == "应付", BillingStatement.status != "已结清")
                .order_by(BillingStatement.id.asc())
            )
        ).all()
        user_ids = sorted(
            {
                int(x)
                for row in rows
                for x in (row.owner_user_id, row.counterparty_user_id, op_id)
                if int(x or 0) > 0
            }
        )
        users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
        user_map = {int(u.id): u for u in users}
        for row in rows:
            cycle = cycle_map.get(int(row.cycle_id or 0))
            if not cycle:
                continue
            period = compute_billing_period(row.created_at or datetime.utcnow(), cycle)
            confirm_due = date.fromisoformat(period["confirm_due_date"])
            payment_due = date.fromisoformat(period["payment_due_date"])
            payer = user_map.get(int(row.owner_user_id))
            payee = user_map.get(int(row.counterparty_user_id))
            targets = [u for u in (payer, payee, op) if u]
            counterparty_name = (row.source_snapshot_json or {}).get("counterparty_name") or ""
            base = f"账单 {row.statement_no}（{period['period_label']}，金额 ¥{row.amount}，对方 {counterparty_name or '—'}）"
            if row.status == "待确认" and (confirm_due - today).days == 1:
                for target in targets:
                    await _notify_once(
                        db,
                        event_type="billing_confirm_due_soon",
                        title="账单即将到确认期限",
                        content=f"{base} 将于 {period['confirm_due_date']} 到确认期限，请及时核对。",
                        target=target,
                        statement_id=int(row.id),
                    )
            if row.status in {"待确认", "已确认", "部分结清"} and (payment_due - today).days == 1:
                for target in targets:
                    await _notify_once(
                        db,
                        event_type="billing_payment_due_soon",
                        title="账单即将到付款期限",
                        content=f"{base} 将于 {period['payment_due_date']} 到付款期限，请及时跟进。",
                        target=target,
                        statement_id=int(row.id),
                    )
            if row.status == "待确认" and today > confirm_due:
                await _ensure_billing_ticket(
                    db,
                    statement=row,
                    prefix=BILLING_CONFIRM_OVERDUE_PREFIX,
                    description=f"{BILLING_CONFIRM_OVERDUE_PREFIX}{base} 已超过确认期限 {period['confirm_due_date']}，超期 {(today - confirm_due).days} 天。",
                    actor_user_id=op_id,
                )
            if row.status in {"已确认", "部分结清"} and today > payment_due:
                await _ensure_billing_ticket(
                    db,
                    statement=row,
                    prefix=BILLING_PAYMENT_OVERDUE_PREFIX,
                    description=f"{BILLING_PAYMENT_OVERDUE_PREFIX}{base} 已超过付款期限 {period['payment_due_date']}，超期 {(today - payment_due).days} 天。",
                    actor_user_id=op_id,
                )
        await db.commit()


async def _scanner_loop() -> None:
    while True:
        try:
            await scan_billing_followups_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def start_billing_followup_scanner() -> asyncio.Task:
    return asyncio.create_task(_scanner_loop())


async def stop_billing_followup_scanner(task: asyncio.Task | None) -> None:
    if not task:
        return
    task.cancel()
    with contextlib.suppress(Exception):
        await task
