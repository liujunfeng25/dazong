"""订单配送超时扫描器（asyncio 循环，每 5 分钟一次）。

口径：
- 订单仍处于 `下单 / 配货 / 发货` 之一（即未到「收货」及之后）
- `expected_delivery_date + slot 结束时刻` 已过当前北京时间
- 同一订单同一「配送超时」工单只允许一张未关闭（去重靠 ticket_service）
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models import Alert, Order, User
from services.audit_service import write_audit_log
from services.delivery_slot import parse_delivery_slot_hours
from services.ticket_service import (
    DELIVERY_OVERDUE_PREFIX,
    ensure_delivery_overdue_ticket,
    find_open_delivery_overdue_alert,
)

SCAN_INTERVAL_SECONDS = 300
PRE_DELIVERY_STATUSES = ("下单", "配货", "发货")
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def _slot_end_naive(order: Order) -> datetime | None:
    """以北京时区拼出 expected_delivery_date + slot 结束时刻，转为 naive datetime（北京时区视图）。"""
    if not order.expected_delivery_date:
        return None
    parsed = parse_delivery_slot_hours(order.expected_delivery_slot)
    if not parsed:
        return None
    _, end_h = parsed
    base = datetime.combine(order.expected_delivery_date, datetime.min.time())
    return base + timedelta(hours=int(end_h))


async def _operation_user_id(db: AsyncSession) -> int:
    """超时是系统侧触发，记到任一运营账号下；找不到则用 0（兼容老数据）。"""
    user = await db.scalar(
        select(User).where(User.role == "operation").order_by(User.id.asc())
    )
    return int(user.id) if user else 0


async def _scan_once() -> None:
    async with SessionLocal() as db:
        now_bj = datetime.now(BEIJING_TZ).replace(tzinfo=None)
        rows = (
            await db.scalars(
                select(Order).where(Order.status.in_(PRE_DELIVERY_STATUSES))
            )
        ).all()
        if not rows:
            return
        actor_id = await _operation_user_id(db)
        hits: list[Order] = []
        for order in rows:
            end_dt = _slot_end_naive(order)
            if not end_dt:
                continue
            if end_dt > now_bj:
                continue
            hits.append(order)
        if not hits:
            return
        for order in hits:
            await ensure_delivery_overdue_ticket(db, order, actor_user_id=actor_id)
            now_iso = datetime.utcnow().isoformat()
            description = (
                f"订单 {order.order_no}：约定 "
                f"{order.expected_delivery_date} {order.expected_delivery_slot} 仍未送达"
            )
            existing_alert = await find_open_delivery_overdue_alert(db, int(order.id))
            if existing_alert is not None:
                # 同订单同 type 未关闭只保留一条；刷新描述与扫描元信息，不重复落库
                existing_alert.description = description
                payload = (
                    dict(existing_alert.payload_json)
                    if isinstance(existing_alert.payload_json, dict)
                    else {}
                )
                payload["status"] = order.status
                payload["last_seen_at"] = now_iso
                try:
                    payload["scan_count"] = int(payload.get("scan_count") or 0) + 1
                except (TypeError, ValueError):
                    payload["scan_count"] = 1
                existing_alert.payload_json = payload
            else:
                db.add(
                    Alert(
                        level="medium",
                        type="delivery_overdue",
                        description=description,
                        status="open",
                        payload_json={
                            "order_id": int(order.id),
                            "order_no": order.order_no,
                            "expected_delivery_date": order.expected_delivery_date.isoformat()
                            if order.expected_delivery_date
                            else None,
                            "expected_delivery_slot": order.expected_delivery_slot,
                            "status": order.status,
                            "first_seen_at": now_iso,
                            "last_seen_at": now_iso,
                            "scan_count": 1,
                        },
                    )
                )
            await write_audit_log(
                db=db,
                actor_user_id=actor_id,
                action="delivery_overdue_detected",
                category="order",
                object_type="order",
                object_id=int(order.id),
                detail=(
                    f"配送超时：订单 {order.order_no} 约定 "
                    f"{order.expected_delivery_date} {order.expected_delivery_slot} 仍未送达"
                ),
                after_json={
                    "order_no": order.order_no,
                    "current_status": order.status,
                    "ticket_prefix": DELIVERY_OVERDUE_PREFIX,
                },
            )
        await db.commit()


async def _scanner_loop() -> None:
    while True:
        try:
            await _scan_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — 扫描器不能因单次异常退出
            # 静默吞掉，避免任务整体退出；具体错误依赖日志体系
            pass
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def start_overdue_scanner() -> asyncio.Task:
    """供 main.lifespan 调用；返回 task 便于取消。"""
    task = asyncio.create_task(_scanner_loop())
    return task


async def stop_overdue_scanner(task: asyncio.Task | None) -> None:
    if not task:
        return
    task.cancel()
    with contextlib.suppress(Exception):
        await task
