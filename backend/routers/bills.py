import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, resolve_client_canteen_id_from_request
from models import Bill, BillingCycle, BillingStatement, ClientCanteen, Notification, Order, OrderItemAllocation, ReconciliationStatement, User
from schemas.billing import (
    BillingCycleCreateIn,
    BillingCycleOut,
    BillingCycleUpdateIn,
    BillingStatementConfirmIn,
    BillingStatementOut,
    BillingStatementSettleIn,
    TargetedCycleCreateIn,
    TargetedCycleUpdateIn,
)
from services.billing_service import (
    RELATION_RULES,
    _is_reversal_statement,
    _recon_canteen_cond,
    billing_route_for_role,
    compute_billing_period,
    ensure_default_billing_cycle,
    ensure_relation_billing_rule,
    relation_type_from_cycle,
    summarize_overdue,
)
from services.billing_followup_scanner import (
    close_billing_confirm_overdue_tickets_if_confirmed,
    close_billing_overdue_tickets_if_settled,
)

router = APIRouter(prefix="/bills", tags=["bills"])


def _extract_statement_order_ids(snapshot: dict | None) -> list[int]:
    """从对账单快照解析订单 id（兼容 order_ids 与 orders[].order_id）。"""
    snap = snapshot or {}
    out: list[int] = []
    for x in snap.get("order_ids") or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    for o in snap.get("orders") or []:
        if isinstance(o, dict) and o.get("order_id") is not None:
            try:
                out.append(int(o["order_id"]))
            except (TypeError, ValueError):
                continue
    return list(dict.fromkeys(out))


async def _client_statement_belongs_to_canteen(
    db: AsyncSession,
    row: BillingStatement,
    *,
    user_id: int,
    canteen_id: int,
) -> bool:
    """对账单内订单是否全部属于本校且均为同一食堂（用于采购端「仅当前食堂」视图）。"""
    ids = _extract_statement_order_ids(row.source_snapshot_json)
    if not ids:
        return False
    orders = (await db.scalars(select(Order).where(Order.id.in_(ids)))).all()
    if len(orders) != len(ids):
        return False
    canteen_ids: set[int] = set()
    for o in orders:
        if int(o.client_id) != int(user_id):
            return False
        if o.canteen_id is None:
            return False
        canteen_ids.add(int(o.canteen_id))
    return canteen_ids == {int(canteen_id)}


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


# ============ 定向账期规则（按 学校×食堂×配送商 / 配送商×供货商 颗粒化）============
# 注意：必须注册在 /cycles/{cycle_id} 之前，否则 "targeted" 会被当作路径参数。


def _targeted_relation_type(row: BillingCycle, counterparty_role: str | None) -> Optional[str]:
    """归一化规则的关系类型：client 侧→client_delivery；delivery×(supplier|factory)→delivery_supplier。
    其余（历史镜像侧派生的孤儿规则）返回 None，不再参与管理。"""
    if row.role == "client":
        return "client_delivery"
    if row.role == "delivery" and (counterparty_role or "") in {"supplier", "factory"}:
        return "delivery_supplier"
    return None


def _serialize_targeted_cycle(
    row: BillingCycle,
    relation_type: str,
    owner: User | None,
    counterparty: User | None,
    canteen_name: str | None,
) -> dict:
    def _name(u: User | None) -> str:
        return (u.company_name or u.username) if u else ""

    return {
        "id": int(row.id),
        "cycle_code": row.cycle_code,
        "relation_type": relation_type,
        "relation_title": (RELATION_RULES.get(relation_type) or {}).get("title") or relation_type,
        "owner_user_id": int(row.owner_user_id),
        "owner_name": _name(owner),
        "counterparty_user_id": int(row.scope_ref_id),
        "counterparty_name": _name(counterparty),
        "canteen_id": int(row.canteen_id) if row.canteen_id is not None else None,
        "canteen_name": canteen_name or "",
        "cycle_type": row.cycle_type,
        "cycle_type_label": _CYCLE_LABEL.get(row.cycle_type, row.cycle_type),
        "close_day": int(row.close_day),
        "confirm_due_days": int(row.confirm_due_days),
        "payment_due_days": int(row.payment_due_days),
        "is_customized": bool(row.is_customized),
        "follow_label": "已定制" if row.is_customized else "跟随全局",
    }


async def _load_targeted_cycle_context(db: AsyncSession, rows: list) -> tuple[dict, dict]:
    uids = sorted({int(r.owner_user_id) for r in rows} | {int(r.scope_ref_id) for r in rows})
    users = (await db.scalars(select(User).where(User.id.in_(uids)))).all() if uids else []
    umap = {int(u.id): u for u in users}
    cmap = await _canteen_name_map(db, rows)
    return umap, cmap


