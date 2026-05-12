from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, resolve_client_canteen_id_from_request
from models import Bill, BillingCycle, BillingStatement, Notification, Order, OrderItemAllocation, User
from schemas.billing import (
    BillingCycleCreateIn,
    BillingCycleOut,
    BillingCycleUpdateIn,
    BillingStatementConfirmIn,
    BillingStatementOut,
    BillingStatementSettleIn,
)
from services.billing_service import (
    RELATION_RULES,
    ensure_relation_billing_rule,
    relation_type_from_cycle,
)

router = APIRouter(prefix="/bills", tags=["bills"])


async def _client_bills_owner_clause(db: AsyncSession, user, request: Request):
    cid = await resolve_client_canteen_id_from_request(db, user, request)
    return and_(Order.client_id == user.id, Order.canteen_id == int(cid))


@router.get("")
async def list_my_bills(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    role = user.role if user.role in {"client", "delivery", "supplier", "factory"} else None
    if role is None:
        return []
    owner_clause = True
    if role == "client":
        owner_clause = await _client_bills_owner_clause(db, user, request)
    elif role == "delivery":
        owner_clause = Order.delivery_id == user.id
    elif role == "supplier":
        allocated_to_me = Order.id.in_(
            select(OrderItemAllocation.order_id).where(OrderItemAllocation.supplier_id == user.id).distinct()
        )
        owner_clause = or_(allocated_to_me, Order.supplier_id == user.id)
    elif role == "factory":
        owner_clause = Order.id.in_(
            select(OrderItemAllocation.order_id).where(OrderItemAllocation.supplier_id == user.id).distinct()
        )
    rows = (
        await db.scalars(
            select(Bill).join(Order, Order.id == Bill.order_id).where(Bill.role == role, owner_clause).order_by(Bill.id.desc())
        )
    ).all()
    if role == "supplier":
        rows = [row for row in rows if int((row.order_snapshot_json or {}).get("supplier_id") or 0) == int(user.id)]
    return rows


@router.get("/cycles", response_model=list[BillingCycleOut])
async def list_cycles(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"client", "delivery", "supplier", "factory", "operation", "monitor"}:
        return []
    if user.role in {"operation", "monitor"}:
        for relation_type in RELATION_RULES:
            await ensure_relation_billing_rule(db, relation_type)
        await db.commit()
        rows = (
            await db.scalars(
                select(BillingCycle)
                .where(BillingCycle.owner_user_id == 0, BillingCycle.scope_type == "relation_type")
                .order_by(BillingCycle.scope_ref_id.asc())
            )
        ).all()
        return [_serialize_cycle(row) for row in rows]
    rows = await db.scalars(select(BillingCycle).where(BillingCycle.owner_user_id == user.id).order_by(BillingCycle.id.desc()))
    return [_serialize_cycle(row) for row in rows.all()]


def _serialize_cycle(row: BillingCycle) -> dict:
    relation_type = relation_type_from_cycle(row)
    config = RELATION_RULES.get(relation_type, {})
    if relation_type:
        scope_label = "关系类型默认规则"
    elif row.scope_type == "counterparty":
        scope_label = "具体对手方"
    else:
        scope_label = row.scope_type
    return {
        "id": row.id,
        "cycle_code": row.cycle_code,
        "role": row.role,
        "owner_user_id": row.owner_user_id,
        "scope_type": row.scope_type,
        "scope_ref_id": row.scope_ref_id,
        "cycle_type": row.cycle_type,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "close_day": row.close_day,
        "confirm_due_days": row.confirm_due_days,
        "payment_due_days": row.payment_due_days,
        "is_active": row.is_active,
        "is_confirmed": row.is_confirmed,
        "created_at": row.created_at,
        "relation_type": relation_type or None,
        "display_title": config.get("title") or row.cycle_code,
        "relation_description": config.get("description"),
        "scope_label": scope_label,
    }


@router.get("/cycles/{cycle_id}", response_model=BillingCycleOut)
async def get_cycle(cycle_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    owner_clause = BillingCycle.owner_user_id == (0 if user.role in {"operation", "monitor"} else user.id)
    cycle = await db.scalar(select(BillingCycle).where(BillingCycle.id == cycle_id, owner_clause))
    if not cycle:
        raise HTTPException(404, "账期不存在")
    return _serialize_cycle(cycle)


@router.post("/cycles", response_model=BillingCycleOut)
async def create_cycle(payload: BillingCycleCreateIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    cycle = await ensure_relation_billing_rule(
        db,
        payload.relation_type,
        cycle_type=payload.cycle_type,
        close_day=payload.close_day,
        confirm_due_days=payload.confirm_due_days,
        payment_due_days=payload.payment_due_days,
    )
    cycle.cycle_type = payload.cycle_type
    cycle.close_day = payload.close_day
    cycle.confirm_due_days = payload.confirm_due_days
    cycle.payment_due_days = payload.payment_due_days
    cycle.is_active = True
    await db.commit()
    await db.refresh(cycle)
    return _serialize_cycle(cycle)


@router.put("/cycles/{cycle_id}", response_model=BillingCycleOut)
async def update_cycle(cycle_id: int, payload: BillingCycleUpdateIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    cycle = await db.scalar(
        select(BillingCycle).where(
            BillingCycle.id == cycle_id,
            BillingCycle.owner_user_id == 0,
            BillingCycle.scope_type == "relation_type",
        )
    )
    if not cycle:
        raise HTTPException(404, "账期不存在")
    if payload.cycle_type is not None:
        cycle.cycle_type = payload.cycle_type
    if payload.close_day is not None:
        cycle.close_day = payload.close_day
    if payload.confirm_due_days is not None:
        cycle.confirm_due_days = payload.confirm_due_days
    if payload.payment_due_days is not None:
        cycle.payment_due_days = payload.payment_due_days
    if payload.is_active is not None:
        cycle.is_active = payload.is_active
    await db.commit()
    await db.refresh(cycle)
    return _serialize_cycle(cycle)


@router.post("/cycles/{cycle_id}/confirm", response_model=BillingCycleOut)
async def confirm_cycle(cycle_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    cycle = await db.scalar(
        select(BillingCycle).where(
            BillingCycle.id == cycle_id,
            BillingCycle.owner_user_id == 0,
            BillingCycle.scope_type == "relation_type",
        )
    )
    if not cycle:
        raise HTTPException(404, "账期不存在")
    cycle.is_confirmed = True
    await db.commit()
    await db.refresh(cycle)
    return _serialize_cycle(cycle)


@router.delete("/testing/clear")
async def clear_billing_testing_data(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    operation_owner_ids = select(User.id).where(User.role.in_(["operation", "monitor"]))
    invalid_cycle_ids = (
        await db.scalars(
            select(BillingCycle.id).where(
                or_(
                    BillingCycle.scope_type == "canteen",
                    BillingCycle.owner_user_id.in_(operation_owner_ids),
                    and_(
                        BillingCycle.scope_type == "relation_type",
                        BillingCycle.scope_ref_id.notin_([int(v["scope_ref_id"]) for v in RELATION_RULES.values()]),
                    ),
                )
            )
        )
    ).all()
    if invalid_cycle_ids:
        await db.execute(delete(BillingStatement).where(BillingStatement.cycle_id.in_(invalid_cycle_ids)))
        await db.execute(delete(BillingCycle).where(BillingCycle.id.in_(invalid_cycle_ids)))
    await db.execute(delete(Notification).where(Notification.event_type.like("billing%")))
    await db.commit()
    return {"message": "无效账期数据已清理", "removed_cycles": len(invalid_cycle_ids)}


def _action_hint(row: BillingStatement) -> str:
    if row.status == "已结清":
        return "已完成结清"
    if row.direction == "应付":
        return "核对无误后，由你完成结清"
    return "等待对方完成结清，到账后系统会同步状态"


def _display_title(row: BillingStatement, counterparty_name: str) -> str:
    role = str(row.role or "")
    direction = str(row.direction or "")
    if role == "client" and direction == "应付":
        return "我应付给配送商"
    if role == "delivery" and direction == "应收":
        return "客户（食堂）待付给我"
    if role == "delivery" and direction == "应付":
        return "我应付给供货商/厂家"
    if role in {"supplier", "factory"} and direction == "应收":
        return "配送商待付给我"
    if row.direction == "应付":
        return f"我应付给{counterparty_name or '对方'}"
    return f"{counterparty_name or '对方'}待付给我"


def _same_statement_source(a: BillingStatement, b: BillingStatement) -> bool:
    a_ids = (a.source_snapshot_json or {}).get("order_ids") or []
    b_ids = (b.source_snapshot_json or {}).get("order_ids") or []
    return sorted(map(int, a_ids)) == sorted(map(int, b_ids))


async def _serialize_statements(db: AsyncSession, rows: list[BillingStatement]) -> list[dict]:
    counterparty_ids = sorted({int(row.counterparty_user_id) for row in rows if row.counterparty_user_id})
    users = (await db.scalars(select(User).where(User.id.in_(counterparty_ids)))).all() if counterparty_ids else []
    user_map = {int(u.id): u for u in users}
    out: list[dict] = []
    for row in rows:
        cp = user_map.get(int(row.counterparty_user_id))
        counterparty_name = (cp.company_name or cp.username) if cp else (row.source_snapshot_json or {}).get("counterparty_name", "")
        snapshot = row.source_snapshot_json or {}
        out.append(
            {
                "id": row.id,
                "statement_no": row.statement_no,
                "cycle_id": row.cycle_id,
                "role": row.role,
                "owner_user_id": row.owner_user_id,
                "counterparty_user_id": row.counterparty_user_id,
                "direction": row.direction,
                "status": row.status,
                "amount": row.amount,
                "confirmed_amount": row.confirmed_amount,
                "settled_amount": row.settled_amount,
                "item_count": row.item_count,
                "source_snapshot_json": snapshot,
                "cycle_snapshot_json": row.cycle_snapshot_json,
                "remark": row.remark,
                "confirmed_at": row.confirmed_at,
                "due_at": row.due_at,
                "created_at": row.created_at,
                "counterparty_name": counterparty_name,
                "counterparty_role": (cp.role if cp else snapshot.get("counterparty_role")),
                "display_title": _display_title(row, counterparty_name),
                "action_hint": _action_hint(row),
                "order_numbers": snapshot.get("order_numbers") or [],
            }
        )
    return out


@router.get("/statements", response_model=list[BillingStatementOut])
async def list_statements(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"client", "delivery", "supplier", "factory", "operation", "monitor"}:
        return []
    stmt = select(BillingStatement).where(BillingStatement.owner_user_id == user.id)
    if user.role in {"client", "delivery", "supplier", "factory"}:
        stmt = stmt.where(BillingStatement.role == user.role)
    rows = await db.scalars(stmt.order_by(BillingStatement.id.desc()))
    return await _serialize_statements(db, rows.all())


@router.get("/statements/{statement_id}", response_model=BillingStatementOut)
async def get_statement(statement_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(BillingStatement).where(BillingStatement.id == statement_id, BillingStatement.owner_user_id == user.id))
    if not row:
        raise HTTPException(404, "账单不存在")
    return (await _serialize_statements(db, [row]))[0]


@router.post("/statements/{statement_id}/confirm", response_model=BillingStatementOut)
async def confirm_statement(statement_id: int, payload: BillingStatementConfirmIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(BillingStatement).where(BillingStatement.id == statement_id, BillingStatement.owner_user_id == user.id))
    if not row:
        raise HTTPException(404, "账单不存在")
    if row.status == "已结清":
        raise HTTPException(400, "已结清账单不可再次确认")
    row.status = "已确认"
    row.confirmed_amount = row.amount
    row.confirmed_at = row.confirmed_at or datetime.utcnow()
    row.remark = (payload.remark or row.remark or "").strip()
    db.add(Notification(event_type="billing_confirmed", title="账单已确认", content=f"账单 {row.statement_no} 已确认，请安排后续结清。", role=user.role, target_user_id=int(user.id), canteen_id=None, object_type="billing_statement", object_id=int(row.id), route="/bills", is_read=False))
    await db.commit()
    await db.refresh(row)
    return (await _serialize_statements(db, [row]))[0]


@router.post("/statements/{statement_id}/settle", response_model=BillingStatementOut)
async def settle_statement(statement_id: int, payload: BillingStatementSettleIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(BillingStatement).where(BillingStatement.id == statement_id, BillingStatement.owner_user_id == user.id))
    if not row:
        raise HTTPException(404, "账单不存在")
    if row.direction != "应付":
        raise HTTPException(403, "收款账单由付款方结清，你可以查看到账状态")
    if row.status == "已结清":
        raise HTTPException(400, "账单已结清")
    remaining = Decimal(str(row.amount or 0)) - Decimal(str(row.settled_amount or 0))
    if payload.amount > remaining:
        raise HTTPException(400, "结清金额不能超过剩余未结金额")
    row.settled_amount = Decimal(str(row.settled_amount or 0)) + payload.amount
    row.status = "已结清" if row.settled_amount >= row.amount else "部分结清"
    row.remark = (payload.remark or row.remark or "").strip()
    mirror_rows = (
        await db.scalars(
            select(BillingStatement).where(
                BillingStatement.owner_user_id == row.counterparty_user_id,
                BillingStatement.counterparty_user_id == row.owner_user_id,
                BillingStatement.direction == "应收",
                BillingStatement.amount == row.amount,
            )
        )
    ).all()
    for mirror in mirror_rows:
        if not _same_statement_source(row, mirror):
            continue
        mirror.settled_amount = row.settled_amount
        mirror.status = row.status
        mirror.remark = row.remark
    db.add(Notification(event_type="billing_settled", title="账单已结清", content=f"账单 {row.statement_no} 已完成结清。", role=user.role, target_user_id=int(user.id), canteen_id=None, object_type="billing_statement", object_id=int(row.id), route="/bills", is_read=False))
    await db.commit()
    await db.refresh(row)
    return (await _serialize_statements(db, [row]))[0]


@router.post("/demo/generate")
async def generate_demo_statements(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    raise HTTPException(410, "账单必须由真实订单收货确认后生成，不能手工生成演示账单")