@router.get("/cycles/targeted")
async def list_targeted_cycles(
    relation_type: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """运营端：列出已派生/已定制的定向账期规则（未定制的展示为「跟随全局」）。"""
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    rows = (
        await db.scalars(
            select(BillingCycle)
            .where(BillingCycle.scope_type == "counterparty", BillingCycle.is_active.is_(True))
            .order_by(BillingCycle.id.desc())
        )
    ).all()
    umap, cmap = await _load_targeted_cycle_context(db, rows)
    out = []
    for r in rows:
        cp = umap.get(int(r.scope_ref_id))
        relation = _targeted_relation_type(r, cp.role if cp else None)
        if relation is None:
            continue
        if relation_type and relation != relation_type:
            continue
        owner = umap.get(int(r.owner_user_id))
        cname = cmap.get(int(r.canteen_id)) if r.canteen_id is not None else None
        item = _serialize_targeted_cycle(r, relation, owner, cp, cname)
        if keyword and all(
            keyword not in (item.get(k) or "") for k in ("owner_name", "counterparty_name", "canteen_name")
        ):
            continue
        out.append(item)
    return out


async def _get_targeted_cycle_or_404(db: AsyncSession, cycle_id: int) -> BillingCycle:
    row = await db.scalar(
        select(BillingCycle).where(
            BillingCycle.id == int(cycle_id),
            BillingCycle.scope_type == "counterparty",
            BillingCycle.is_active.is_(True),
        )
    )
    if not row:
        raise HTTPException(404, "定向账期规则不存在")
    return row


async def _serialize_one_targeted(db: AsyncSession, row: BillingCycle) -> dict:
    umap, cmap = await _load_targeted_cycle_context(db, [row])
    cp = umap.get(int(row.scope_ref_id))
    relation = _targeted_relation_type(row, cp.role if cp else None) or ""
    cname = cmap.get(int(row.canteen_id)) if row.canteen_id is not None else None
    return _serialize_targeted_cycle(row, relation, umap.get(int(row.owner_user_id)), cp, cname)


@router.post("/cycles/targeted")
async def create_targeted_cycle(
    payload: TargetedCycleCreateIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """运营端预配置定向规则（出账前即可定制；创建即视为已定制）。"""
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    owner = await db.get(User, int(payload.owner_user_id))
    cp = await db.get(User, int(payload.counterparty_user_id))
    if payload.relation_type == "client_delivery":
        if not owner or owner.role != "client" or not cp or cp.role != "delivery":
            raise HTTPException(400, "client_delivery 规则需选择 客户 与 配送商")
        if not payload.canteen_id:
            raise HTTPException(400, "client_delivery 规则需指定食堂")
        canteen = await db.scalar(
            select(ClientCanteen).where(
                ClientCanteen.id == int(payload.canteen_id),
                ClientCanteen.school_client_id == int(owner.id),
            )
        )
        if not canteen:
            raise HTTPException(400, "食堂不存在或不属于该客户")
        canteen_id = int(payload.canteen_id)
        role = "client"
    else:
        if not owner or owner.role != "delivery" or not cp or cp.role not in {"supplier", "factory"}:
            raise HTTPException(400, "delivery_supplier 规则需选择 配送商 与 供货商/厂家")
        if payload.canteen_id:
            raise HTTPException(400, "供货腿规则不区分食堂")
        canteen_id = None
        role = "delivery"
    row = await ensure_default_billing_cycle(
        db,
        owner_user_id=int(owner.id),
        role=role,
        scope_type="counterparty",
        scope_ref_id=int(cp.id),
        canteen_id=canteen_id,
    )
    row.cycle_type = payload.cycle_type
    row.close_day = payload.close_day
    row.confirm_due_days = payload.confirm_due_days
    row.payment_due_days = payload.payment_due_days
    row.is_customized = True
    await db.commit()
    await db.refresh(row)
    return await _serialize_one_targeted(db, row)


@router.put("/cycles/targeted/{cycle_id}")
async def update_targeted_cycle(
    cycle_id: int, payload: TargetedCycleUpdateIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """编辑定向规则参数 → 标记已定制，不再跟随全局。"""
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    row = await _get_targeted_cycle_or_404(db, cycle_id)
    if payload.cycle_type is not None:
        row.cycle_type = payload.cycle_type
    if payload.close_day is not None:
        row.close_day = payload.close_day
    if payload.confirm_due_days is not None:
        row.confirm_due_days = payload.confirm_due_days
    if payload.payment_due_days is not None:
        row.payment_due_days = payload.payment_due_days
    row.is_customized = True
    await db.commit()
    await db.refresh(row)
    return await _serialize_one_targeted(db, row)


@router.post("/cycles/targeted/{cycle_id}/follow-global")
async def follow_global_targeted_cycle(
    cycle_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """恢复跟随全局：清除定制标记并立即同步全局参数。"""
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    row = await _get_targeted_cycle_or_404(db, cycle_id)
    cp = await db.get(User, int(row.scope_ref_id))
    relation = _targeted_relation_type(row, cp.role if cp else None)
    if not relation:
        raise HTTPException(400, "该规则不属于可管理的结算关系")
    rule = await ensure_relation_billing_rule(db, relation)
    row.is_customized = False
    row.cycle_type = rule.cycle_type
    row.close_day = rule.close_day
    row.confirm_due_days = rule.confirm_due_days
    row.payment_due_days = rule.payment_due_days
    await db.commit()
    await db.refresh(row)
    return await _serialize_one_targeted(db, row)


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


def _cycle_type_label(value: str | None) -> str:
    return {"daily": "按天结算", "weekly": "按周结算", "monthly": "按月结算"}.get(value or "", value or "")


def _money_text(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    text = format(amount, "f").rstrip("0").rstrip(".")
    return f"¥{text or '0'}"


def _statement_counterparty_name(row: BillingStatement, counterparty: User | None = None) -> str:
    if counterparty:
        return counterparty.company_name or counterparty.username or ""
    return (row.source_snapshot_json or {}).get("counterparty_name") or ""


def _statement_order_numbers(row: BillingStatement) -> str:
    numbers = (row.source_snapshot_json or {}).get("order_numbers") or []
    return "、".join(str(x) for x in numbers if x) or "—"


async def _add_billing_notification_once(
    db: AsyncSession,
    *,
    event_type: str,
    title: str,
    content: str,
    role: str,
    target_user_id: int,
    object_id: int,
    route: str,
) -> None:
    since = datetime.utcnow() - timedelta(minutes=5)
    existing = await db.scalar(
        select(Notification.id)
        .where(
            Notification.event_type == event_type,
            Notification.target_user_id == int(target_user_id),
            Notification.object_type == "billing_statement",
            Notification.object_id == int(object_id),
            Notification.created_at >= since,
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
            role=role,
            target_user_id=int(target_user_id),
            canteen_id=None,
            object_type="billing_statement",
            object_id=int(object_id),
            route=route,
            is_read=False,
        )
    )


def _confirmed_content(row: BillingStatement, *, peer: bool, counterparty_name: str) -> str:
    next_step = "等待对方付款" if row.direction == "应收" else "安排付款"
    prefix = "对方已确认账单" if peer else "账单已确认"
    return f"{prefix}｜金额：{_money_text(row.amount)}｜对方：{counterparty_name or '—'}｜下一步：{next_step}"


def _settled_content(row: BillingStatement, *, counterparty_name: str) -> str:
    return (
        f"金额：{_money_text(row.amount)}｜对方：{counterparty_name or '—'}｜"
        f"关联订单：{_statement_order_numbers(row)}"
    )


async def _serialize_statements(db: AsyncSession, rows: list[BillingStatement]) -> list[dict]:
    counterparty_ids = sorted({int(row.counterparty_user_id) for row in rows if row.counterparty_user_id})
    users = (await db.scalars(select(User).where(User.id.in_(counterparty_ids)))).all() if counterparty_ids else []
    user_map = {int(u.id): u for u in users}
    cycle_ids = sorted({int(row.cycle_id) for row in rows if row.cycle_id})
    cycles = (await db.scalars(select(BillingCycle).where(BillingCycle.id.in_(cycle_ids)))).all() if cycle_ids else []
    cycle_map = {int(c.id): c for c in cycles}
    today = date.today()
    out: list[dict] = []
    for row in rows:
        cp = user_map.get(int(row.counterparty_user_id))
        counterparty_name = (cp.company_name or cp.username) if cp else (row.source_snapshot_json or {}).get("counterparty_name", "")
        snapshot = row.source_snapshot_json or {}
        is_reversal = snapshot.get("kind") == "return_reversal"
        cycle = cycle_map.get(int(row.cycle_id or 0))
        period = compute_billing_period(row.created_at or datetime.utcnow(), cycle) if cycle else {}
        amount = float(row.amount or 0)
        settled = float(row.settled_amount or 0)
        status = str(row.status or "")
        confirm_due = period.get("confirm_due_date")
        payment_due = period.get("payment_due_date")
        overdue_confirm = False
        overdue_payment = False
        if confirm_due:
            overdue_confirm = status == "待确认" and today > date.fromisoformat(confirm_due)
        if payment_due:
            overdue_payment = status in {"已确认", "部分结清"} and today > date.fromisoformat(payment_due)
        out.append(
            {
                "id": row.id,
                "statement_no": row.statement_no,
                "cycle_id": row.cycle_id,
                "role": row.role,
                "owner_user_id": row.owner_user_id,
                "counterparty_user_id": row.counterparty_user_id,
                "canteen_id": row.canteen_id,
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
                "is_reversal": is_reversal,
                "display_title": "退货红冲（冲减）" if is_reversal else _display_title(row, counterparty_name),
                "action_hint": "退货冲减，自动抵减应付/应收净额" if is_reversal else _action_hint(row),
                "order_numbers": snapshot.get("order_numbers") or [],
                **period,
                "cycle_type_label": _cycle_type_label(period.get("cycle_type")),
                "amount": amount,
                "settled_amount": settled,
                "confirmed_amount": float(row.confirmed_amount or 0),
                "unsettled_amount": max(0.0, amount - settled),
                "overdue_confirm": overdue_confirm,
                "overdue_payment": overdue_payment,
            }
        )
    return out


def _apply_statement_filters(
    rows: list[dict],
    *,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    period_label: Optional[str] = None,
    counterparty_keyword: Optional[str] = None,
    keyword: Optional[str] = None,
    overdue: Optional[str] = None,
    relation_type: Optional[str] = None,
    cycle_id: Optional[int] = None,
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    statuses: Optional[list[str]] = None,
) -> list[dict]:
    out = rows
    if direction:
        out = [r for r in out if str(r.get("direction") or "") == direction]
    if status:
        out = [r for r in out if str(r.get("status") or "") == status]
    if statuses:
        sset = {s for s in statuses if s}
        if sset:
            out = [r for r in out if str(r.get("status") or "") in sset]
    if period_label:
        out = [r for r in out if str(r.get("period_label") or "") == period_label]
    if counterparty_keyword:
        kw = counterparty_keyword.strip().lower()
        out = [r for r in out if kw in str(r.get("counterparty_name") or "").lower()]
    if keyword:
        kw = keyword.strip().lower()
        out = [
            r for r in out
            if kw in str(r.get("statement_no") or "").lower()
            or any(kw in str(no).lower() for no in (r.get("order_numbers") or []))
        ]
    if overdue:
        val = overdue.strip().lower()
        if val in {"1", "true", "yes", "all"}:
            out = [r for r in out if r.get("overdue_confirm") or r.get("overdue_payment")]
        elif val == "confirm":
            out = [r for r in out if r.get("overdue_confirm")]
        elif val == "payment":
            out = [r for r in out if r.get("overdue_payment")]
    if relation_type:
        rt = relation_type.strip()
        out = [r for r in out if (r.get("source_snapshot_json") or {}).get("relation_type") == rt]
    if cycle_id is not None:
        out = [r for r in out if int(r.get("cycle_id") or 0) == int(cycle_id)]
    if period_from:
        try:
            d_from = date.fromisoformat(period_from)
            out = [
                r for r in out
                if r.get("period_start") and date.fromisoformat(r["period_start"]) >= d_from
            ]
        except ValueError:
            pass
    if period_to:
        try:
            d_to = date.fromisoformat(period_to)
            out = [
                r for r in out
                if r.get("period_start") and date.fromisoformat(r["period_start"]) <= d_to
            ]
        except ValueError:
            pass
    return out


@router.get("/statements", response_model=list[BillingStatementOut])
async def list_statements(
    request: Request,
    statement_scope: Optional[str] = Query(
        None,
        description="仅采购端 client 生效：current_canteen=仅当前 JWT 食堂；school_merged=本校全部食堂合并。缺省按 current_canteen。",
    ),
    direction: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    period_label: Optional[str] = Query(None),
    counterparty_keyword: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    overdue: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in {"client", "delivery", "supplier", "factory", "operation", "monitor"}:
        return []
    stmt = select(BillingStatement).where(BillingStatement.owner_user_id == user.id)
    if user.role in {"client", "delivery", "supplier", "factory"}:
        stmt = stmt.where(BillingStatement.role == user.role)
    rows = (await db.scalars(stmt.order_by(BillingStatement.id.desc()))).all()
    if user.role == "client":
        scope = (statement_scope or "current_canteen").strip().lower()
        if scope not in ("current_canteen", "school_merged"):
            scope = "current_canteen"
        if scope == "current_canteen":
            cid = await resolve_client_canteen_id_from_request(db, user, request)
            # 新：账单已带 canteen_id，直接按列过滤；兼容历史无 canteen_id 的账单（fall back 到订单反查）
            rows_with_cid = [r for r in rows if r.canteen_id is not None]
            legacy_rows = [r for r in rows if r.canteen_id is None]
            filtered = [r for r in rows_with_cid if int(r.canteen_id) == int(cid)]
            if legacy_rows:
                for row in legacy_rows:
                    if await _client_statement_belongs_to_canteen(
                        db, row, user_id=int(user.id), canteen_id=int(cid)
                    ):
                        filtered.append(row)
            rows = filtered
    serialized = await _serialize_statements(db, rows)
    return _apply_statement_filters(
        serialized,
        direction=direction,
        status=status,
        period_label=period_label,
        counterparty_keyword=counterparty_keyword,
        keyword=keyword,
        overdue=overdue,
    )


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
    was_confirmed = row.status == "已确认"
    row.status = "已确认"
    row.confirmed_amount = row.amount
    row.confirmed_at = row.confirmed_at or datetime.utcnow()
    row.remark = (payload.remark or row.remark or "").strip()
    # 镜像同步对方应收账单，避免应收方仍看到「待确认」
    mirror_direction = "应收" if row.direction == "应付" else "应付"
    mirror_rows = (
        await db.scalars(
            select(BillingStatement).where(
                BillingStatement.owner_user_id == row.counterparty_user_id,
                BillingStatement.counterparty_user_id == row.owner_user_id,
                BillingStatement.direction == mirror_direction,
                BillingStatement.amount == row.amount,
            )
        )
    ).all()
    for mirror in mirror_rows:
        if not _same_statement_source(row, mirror):
            continue
        if mirror.status == "待确认":
            mirror.status = "已确认"
            mirror.confirmed_amount = mirror.amount
            mirror.confirmed_at = row.confirmed_at
        await close_billing_confirm_overdue_tickets_if_confirmed(db, int(mirror.id))
    await close_billing_confirm_overdue_tickets_if_confirmed(db, int(row.id))
    counterparty = await db.get(User, int(row.counterparty_user_id))
    if not was_confirmed:
        cp_name = _statement_counterparty_name(row, counterparty)
        await _add_billing_notification_once(
            db,
            event_type="billing_confirmed",
            title="账单已确认",
            content=_confirmed_content(row, peer=False, counterparty_name=cp_name),
            role=user.role,
            target_user_id=int(user.id),
            object_id=int(row.id),
            route=billing_route_for_role(user.role),
        )
        if counterparty:
            await _add_billing_notification_once(
                db,
                event_type="billing_confirmed_by_peer",
                title="账单已确认",
                content=_confirmed_content(row, peer=True, counterparty_name=user.company_name or user.username or ""),
                role=counterparty.role,
                target_user_id=int(counterparty.id),
                object_id=int(row.id),
                route=billing_route_for_role(counterparty.role),
            )
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
        if mirror.status == "已结清":
            await close_billing_overdue_tickets_if_settled(db, int(mirror.id))
    if row.status == "已结清":
        await close_billing_overdue_tickets_if_settled(db, int(row.id))
    counterparty = await db.get(User, int(row.counterparty_user_id))
    cp_name = _statement_counterparty_name(row, counterparty)
    await _add_billing_notification_once(
        db,
        event_type="billing_settled",
        title="账单已结清" if row.status == "已结清" else "账单已部分付款",
        content=_settled_content(row, counterparty_name=cp_name),
        role=user.role,
        target_user_id=int(user.id),
        object_id=int(row.id),
        route=billing_route_for_role(user.role),
    )
    # 通知对手方：对方已结清/部分付款
    if counterparty:
        peer_title = "对方已结清账单" if row.status == "已结清" else "对方已部分付款"
        peer_content = (
            _settled_content(row, counterparty_name=user.company_name or user.username or "")
            if row.status == "已结清"
            else f"对方已部分付款账单 {row.statement_no}：本次 ¥{payload.amount}，累计已结 ¥{row.settled_amount}/¥{row.amount}。"
        )
        await _add_billing_notification_once(
            db,
            event_type="billing_settled_by_peer",
            title=peer_title,
            content=peer_content,
            role=counterparty.role,
            target_user_id=int(counterparty.id),
            object_id=int(row.id),
            route=billing_route_for_role(counterparty.role),
        )
    await db.commit()
    await db.refresh(row)
    return (await _serialize_statements(db, [row]))[0]


@router.post("/demo/generate")
async def generate_demo_statements(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(status_code=403, detail="无权限")
    raise HTTPException(410, "账单必须由真实订单收货确认后生成，不能手工生成演示账单")


def _enrich_with_period(serialized: list[dict], cycle_map: dict[int, BillingCycle]) -> list[dict]:
    out: list[dict] = []
    for r in serialized:
        cycle = cycle_map.get(int(r.get("cycle_id") or 0))
        if not cycle:
            continue
        period = compute_billing_period(r.get("created_at") or datetime.utcnow(), cycle)
        amount = float(r.get("amount") or 0)
        settled = float(r.get("settled_amount") or 0)
        out.append(
            {
                **r,
                **period,
                "amount": amount,
                "settled_amount": settled,
                "confirmed_amount": float(r.get("confirmed_amount") or 0),
                "unsettled_amount": max(0.0, amount - settled),
            }
        )
    return out


@router.get("/statements-grouped")
async def list_statements_grouped(
    request: Request,
    statement_scope: Optional[str] = Query(None, description="同 /bills/statements"),
    direction: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    period_label: Optional[str] = Query(None),
    counterparty_keyword: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    overdue: Optional[str] = Query(None),
    relation_type: Optional[str] = Query(None, description="client_delivery | delivery_supplier；运营端按结算关系链拆开看"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按账期+方向聚合返回，便于「按账期对账」视图。"""
    if user.role not in {"client", "delivery", "supplier", "factory", "operation", "monitor"}:
        return []
    stmt = select(BillingStatement)
    if user.role in {"client", "delivery", "supplier", "factory"}:
        stmt = stmt.where(BillingStatement.owner_user_id == user.id, BillingStatement.role == user.role)
    rows = (await db.scalars(stmt.order_by(BillingStatement.id.desc()))).all()
    if user.role == "client":
        scope = (statement_scope or "current_canteen").strip().lower()
        if scope not in ("current_canteen", "school_merged"):
            scope = "current_canteen"
        if scope == "current_canteen":
            cid = await resolve_client_canteen_id_from_request(db, user, request)
            rows_with_cid = [r for r in rows if r.canteen_id is not None]
            legacy_rows = [r for r in rows if r.canteen_id is None]
            filtered = [r for r in rows_with_cid if int(r.canteen_id) == int(cid)]
            if legacy_rows:
                for row in legacy_rows:
                    if await _client_statement_belongs_to_canteen(
                        db, row, user_id=int(user.id), canteen_id=int(cid)
                    ):
                        filtered.append(row)
            rows = filtered
    serialized = await _serialize_statements(db, rows)
    enriched = _apply_statement_filters(
        serialized,
        direction=direction,
        status=status,
        period_label=period_label,
        counterparty_keyword=counterparty_keyword,
        keyword=keyword,
        overdue=overdue,
        relation_type=relation_type,
    )

    today = date.today()
    groups: dict[tuple, dict] = {}
    for r in enriched:
        key = (r["period_label"], r["direction"])
        g = groups.setdefault(
            key,
            {
                "period_label": r["period_label"],
                "period_start": r["period_start"],
                "period_end": r["period_end"],
                "close_at": r["close_at"],
                "confirm_due_date": r.get("confirm_due_date"),
                "payment_due_date": r.get("payment_due_date"),
                "direction": r["direction"],
                "cycle_type": r["cycle_type"],
                "cycle_type_label": r.get("cycle_type_label"),
                "total_amount": 0.0,
                "settled_amount": 0.0,
                "unsettled_amount": 0.0,
                "statement_count": 0,
                "overdue_count": 0,
                "statements": [],
            },
        )
        g["total_amount"] += r["amount"]
        g["settled_amount"] += r["settled_amount"]
        g["unsettled_amount"] += r["unsettled_amount"]
        g["statement_count"] += 1
        if r["status"] != "已结清":
            try:
                if today > date.fromisoformat(r["payment_due_date"]):
                    g["overdue_count"] += 1
            except ValueError:
                pass
        g["statements"].append(r)
    return sorted(groups.values(), key=lambda x: (x["period_end"], x["direction"]), reverse=True)


# ============ 对账单（月结合并单：按 对手方×账期 聚合）============

_CYCLE_LABEL = {"daily": "按天结算", "weekly": "按周结算", "monthly": "按月结算"}


async def _recompute_reconciliation(db: AsyncSession, recon: ReconciliationStatement) -> None:
    """以成员明细为准重算对账单合计与笔数；过关账日的进行中对账单懒锁定为待确认。
    口径：total=非红冲成员之和（毛额），adjust=红冲成员之和，净额=total+adjust。"""
    members = (
        await db.scalars(
            select(BillingStatement).where(BillingStatement.reconciliation_id == int(recon.id))
        )
    ).all()
    recon.total_amount = sum(
        (Decimal(str(m.amount or 0)) for m in members if not _is_reversal_statement(m)), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    recon.adjust_amount = sum(
        (Decimal(str(m.amount or 0)) for m in members if _is_reversal_statement(m)), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    recon.item_count = len(members)
    if recon.status == "进行中" and recon.close_at and recon.close_at < date.today():
        recon.status = "待确认"
        recon.locked_at = recon.locked_at or datetime.utcnow()


async def _canteen_name_map(db: AsyncSession, recons) -> dict[int, str]:
    """批量取对账单关联食堂名（client↔delivery 腿按食堂一张，卡片要显示食堂）。"""
    ids = sorted({int(r.canteen_id) for r in recons if r.canteen_id is not None})
    if not ids:
        return {}
    rows = (await db.scalars(select(ClientCanteen).where(ClientCanteen.id.in_(ids)))).all()
    return {int(c.id): c.name for c in rows}


def _serialize_reconciliation(
    recon: ReconciliationStatement, counterparty: User | None, canteen_name: str | None = None
) -> dict:
    cycle = None  # cycle_type label 由 period_label 形态推断不可靠，直接用 cycle_type 快照不存于此，取关系默认
    total = Decimal(str(recon.total_amount or 0))
    adjust = Decimal(str(recon.adjust_amount or 0))
    settled = Decimal(str(recon.settled_amount or 0))
    payable = (total + adjust)
    unsettled = (payable - settled)
    overdue = bool(
        recon.status != "已结清"
        and recon.payment_due_date
        and date.today() > recon.payment_due_date
    )
    cp_name = (counterparty.company_name or counterparty.username) if counterparty else ""
    return {
        "id": int(recon.id),
        "statement_no": recon.statement_no,
        "relation_type": recon.relation_type,
        "role": recon.role,
        "direction": recon.direction,
        "period_label": recon.period_label,
        "status": recon.status,
        "counterparty_id": int(recon.counterparty_user_id),
        "counterparty_name": cp_name,
        "canteen_id": int(recon.canteen_id) if recon.canteen_id is not None else None,
        "canteen_name": canteen_name or "",
        "total_amount": float(total),
        "adjust_amount": float(adjust),
        "payable_amount": float(payable),
        "settled_amount": float(settled),
        "unsettled_amount": float(unsettled),
        "item_count": int(recon.item_count or 0),
        "close_at": recon.close_at.isoformat() if recon.close_at else None,
        "confirm_due_date": recon.confirm_due_date.isoformat() if recon.confirm_due_date else None,
        "payment_due_date": recon.payment_due_date.isoformat() if recon.payment_due_date else None,
        "overdue": overdue,
        "locked": recon.status != "进行中",
    }


async def _cascade_members(db: AsyncSession, recon_id: int, *, status: str, full_settle: bool) -> None:
    members = (
        await db.scalars(select(BillingStatement).where(BillingStatement.reconciliation_id == int(recon_id)))
    ).all()
    for m in members:
        if m.status == "已结清":
            continue
        if status == "已确认" and m.status == "待确认":
            m.status = "已确认"
            m.confirmed_amount = m.amount
            m.confirmed_at = m.confirmed_at or datetime.utcnow()
        elif status in ("部分结清", "已结清"):
            if m.status == "待确认":
                m.status = "已确认"
                m.confirmed_amount = m.amount
                m.confirmed_at = m.confirmed_at or datetime.utcnow()
            if full_settle:
                m.status = "已结清"
                m.settled_amount = m.amount
            else:
                m.status = "部分结清"


async def _mirror_reconciliation(db: AsyncSession, recon: ReconciliationStatement) -> Optional[ReconciliationStatement]:
    if recon.mirror_id:
        m = await db.get(ReconciliationStatement, int(recon.mirror_id))
        if m:
            return m
    opp = "应收" if recon.direction == "应付" else "应付"
    return await db.scalar(
        select(ReconciliationStatement).where(
            ReconciliationStatement.owner_user_id == int(recon.counterparty_user_id),
            ReconciliationStatement.counterparty_user_id == int(recon.owner_user_id),
            ReconciliationStatement.relation_type == recon.relation_type,
            ReconciliationStatement.direction == opp,
            ReconciliationStatement.period_label == recon.period_label,
            _recon_canteen_cond(recon.canteen_id),
        )
    )


@router.get("/reconciliations")
async def list_reconciliations(
    request: Request,
    direction: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    period_label: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    recon_scope: Optional[str] = Query(
        None,
        description="仅采购端 client 生效：current_canteen=仅当前 JWT 食堂；school_merged=本校全部食堂合并。缺省按 current_canteen。",
    ),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前用户的对账单列表（client↔delivery 腿按 食堂×对手方×账期 聚合）。运营/监管看全部。"""
    q = select(ReconciliationStatement)
    if user.role not in {"operation", "monitor"}:
        q = q.where(ReconciliationStatement.owner_user_id == int(user.id))
    if user.role == "client":
        scope = (recon_scope or "current_canteen").strip().lower()
        if scope not in ("current_canteen", "school_merged"):
            scope = "current_canteen"
        if scope == "current_canteen":
            cid = await resolve_client_canteen_id_from_request(db, user, request)
            # IS NULL 兼容无食堂信息的历史明细聚出的对账单
            q = q.where(
                or_(
                    ReconciliationStatement.canteen_id == int(cid),
                    ReconciliationStatement.canteen_id.is_(None),
                )
            )
    if direction:
        q = q.where(ReconciliationStatement.direction == direction)
    if status:
        q = q.where(ReconciliationStatement.status == status)
    if period_label:
        q = q.where(ReconciliationStatement.period_label == period_label)
    rows = (await db.scalars(q.order_by(ReconciliationStatement.period_label.desc(), ReconciliationStatement.id.desc()))).all()
    cp_ids = sorted({int(r.counterparty_user_id) for r in rows})
    users = (await db.scalars(select(User).where(User.id.in_(cp_ids)))).all() if cp_ids else []
    umap = {int(u.id): u for u in users}
    cmap = await _canteen_name_map(db, rows)
    out = []
    for r in rows:
        await _recompute_reconciliation(db, r)
        cp = umap.get(int(r.counterparty_user_id))
        cname = cmap.get(int(r.canteen_id)) if r.canteen_id is not None else None
        if keyword:
            name = (cp.company_name or cp.username) if cp else ""
            if keyword not in name and keyword not in (r.period_label or "") and keyword not in (cname or ""):
                continue
        out.append(_serialize_reconciliation(r, cp, cname))
    await db.commit()
    return out


@router.get("/reconciliations/{recon_id}")
async def get_reconciliation(recon_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    recon = await db.get(ReconciliationStatement, recon_id)
    if not recon or (user.role not in {"operation", "monitor"} and int(recon.owner_user_id) != int(user.id)):
        raise HTTPException(404, "对账单不存在")
    await _recompute_reconciliation(db, recon)
    cp = await db.get(User, int(recon.counterparty_user_id))
    members = (
        await db.scalars(
            select(BillingStatement).where(BillingStatement.reconciliation_id == int(recon.id)).order_by(BillingStatement.id.asc())
        )
    ).all()
    cmap = await _canteen_name_map(db, [recon])
    data = _serialize_reconciliation(recon, cp, cmap.get(int(recon.canteen_id)) if recon.canteen_id is not None else None)
    data["statements"] = await _serialize_statements(db, members)
    await db.commit()
    return data


@router.post("/reconciliations/{recon_id}/confirm")
async def confirm_reconciliation(recon_id: int, payload: BillingStatementConfirmIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    recon = await db.scalar(select(ReconciliationStatement).where(ReconciliationStatement.id == recon_id, ReconciliationStatement.owner_user_id == int(user.id)))
    if not recon:
        raise HTTPException(404, "对账单不存在")
    if recon.status == "已结清":
        raise HTTPException(400, "已结清对账单不可再次确认")
    if recon.status == "进行中":
        raise HTTPException(400, "对账单尚未关账（进行中），无法确认")
    recon.status = "已确认"
    recon.confirmed_at = recon.confirmed_at or datetime.utcnow()
    await _cascade_members(db, int(recon.id), status="已确认", full_settle=False)
    mirror = await _mirror_reconciliation(db, recon)
    if mirror and mirror.status in ("进行中", "待确认"):
        mirror.status = "已确认"
        mirror.confirmed_at = recon.confirmed_at
        await _cascade_members(db, int(mirror.id), status="已确认", full_settle=False)
    await db.commit()
    await db.refresh(recon)
    cp = await db.get(User, int(recon.counterparty_user_id))
    cmap = await _canteen_name_map(db, [recon])
    return _serialize_reconciliation(recon, cp, cmap.get(int(recon.canteen_id)) if recon.canteen_id is not None else None)


@router.post("/reconciliations/{recon_id}/settle")
async def settle_reconciliation(recon_id: int, payload: BillingStatementSettleIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    recon = await db.scalar(select(ReconciliationStatement).where(ReconciliationStatement.id == recon_id, ReconciliationStatement.owner_user_id == int(user.id)))
    if not recon:
        raise HTTPException(404, "对账单不存在")
    if recon.direction != "应付":
        raise HTTPException(403, "收款对账单由付款方结清，你可查看到账状态")
    if recon.status == "已结清":
        raise HTTPException(400, "对账单已结清")
    if recon.status == "进行中":
        raise HTTPException(400, "对账单尚未关账（进行中），无法结清")
    await _recompute_reconciliation(db, recon)
    payable = Decimal(str(recon.total_amount or 0)) + Decimal(str(recon.adjust_amount or 0))
    remaining = payable - Decimal(str(recon.settled_amount or 0))
    pay = Decimal(str(payload.amount))
    if pay <= 0:
        raise HTTPException(400, "结清金额必须大于 0")
    if pay > remaining:
        raise HTTPException(400, "结清金额不能超过剩余未结金额")
    recon.settled_amount = (Decimal(str(recon.settled_amount or 0)) + pay).quantize(Decimal("0.01"))
    full = recon.settled_amount >= payable
    recon.status = "已结清" if full else "部分结清"
    await _cascade_members(db, int(recon.id), status=recon.status, full_settle=full)
    mirror = await _mirror_reconciliation(db, recon)
    if mirror:
        mirror.settled_amount = recon.settled_amount
        mirror.status = recon.status
        await _cascade_members(db, int(mirror.id), status=recon.status, full_settle=full)
    await db.commit()
    await db.refresh(recon)
    cp = await db.get(User, int(recon.counterparty_user_id))
    cmap = await _canteen_name_map(db, [recon])
    return _serialize_reconciliation(recon, cp, cmap.get(int(recon.canteen_id)) if recon.canteen_id is not None else None)


@router.get("/reconciliations/{recon_id}/export")
async def export_reconciliation(recon_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """导出标准对账单 CSV（对账单头 + 订单明细 + 商品行），UTF-8 BOM，可直接 Excel 打开。"""
    recon = await db.get(ReconciliationStatement, recon_id)
    if not recon or (user.role not in {"operation", "monitor"} and int(recon.owner_user_id) != int(user.id)):
        raise HTTPException(404, "对账单不存在")
    await _recompute_reconciliation(db, recon)
    cp = await db.get(User, int(recon.counterparty_user_id))
    cp_name = (cp.company_name or cp.username) if cp else ""
    members = (
        await db.scalars(
            select(BillingStatement).where(BillingStatement.reconciliation_id == int(recon.id)).order_by(BillingStatement.id.asc())
        )
    ).all()

    buf = io.StringIO()
    buf.write("﻿")  # BOM
    w = csv.writer(buf)
    w.writerow(["对账单", recon.statement_no])
    w.writerow(["对手方", cp_name])
    w.writerow(["账期", recon.period_label, "方向", recon.direction, "状态", recon.status])
    w.writerow(["账期总额", float(recon.total_amount or 0), "调整", float(recon.adjust_amount or 0), "已结清", float(recon.settled_amount or 0)])
    w.writerow(["关账日", recon.close_at.isoformat() if recon.close_at else "", "确认到期", recon.confirm_due_date.isoformat() if recon.confirm_due_date else "", "付款到期", recon.payment_due_date.isoformat() if recon.payment_due_date else ""])
    w.writerow([])
    w.writerow(["订单号", "商品", "规格", "数量", "单位", "单价", "金额", "状态"])
    for m in members:
        ss = m.source_snapshot_json or {}
        order_no = "、".join(ss.get("order_numbers") or [str(i) for i in (ss.get("order_ids") or [])]) or (m.remark or f"#{m.id}")
        allocs = ss.get("allocations") or []
        if allocs:
            for a in allocs:
                w.writerow([order_no, a.get("product_name", ""), a.get("spec", ""), a.get("quantity", ""), a.get("unit", ""), a.get("unit_price", ""), a.get("amount", ""), m.status])
        else:
            w.writerow([order_no, "（订单合计）", "", "", "", "", float(m.amount or 0), m.status])

    buf.seek(0)
    fname = f"reconciliation-{recon.statement_no}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/overview")
async def billing_overview(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """运营端账单总览：总额 KPI + 超期清单 + 即将出账。"""
    if user.role not in {"operation", "monitor"}:
        raise HTTPException(403, "无权限")
    rows = (await db.scalars(select(BillingStatement).order_by(BillingStatement.id.desc()))).all()
    serialized = await _serialize_statements(db, rows)
    cycles = (await db.scalars(select(BillingCycle))).all()
    cycle_map = {int(c.id): c for c in cycles}
    enriched = _enrich_with_period(serialized, cycle_map)

    today = date.today()
    client_delivery_unsettled = 0.0
    delivery_supplier_unsettled = 0.0
    settled_count = 0
    for r in enriched:
        if r["status"] == "已结清":
            settled_count += 1
        # 只取应付侧（应收是镜像），避免双重计数
        if r["direction"] != "应付":
            continue
        relation = (r.get("source_snapshot_json") or {}).get("relation_type")
        if relation == "client_delivery":
            client_delivery_unsettled += r["unsettled_amount"]
        elif relation == "delivery_supplier":
            delivery_supplier_unsettled += r["unsettled_amount"]

    overdue = summarize_overdue(enriched, today)

    upcoming: list[dict] = []
    for c in cycles:
        if c.scope_type != "relation_type":
            continue
        period = compute_billing_period(today, c)
        try:
            close_at = date.fromisoformat(period["close_at"])
        except ValueError:
            continue
        days_to_close = (close_at - today).days
        if 0 <= days_to_close <= 7:
            rt = relation_type_from_cycle(c)
            upcoming.append(
                {
                    "relation_type": rt,
                    "title": (RELATION_RULES.get(rt) or {}).get("title") or c.cycle_code,
                    "close_at": period["close_at"],
                    "days_to_close": days_to_close,
                    "period_label": period["period_label"],
                    "cycle_type": c.cycle_type,
                }
            )
    upcoming.sort(key=lambda x: x["days_to_close"])

    # 计数以「对账单」为单元：只数应付侧（应收是镜像），避免翻倍 / 高估
    recon_rows = (
        await db.scalars(select(ReconciliationStatement).where(ReconciliationStatement.direction == "应付"))
    ).all()
    recon_total = len(recon_rows)
    recon_settled = sum(1 for rr in recon_rows if rr.status == "已结清")

    return {
        "totals": {
            "client_delivery_unsettled": round(client_delivery_unsettled, 2),
            "delivery_supplier_unsettled": round(delivery_supplier_unsettled, 2),
            "statement_count": recon_total,
            "settled_count": recon_settled,
        },
        "overdue_confirm": overdue["overdue_confirm"],
        "overdue_payment": overdue["overdue_payment"],
        "upcoming_close": upcoming,
    }


# ===== 运营专用：账单明细列表 + 单张详情（仅 require_role operation）=====


def _operation_statement_summary(rows: list[dict]) -> dict:
    by_status: dict[str, int] = {"待确认": 0, "已确认": 0, "部分结清": 0, "已结清": 0}
    amount_sum = 0.0
    unsettled_sum = 0.0
    for r in rows:
        s = str(r.get("status") or "")
        if s in by_status:
            by_status[s] += 1
        amount_sum += float(r.get("amount") or 0)
        unsettled_sum += float(r.get("unsettled_amount") or 0)
    return {
        "amount_sum": round(amount_sum, 2),
        "unsettled_sum": round(unsettled_sum, 2),
        "count_by_status": by_status,
    }


@router.get("/operation/statements")
async def operation_list_statements(
    relation_type: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="可逗号分隔传多个状态"),
    cycle_id: Optional[int] = Query(None),
    counterparty_keyword: Optional[str] = Query(None),
    overdue: Optional[str] = Query(None),
    period_from: Optional[str] = Query(None),
    period_to: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "operation":
        raise HTTPException(403, "无权限")
    rows = (
        await db.scalars(select(BillingStatement).order_by(BillingStatement.id.desc()))
    ).all()
    serialized = await _serialize_statements(db, rows)
    statuses = [s.strip() for s in (status or "").split(",") if s.strip()] or None
    filtered = _apply_statement_filters(
        serialized,
        direction=direction,
        counterparty_keyword=counterparty_keyword,
        keyword=keyword,
        overdue=overdue,
        relation_type=relation_type,
        cycle_id=cycle_id,
        period_from=period_from,
        period_to=period_to,
        statuses=statuses,
    )
    summary = _operation_statement_summary(filtered)
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": summary,
    }


@router.get("/operation/statements/{statement_id}/detail")
async def operation_statement_detail(
    statement_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "operation":
        raise HTTPException(403, "无权限")
    row = await db.scalar(select(BillingStatement).where(BillingStatement.id == statement_id))
    if not row:
        raise HTTPException(404, "账单不存在")
    serialized = (await _serialize_statements(db, [row]))[0]

    # 镜像：owner ↔ counterparty 互换 + 相反 direction + 同 statement_no 时间戳前缀（同批生成）
    mirror_dir = "应收" if row.direction == "应付" else "应付"
    stmt_no = row.statement_no or ""
    timestamp_prefix = stmt_no.rsplit("-", 1)[0] if "-" in stmt_no else stmt_no
    mirror_row = await db.scalar(
        select(BillingStatement).where(
            BillingStatement.owner_user_id == row.counterparty_user_id,
            BillingStatement.counterparty_user_id == row.owner_user_id,
            BillingStatement.direction == mirror_dir,
            BillingStatement.statement_no.like(f"{timestamp_prefix}-%"),
            BillingStatement.id != row.id,
        )
    )
    mirror_payload = None
    if mirror_row:
        mirror_payload = {
            "id": int(mirror_row.id),
            "statement_no": mirror_row.statement_no,
            "direction": mirror_row.direction,
            "status": mirror_row.status,
            "role": mirror_row.role,
            "amount": float(mirror_row.amount or 0),
            "settled_amount": float(mirror_row.settled_amount or 0),
            "owner_user_id": mirror_row.owner_user_id,
            "counterparty_user_id": mirror_row.counterparty_user_id,
        }

    # 周期信息
    cycle = (
        await db.scalar(select(BillingCycle).where(BillingCycle.id == row.cycle_id))
        if row.cycle_id else None
    )
    cycle_payload = None
    if cycle:
        period = compute_billing_period(row.created_at or datetime.utcnow(), cycle)
        cycle_payload = {
            "id": int(cycle.id),
            "cycle_type": cycle.cycle_type,
            "close_day": cycle.close_day,
            "confirm_due_days": cycle.confirm_due_days,
            "payment_due_days": cycle.payment_due_days,
            "scope_type": cycle.scope_type,
            "is_confirmed": getattr(cycle, "is_confirmed", None),
            "close_at": period.get("close_at"),
            "confirm_due_date": period.get("confirm_due_date"),
            "payment_due_date": period.get("payment_due_date"),
            "period_label": period.get("period_label"),
            "period_start": period.get("period_start"),
            "period_end": period.get("period_end"),
        }

    # 关联订单
    order_ids = _extract_statement_order_ids(row.source_snapshot_json)
    orders_payload: list[dict] = []
    if order_ids:
        orders = (await db.scalars(select(Order).where(Order.id.in_(order_ids)))).all()
        for o in orders:
            orders_payload.append(
                {
                    "id": int(o.id),
                    "order_no": o.order_no,
                    "expected_delivery_date": o.expected_delivery_date.isoformat() if o.expected_delivery_date else None,
                    "expected_delivery_slot": o.expected_delivery_slot,
                    "amount": float(o.total_amount or 0),
                    "status": o.status,
                }
            )

    return {
        "statement": serialized,
        "mirror": mirror_payload,
        "cycle": cycle_payload,
        "orders": orders_payload,
    }


# ===== 账期配置实时预览（不落库）=====


_WEEKDAY_CN = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


def _natural_language_for_cycle(cycle_type: str, close_day: int, confirm_due_days: int, payment_due_days: int) -> str:
    ct = (cycle_type or "monthly").strip().lower()
    if ct == "daily":
        head = "每天 24:00 关账"
    elif ct == "weekly":
        cd = max(1, min(7, int(close_day or 1)))
        head = f"每{_WEEKDAY_CN[cd]} 24:00 关账"
    else:
        cd = max(1, min(28, int(close_day or 1)))
        head = f"每月 {cd} 号 24:00 关账"
    return (
        f"{head}。对方需在关账后 {int(confirm_due_days)} 天内确认账单、"
        f"{int(payment_due_days)} 天内付清欠款。"
    )


@router.post("/cycles/preview")
async def preview_billing_cycle(
    payload: dict,
    user=Depends(get_current_user),
):
    """账期配置预览：传入字段实时算出下一关账日、确认到期日、付款到期日 + 自然语言描述。不落库、不写入。"""
    if user.role != "operation":
        raise HTTPException(403, "无权限")
    cycle_type = str(payload.get("cycle_type") or "monthly").strip().lower()
    if cycle_type not in {"daily", "weekly", "monthly"}:
        raise HTTPException(400, "cycle_type 必须为 daily/weekly/monthly")
    try:
        close_day = int(payload.get("close_day") or 1)
        confirm_due_days = int(payload.get("confirm_due_days") or 0)
        payment_due_days = int(payload.get("payment_due_days") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "close_day / confirm_due_days / payment_due_days 必须为整数")
    if confirm_due_days < 0 or payment_due_days < 0:
        raise HTTPException(400, "天数不能为负")
    if payment_due_days < confirm_due_days:
        raise HTTPException(400, "付款期限应不少于确认期限")
    if cycle_type == "weekly" and not (1 <= close_day <= 7):
        raise HTTPException(400, "按周时 close_day 必须为 1-7")
    if cycle_type == "monthly" and not (1 <= close_day <= 28):
        raise HTTPException(400, "按月时 close_day 必须为 1-28")

    from types import SimpleNamespace

    fake_cycle = SimpleNamespace(
        cycle_type=cycle_type,
        close_day=close_day if cycle_type != "daily" else 1,
        confirm_due_days=confirm_due_days,
        payment_due_days=payment_due_days,
    )
    today = date.today()
    period = compute_billing_period(today, fake_cycle)
    next_close = date.fromisoformat(period["close_at"])
    days_to_close = (next_close - today).days
    return {
        "natural_language": _natural_language_for_cycle(cycle_type, close_day, confirm_due_days, payment_due_days),
        "next_close_at": period["close_at"],
        "next_confirm_due": period["confirm_due_date"],
        "next_payment_due": period["payment_due_date"],
        "period_label": period["period_label"],
        "period_start": period["period_start"],
        "period_end": period["period_end"],
        "days_to_close": days_to_close,
        "today": today.isoformat(),
    }
