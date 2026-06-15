from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    BillingCycle,
    BillingStatement,
    Contract,
    Notification,
    Order,
    OrderItemAllocation,
    OrderReturnLine,
    Product,
    ReconciliationStatement,
    SupplierProductQuote,
    User,
)
from services.receiving_billing import build_receiving_billing_snapshot


@dataclass
class StatementDraft:
    owner_user_id: int
    counterparty_user_id: int
    direction: str
    role: str
    amount: Decimal
    item_count: int
    source_snapshot_json: dict
    cycle_snapshot_json: dict
    canteen_id: int | None = None


ROLE_LABELS = {
    "client": "客户端",
    "delivery": "配送商",
    "supplier": "供货商",
    "factory": "厂家",
}

RELATION_RULES = {
    "client_delivery": {
        "scope_ref_id": 1,
        "role": "client",
        "title": "客户（食堂）对配送商结算",
        "description": "客户（食堂）应付配送商，配送商应收客户（食堂）",
    },
    "delivery_supplier": {
        "scope_ref_id": 2,
        "role": "delivery",
        "title": "配送商对供货商/厂家结算",
        "description": "配送商应付供货商/厂家，供货商/厂家应收配送商",
    },
}


def billing_route_for_role(role: str) -> str:
    value = str(role or "").strip()
    if value in {"client", "delivery", "supplier", "factory"}:
        return f"/{value}/bills"
    return "/operation/billing-overview"


def _money_text(value: Decimal | float | int | str) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    text = format(amount, "f").rstrip("0").rstrip(".")
    return f"¥{text or '0'}"


def _billing_title(direction: str) -> str:
    if direction == "应收":
        return "应收账单生成"
    if direction == "应付":
        return "应付账单生成"
    return "待确认账单生成"


def _billing_content(statement: BillingStatement, cycle: BillingCycle, counterparty_name: str) -> str:
    period = compute_billing_period(statement.created_at or datetime.utcnow(), cycle)
    return (
        f"对方：{counterparty_name or '—'}｜金额：{_money_text(statement.amount)}｜"
        f"账期：{period.get('period_label') or '—'}｜确认到期：{period.get('confirm_due_date') or '—'}"
    )


def compute_billing_period(reference_dt, cycle: BillingCycle) -> dict:
    """根据业务发生时间反算账期归属。close_day=1 + monthly：4 月内的账单归 "2026-04"，
    close_at=2026-05-01；close_day=15：4/15 ~ 5/14 归 "2026-05"，close_at=2026-05-15。"""
    d = reference_dt.date() if isinstance(reference_dt, datetime) else reference_dt
    cycle_type = (cycle.cycle_type or "monthly") if cycle else "monthly"
    close_day = int((cycle.close_day if cycle else 1) or 1)
    confirm_due_days = int((cycle.confirm_due_days if cycle else 0) or 0)
    payment_due_days = int((cycle.payment_due_days if cycle else 0) or 0)

    if cycle_type == "daily":
        period_start = period_end = close_at = d
        label = d.isoformat()
    elif cycle_type == "weekly":
        cd = max(1, min(7, close_day))
        wd = d.isoweekday()
        delta = (cd - wd) if wd < cd else (7 - (wd - cd))
        close_at = d + timedelta(days=delta)
        period_end = close_at - timedelta(days=1) if delta > 0 else close_at
        period_start = period_end - timedelta(days=6)
        iso_year, iso_week, _ = period_end.isocalendar()
        label = f"{iso_year}-W{iso_week:02d}"
    else:
        cd = max(1, min(28, close_day))
        if d.day < cd:
            close_at = date(d.year, d.month, cd)
            prev_year = d.year if d.month > 1 else d.year - 1
            prev_month = d.month - 1 if d.month > 1 else 12
            period_start = date(prev_year, prev_month, cd)
        else:
            next_year, next_month = (d.year, d.month + 1) if d.month < 12 else (d.year + 1, 1)
            close_at = date(next_year, next_month, cd)
            period_start = date(d.year, d.month, cd)
        period_end = close_at - timedelta(days=1)
        label = f"{period_end.year:04d}-{period_end.month:02d}"

    return {
        "period_label": label,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "close_at": close_at.isoformat(),
        "confirm_due_date": (close_at + timedelta(days=confirm_due_days)).isoformat(),
        "payment_due_date": (close_at + timedelta(days=payment_due_days)).isoformat(),
        "cycle_type": cycle_type,
        "close_day": close_day,
    }


def is_unsettled_status(status: str) -> bool:
    return status != "已结清"


def summarize_overdue(items: list[dict], today: date) -> dict:
    """从带 period 信息的账单列表里挑出超期未确认、超期未付的两类。"""
    overdue_confirm: list[dict] = []
    overdue_payment: list[dict] = []
    for it in items:
        status = it.get("status") or ""
        confirm_due_s = it.get("confirm_due_date")
        payment_due_s = it.get("payment_due_date")
        if not confirm_due_s or not payment_due_s:
            continue
        confirm_due = date.fromisoformat(confirm_due_s)
        payment_due = date.fromisoformat(payment_due_s)
        if status == "待确认" and today > confirm_due:
            overdue_confirm.append({**it, "overdue_days": (today - confirm_due).days})
        if status in {"已确认", "部分结清"} and today > payment_due:
            overdue_payment.append({**it, "overdue_days": (today - payment_due).days})
    return {"overdue_confirm": overdue_confirm, "overdue_payment": overdue_payment}


def relation_type_from_cycle(cycle: BillingCycle) -> str:
    if cycle.scope_type == "relation_type":
        for key, item in RELATION_RULES.items():
            if int(item["scope_ref_id"]) == int(cycle.scope_ref_id):
                return key
    return ""


async def _get_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, int(user_id))


async def _send_billing_notification(
    db: AsyncSession,
    *,
    owner_user_id: int,
    title: str,
    content: str,
    object_type: str,
    object_id: int,
    route: str,
):
    user = await _get_user(db, owner_user_id)
    if not user:
        return
    db.add(
        Notification(
            event_type="billing",
            title=title,
            content=content,
            role=user.role,
            target_user_id=int(user.id),
            canteen_id=None,
            object_type=object_type,
            object_id=object_id,
            route=route,
            is_read=False,
        )
    )


async def ensure_default_billing_cycle(
    db: AsyncSession,
    *,
    owner_user_id: int,
    role: str,
    scope_type: str,
    scope_ref_id: int,
    canteen_id: int | None = None,
    cycle_type: str = "monthly",
    close_day: int = 1,
    confirm_due_days: int = 3,
    payment_due_days: int = 7,
    follow_rule: "BillingCycle | None" = None,
) -> BillingCycle:
    canteen_cond = (
        BillingCycle.canteen_id.is_(None) if canteen_id is None else BillingCycle.canteen_id == int(canteen_id)
    )
    existing = await db.scalar(
        select(BillingCycle).where(
            BillingCycle.owner_user_id == owner_user_id,
            BillingCycle.role == role,
            BillingCycle.scope_type == scope_type,
            BillingCycle.scope_ref_id == scope_ref_id,
            canteen_cond,
            BillingCycle.is_active.is_(True),
        )
    )
    if existing:
        # 未定制的派生规则跟随全局：每次解析时同步全局参数（运营改全局即改默认值）
        if follow_rule is not None and not bool(existing.is_customized):
            existing.cycle_type = follow_rule.cycle_type
            existing.close_day = follow_rule.close_day
            existing.confirm_due_days = follow_rule.confirm_due_days
            existing.payment_due_days = follow_rule.payment_due_days
        return existing
    today = date.today()
    canteen_tag = f"-C{canteen_id}" if canteen_id is not None else ""
    cycle_code = f"CYC-{role.upper()}-{owner_user_id}-{scope_type}-{scope_ref_id}{canteen_tag}-{today.strftime('%Y%m%d')}"
    cycle = BillingCycle(
        cycle_code=cycle_code,
        role=role,
        owner_user_id=owner_user_id,
        scope_type=scope_type,
        scope_ref_id=scope_ref_id,
        canteen_id=canteen_id,
        cycle_type=cycle_type,
        start_date=today.replace(day=1),
        end_date=today,
        close_day=close_day,
        confirm_due_days=confirm_due_days,
        payment_due_days=payment_due_days,
        is_active=True,
        is_confirmed=False,
        is_customized=False,
    )
    db.add(cycle)
    await db.flush()
    return cycle


async def ensure_relation_billing_rule(
    db: AsyncSession,
    relation_type: str,
    *,
    cycle_type: str = "monthly",
    close_day: int = 1,
    confirm_due_days: int = 3,
    payment_due_days: int = 7,
) -> BillingCycle:
    config = RELATION_RULES.get(relation_type)
    if not config:
        raise HTTPException(400, "账期关系类型无效")
    return await ensure_default_billing_cycle(
        db,
        owner_user_id=0,
        role=str(config["role"]),
        scope_type="relation_type",
        scope_ref_id=int(config["scope_ref_id"]),
        cycle_type=cycle_type,
        close_day=close_day,
        confirm_due_days=confirm_due_days,
        payment_due_days=payment_due_days,
    )


async def relation_rule_for_billing(db: AsyncSession, relation_type: str) -> BillingCycle:
    return await ensure_relation_billing_rule(db, relation_type)


def _order_business_date(order: Order) -> date:
    created_at = getattr(order, "created_at", None)
    if isinstance(created_at, datetime):
        return created_at.date()
    return date.today()


async def assert_active_client_delivery_contract(
    db: AsyncSession,
    *,
    client_id: int,
    delivery_id: int,
    business_date: date,
) -> Contract:
    contract = await db.scalar(
        select(Contract)
        .where(
            Contract.client_id == int(client_id),
            Contract.delivery_id == int(delivery_id),
            Contract.status == "已中标",
            Contract.period_start <= business_date,
            Contract.period_end >= business_date,
        )
        .order_by(Contract.id.desc())
    )
    if not contract:
        raise HTTPException(400, "该客户与配送商没有有效合约，不能生成账单")
    return contract


async def assert_delivery_supplier_relation(
    db: AsyncSession,
    *,
    delivery_id: int,
    supplier_or_factory_id: int,
    product_id: int,
    product_is_designated_factory: bool,
    product_designated_factory_id: int | None,
) -> User:
    user = await _get_user(db, supplier_or_factory_id)
    if not user:
        raise HTTPException(400, "分单供货商/厂家账号不存在，不能生成账单")
    if product_is_designated_factory:
        if str(user.role) == "factory" and int(product_designated_factory_id or 0) == int(user.id):
            return user
        raise HTTPException(400, "指定厂家商品只能与对应厂家结算，不能生成错误供货商账单")
    if str(user.role) == "supplier" and int(user.supplier_delivery_id or 0) == int(delivery_id):
        quote_exists = await db.scalar(
            select(SupplierProductQuote.id).where(
                SupplierProductQuote.supplier_id == int(user.id),
                SupplierProductQuote.product_id == int(product_id),
            )
        )
        if not quote_exists:
            raise HTTPException(400, "分单供货商未对该商品报价，不能生成账单")
        return user
    raise HTTPException(400, "分单供货商/厂家与配送商没有有效业务关系，不能生成账单")


async def build_statement_drafts_from_orders(
    db: AsyncSession,
    *,
    owner_user_id: int,
    role: str,
    counterparty_user_id: int,
    direction: str,
    orders: Iterable[Order],
    cycle: BillingCycle,
) -> list[StatementDraft]:
    total = Decimal("0.00")
    item_count = 0
    order_ids: list[int] = []
    for order in orders:
        amount = Decimal(str(order.total_amount))
        total += amount
        item_count += len(order.items_json or [])
        order_ids.append(int(order.id))
    if not order_ids:
        return []
    return [
        StatementDraft(
            owner_user_id=owner_user_id,
            counterparty_user_id=counterparty_user_id,
            direction=direction,
            role=role,
            amount=total.quantize(Decimal("0.01")),
            item_count=item_count,
            source_snapshot_json={"order_ids": order_ids},
            cycle_snapshot_json={
                "cycle_code": cycle.cycle_code,
                "cycle_type": cycle.cycle_type,
                "start_date": cycle.start_date.isoformat(),
                "end_date": cycle.end_date.isoformat(),
            },
        )
    ]


async def create_statement_from_draft(
    db: AsyncSession,
    draft: StatementDraft,
    cycle: BillingCycle,
    *,
    confirmed: bool = False,
) -> BillingStatement:
    now = datetime.utcnow()
    statement = BillingStatement(
        statement_no=f"ST-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
        cycle_id=int(cycle.id),
        role=draft.role,
        owner_user_id=draft.owner_user_id,
        counterparty_user_id=draft.counterparty_user_id,
        direction=draft.direction,
        status="待确认",
        amount=draft.amount,
        confirmed_amount=draft.amount if confirmed else Decimal("0.00"),
        settled_amount=Decimal("0.00"),
        item_count=draft.item_count,
        source_snapshot_json=draft.source_snapshot_json,
        cycle_snapshot_json=draft.cycle_snapshot_json,
        remark="系统自动生成的业务账单",
        confirmed_at=now if confirmed else None,
        due_at=now + timedelta(days=7),
        canteen_id=draft.canteen_id,
        created_at=now,
    )
    db.add(statement)
    await db.flush()
    counterparty = await _get_user(db, draft.counterparty_user_id)
    counterparty_name = ""
    if counterparty:
        counterparty_name = counterparty.company_name or counterparty.username or ""
    await _send_billing_notification(
        db,
        owner_user_id=draft.owner_user_id,
        title=_billing_title(draft.direction),
        content=_billing_content(statement, cycle, counterparty_name),
        object_type="billing_statement",
        object_id=int(statement.id),
        route=billing_route_for_role(draft.role),
    )
    return statement


def _statement_title(owner_role: str, direction: str, counterparty_role: str | None = None) -> str:
    if owner_role == "client" and direction == "应付":
        return "我应付给配送商"
    if owner_role == "delivery" and direction == "应收":
        return "客户（食堂）待付给我"
    if owner_role == "delivery" and direction == "应付":
        return "我应付给供货商/厂家"
    if owner_role in {"supplier", "factory"} and direction == "应收":
        return "配送商待付给我"
    if direction == "应付":
        return f"我应付给{counterparty_role or '对方'}"
    return f"{counterparty_role or '对方'}待付给我"


async def _active_cycle_for_pair(
    db: AsyncSession,
    *,
    owner_user_id: int,
    role: str,
    counterparty_user_id: int,
    relation_type: str,
    canteen_id: int | None = None,
) -> BillingCycle:
    rule = await relation_rule_for_billing(db, relation_type)
    # 归一到关系主方（client_delivery→client 侧，delivery_supplier→delivery 侧）：
    # 同一对子的应付/应收两腿共用一条规则，单边定制不会导致镜像账期错位。
    canonical_role = str((RELATION_RULES.get(relation_type) or {}).get("role") or role)
    if role != canonical_role:
        owner_user_id, counterparty_user_id = counterparty_user_id, owner_user_id
    return await ensure_default_billing_cycle(
        db,
        owner_user_id=owner_user_id,
        role=canonical_role,
        scope_type="counterparty",
        scope_ref_id=counterparty_user_id,
        canteen_id=_recon_canteen_for(relation_type, canteen_id),
        cycle_type=rule.cycle_type,
        close_day=rule.close_day,
        confirm_due_days=rule.confirm_due_days,
        payment_due_days=rule.payment_due_days,
        follow_rule=rule,
    )


def _reconciliation_no(period_label: str, owner_id: int, counterparty_id: int, direction: str) -> str:
    tag = "P" if direction == "应付" else "R"
    return f"RC-{period_label}-{owner_id}-{counterparty_id}-{tag}-{uuid4().hex[:6]}"


def _recon_canteen_cond(canteen_id: int | None):
    """对账单聚合/镜像查找里的食堂条件（NULL-safe）。"""
    if canteen_id is None:
        return ReconciliationStatement.canteen_id.is_(None)
    return ReconciliationStatement.canteen_id == int(canteen_id)


def _recon_canteen_for(relation_type: str, canteen_id: int | None) -> int | None:
    """对账单粒度上的食堂归属：只有 client↔delivery 腿按食堂拆；
    供货腿明细虽带 canteen_id（来自订单），对账单仍按对手方一张，置 None。"""
    return canteen_id if relation_type == "client_delivery" else None


def _is_reversal_statement(s: BillingStatement) -> bool:
    return (s.source_snapshot_json or {}).get("kind") == "return_reversal"


# 仅当订单明细已挂到「已确认及之后」的对账单时，退货才走红冲（进行中/待确认走重算改原额）。
REVERSAL_TRIGGER_STATUSES = {"已确认", "部分结清", "已结清"}


def _order_deduction_in_snapshot(snapshot_json: dict, order_id: int) -> Decimal:
    """从账单快照里取该订单已体现的扣减额。"""
    for o in (snapshot_json or {}).get("orders") or []:
        if int(o.get("order_id") or 0) == int(order_id):
            return Decimal(str(o.get("deduction_amount") or 0))
    return Decimal("0.00")


def compute_return_reversals(
    *,
    statements,
    recon_status: dict,
    return_lines,
    allocations,
    order_id: int = 10,
):
    """纯函数：算出某订单退货后应生成的负额红冲计划（不碰 DB）。

    红冲额 = 本次退货应扣减总额 − 该订单账单中已体现的扣减（增量红冲）。
    仅对挂在「已确认/部分结清/已结清」对账单上的明细生成。
    """
    new_deduction = sum(
        (Decimal(str(getattr(r, "deduction_amount", 0) or 0)) for r in return_lines),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))

    # 退货行按商品聚合少收量，用于把客户侧退货映射到上游供货价。
    returned_kg_by_product: dict[int, Decimal] = {}
    for r in return_lines:
        pid = int(getattr(r, "product_id", 0) or 0)
        returned_kg_by_product[pid] = returned_kg_by_product.get(pid, Decimal("0")) + Decimal(
            str(getattr(r, "delta_kg", 0) or 0)
        )

    # 已落库的红冲（按腿汇总绝对值），用于幂等/补差：增量再减去已红冲部分。
    prior_reversed: dict[tuple, Decimal] = {}
    for s in statements:
        if (s.source_snapshot_json or {}).get("kind") != "return_reversal":
            continue
        key = (int(s.owner_user_id), int(s.counterparty_user_id), s.direction)
        prior_reversed[key] = prior_reversed.get(key, Decimal("0.00")) + abs(
            Decimal(str(s.amount or 0))
        )

    plans: list[dict] = []
    for s in statements:
        snap = s.source_snapshot_json or {}
        if snap.get("kind") == "return_reversal":
            continue
        relation = snap.get("relation_type")
        if recon_status.get(int(s.reconciliation_id)) not in REVERSAL_TRIGGER_STATUSES:
            continue

        if relation == "client_delivery":
            already = _order_deduction_in_snapshot(snap, order_id)
            incremental = (new_deduction - already).quantize(Decimal("0.01"))
        elif relation == "delivery_supplier":
            # 供货腿按供货价计算：少收量 × 该明细的供货单价，减已体现的供货侧扣减。
            supplier_new = Decimal("0.00")
            already = Decimal("0.00")
            for alloc in snap.get("allocations") or []:
                pid = int(alloc.get("product_id") or 0)
                if pid not in returned_kg_by_product:
                    continue
                supplier_new += returned_kg_by_product[pid] * Decimal(str(alloc.get("unit_price") or 0))
                already += Decimal(str(alloc.get("deduction_amount") or 0))
            incremental = (supplier_new - already).quantize(Decimal("0.01"))
        else:
            continue

        # 扣除该腿已红冲部分（幂等：相同退货再算不重复；退货扩大只补差）。
        key = (int(s.owner_user_id), int(s.counterparty_user_id), s.direction)
        incremental = (incremental - prior_reversed.get(key, Decimal("0.00"))).quantize(Decimal("0.01"))

        if incremental <= 0:
            continue
        plans.append(
            {
                "role": s.role,
                "owner_user_id": int(s.owner_user_id),
                "counterparty_user_id": int(s.counterparty_user_id),
                "direction": s.direction,
                "relation_type": relation,
                "reconciliation_id": int(s.reconciliation_id),
                "origin_statement_no": s.statement_no,
                "amount": (-incremental).quantize(Decimal("0.01")),
            }
        )
    return plans


async def _load_order_billing_statements(db: AsyncSession, order_id: int) -> list[BillingStatement]:
    """取出该订单已挂对账单的收货账单明细（含已落库的红冲明细，供幂等判断）。"""
    rows = (
        await db.scalars(
            select(BillingStatement).where(BillingStatement.reconciliation_id.isnot(None))
        )
    ).all()
    return [s for s in rows if int(order_id) in ((s.source_snapshot_json or {}).get("order_ids") or [])]


async def create_return_reversal_statements(
    db: AsyncSession,
    order,
    order_return,
) -> list[BillingStatement]:
    """对账单已确认后退货：按增量生成负额红冲明细，挂回原对账单并累加 adjust_amount。

    进行中/待确认的对账单不在此处理（由收货重算改原额）。幂等：相同退货重复调用不重复红冲。
    """
    statements = await _load_order_billing_statements(db, int(order.id))
    if not statements:
        return []

    recon_status: dict[int, str] = {}
    recons: dict[int, ReconciliationStatement] = {}
    for s in statements:
        rid = int(s.reconciliation_id)
        if rid in recons:
            continue
        recon = await db.get(ReconciliationStatement, rid)
        if recon is not None:
            recons[rid] = recon
            recon_status[rid] = str(recon.status)

    return_lines = (
        await db.scalars(
            select(OrderReturnLine).where(OrderReturnLine.order_return_id == int(order_return.id))
        )
    ).all()

    plans = compute_return_reversals(
        statements=statements,
        recon_status=recon_status,
        return_lines=return_lines,
        allocations=[],
        order_id=int(order.id),
    )

    created: list[BillingStatement] = []
    for plan in plans:
        recon = recons.get(int(plan["reconciliation_id"]))
        if recon is None:
            continue
        amount = Decimal(str(plan["amount"]))
        reversal = BillingStatement(
            statement_no=f"RV-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
            cycle_id=int(recon.cycle_id),
            reconciliation_id=int(recon.id),
            role=plan["role"],
            owner_user_id=int(plan["owner_user_id"]),
            counterparty_user_id=int(plan["counterparty_user_id"]),
            canteen_id=getattr(order, "canteen_id", None),
            direction=plan["direction"],
            status="待确认",
            amount=amount,
            item_count=0,
            source_snapshot_json={
                "kind": "return_reversal",
                "relation_type": plan["relation_type"],
                "order_ids": [int(order.id)],
                "order_numbers": [getattr(order, "order_no", None)],
                "origin_statement_no": plan["origin_statement_no"],
                "reverses_return_id": int(order_return.id),
            },
            remark="退货红冲",
        )
        db.add(reversal)
        # 红冲只动 adjust_amount（净额=total+adjust），total_amount 保持原毛额。
        recon.adjust_amount = (Decimal(str(recon.adjust_amount or 0)) + amount).quantize(Decimal("0.01"))
        recon.item_count = int(recon.item_count or 0) + 1
        created.append(reversal)

    if created:
        await db.flush()
    return created


async def attach_statement_to_reconciliation(
    db: AsyncSession,
    statement: BillingStatement,
    *,
    owner: User,
    counterparty: User,
    relation_type: str,
    direction: str,
    role: str,
    cycle: BillingCycle,
    canteen_id: int | None,
) -> ReconciliationStatement:
    """把一条账单明细归并进对应「我方×对手方×账期×方向」的进行中对账单（没有则创建），
    并累加金额、关联镜像对账单（应付↔应收）。"""
    period = compute_billing_period(statement.created_at or datetime.utcnow(), cycle)
    plabel = period["period_label"]
    canteen_id = _recon_canteen_for(relation_type, canteen_id)
    recon = await db.scalar(
        select(ReconciliationStatement).where(
            ReconciliationStatement.owner_user_id == int(owner.id),
            ReconciliationStatement.counterparty_user_id == int(counterparty.id),
            ReconciliationStatement.relation_type == relation_type,
            ReconciliationStatement.direction == direction,
            ReconciliationStatement.period_label == plabel,
            _recon_canteen_cond(canteen_id),
        )
    )
    if recon is None:
        recon = ReconciliationStatement(
            statement_no=_reconciliation_no(plabel, int(owner.id), int(counterparty.id), direction),
            relation_type=relation_type,
            cycle_id=int(cycle.id),
            role=role,
            owner_user_id=int(owner.id),
            counterparty_user_id=int(counterparty.id),
            canteen_id=canteen_id,
            direction=direction,
            period_label=plabel,
            status="进行中",
            total_amount=Decimal("0.00"),
            adjust_amount=Decimal("0.00"),
            settled_amount=Decimal("0.00"),
            item_count=0,
            close_at=date.fromisoformat(period["close_at"]),
            confirm_due_date=date.fromisoformat(period["confirm_due_date"]),
            payment_due_date=date.fromisoformat(period["payment_due_date"]),
        )
        db.add(recon)
        await db.flush()
    recon.total_amount = (
        Decimal(str(recon.total_amount or 0)) + Decimal(str(statement.amount or 0))
    ).quantize(Decimal("0.01"))
    recon.item_count = int(recon.item_count or 0) + 1
    statement.reconciliation_id = int(recon.id)
    # 关联镜像对账单（应付↔应收）
    if recon.mirror_id is None:
        opp = "应收" if direction == "应付" else "应付"
        mirror = await db.scalar(
            select(ReconciliationStatement).where(
                ReconciliationStatement.owner_user_id == int(counterparty.id),
                ReconciliationStatement.counterparty_user_id == int(owner.id),
                ReconciliationStatement.relation_type == relation_type,
                ReconciliationStatement.direction == opp,
                ReconciliationStatement.period_label == plabel,
                _recon_canteen_cond(canteen_id),
            )
        )
        if mirror is not None:
            recon.mirror_id = int(mirror.id)
            mirror.mirror_id = int(recon.id)
    return recon


async def backfill_reconciliations(db: AsyncSession, *, commit: bool = True) -> int:
    """把尚未归并的历史账单明细聚合进对账单（幂等：只处理 reconciliation_id 为空的）。
    回填后按成员明细状态推断对账单状态（已确认/部分结清/已结清/待确认）。
    commit=False 供测试/迁移脚本在外层事务里调用。"""
    rows = (await db.scalars(select(BillingStatement).where(BillingStatement.reconciliation_id.is_(None)))).all()
    if not rows:
        return 0
    cycle_ids = sorted({int(r.cycle_id) for r in rows if r.cycle_id})
    cycles = (await db.scalars(select(BillingCycle).where(BillingCycle.id.in_(cycle_ids)))).all()
    cmap = {int(c.id): c for c in cycles}
    touched: set[int] = set()
    for s in rows:
        cycle = cmap.get(int(s.cycle_id or 0))
        if not cycle:
            continue
        period = compute_billing_period(s.created_at or datetime.utcnow(), cycle)
        plabel = period["period_label"]
        relation = (s.source_snapshot_json or {}).get("relation_type") or (
            "client_delivery" if s.role == "client" else "delivery_supplier"
        )
        recon_canteen = _recon_canteen_for(relation, s.canteen_id)
        recon = await db.scalar(
            select(ReconciliationStatement).where(
                ReconciliationStatement.owner_user_id == int(s.owner_user_id),
                ReconciliationStatement.counterparty_user_id == int(s.counterparty_user_id),
                ReconciliationStatement.relation_type == relation,
                ReconciliationStatement.direction == s.direction,
                ReconciliationStatement.period_label == plabel,
                _recon_canteen_cond(recon_canteen),
            )
        )
        if recon is None:
            recon = ReconciliationStatement(
                statement_no=_reconciliation_no(plabel, int(s.owner_user_id), int(s.counterparty_user_id), s.direction),
                relation_type=relation,
                cycle_id=int(s.cycle_id),
                role=s.role,
                owner_user_id=int(s.owner_user_id),
                counterparty_user_id=int(s.counterparty_user_id),
                canteen_id=recon_canteen,
                direction=s.direction,
                period_label=plabel,
                status="进行中",
                total_amount=Decimal("0.00"),
                adjust_amount=Decimal("0.00"),
                settled_amount=Decimal("0.00"),
                item_count=0,
                close_at=date.fromisoformat(period["close_at"]),
                confirm_due_date=date.fromisoformat(period["confirm_due_date"]),
                payment_due_date=date.fromisoformat(period["payment_due_date"]),
            )
            db.add(recon)
            await db.flush()
        s.reconciliation_id = int(recon.id)
        touched.add(int(recon.id))
    for rid in touched:
        recon = await db.get(ReconciliationStatement, rid)
        members = (await db.scalars(select(BillingStatement).where(BillingStatement.reconciliation_id == rid))).all()
        # 口径：total=非红冲成员之和（毛额），adjust=红冲成员之和，净额=total+adjust
        recon.total_amount = sum(
            (Decimal(str(m.amount or 0)) for m in members if not _is_reversal_statement(m)), Decimal("0.00")
        ).quantize(Decimal("0.01"))
        recon.adjust_amount = sum(
            (Decimal(str(m.amount or 0)) for m in members if _is_reversal_statement(m)), Decimal("0.00")
        ).quantize(Decimal("0.01"))
        recon.settled_amount = sum((Decimal(str(m.settled_amount or 0)) for m in members), Decimal("0.00")).quantize(Decimal("0.01"))
        recon.item_count = len(members)
        statuses = {str(m.status) for m in members}
        if members and statuses == {"已结清"}:
            recon.status = "已结清"
        elif "部分结清" in statuses or recon.settled_amount > 0:
            recon.status = "部分结清"
        elif members and "待确认" not in statuses:
            recon.status = "已确认"
        elif recon.close_at and recon.close_at < date.today():
            recon.status = "待确认"
        if recon.mirror_id is None:
            opp = "应收" if recon.direction == "应付" else "应付"
            mirror = await db.scalar(
                select(ReconciliationStatement).where(
                    ReconciliationStatement.owner_user_id == int(recon.counterparty_user_id),
                    ReconciliationStatement.counterparty_user_id == int(recon.owner_user_id),
                    ReconciliationStatement.relation_type == recon.relation_type,
                    ReconciliationStatement.direction == opp,
                    ReconciliationStatement.period_label == recon.period_label,
                    _recon_canteen_cond(recon.canteen_id),
                )
            )
            if mirror:
                recon.mirror_id = int(mirror.id)
                mirror.mirror_id = int(recon.id)
    if commit:
        await db.commit()
    else:
        await db.flush()
    return len(rows)


async def _create_pair_statement(
    db: AsyncSession,
    *,
    owner: User,
    counterparty: User,
    direction: str,
    amount: Decimal,
    item_count: int,
    source_snapshot_json: dict,
    relation_type: str,
    owner_role: str | None = None,
    canteen_id: int | None = None,
) -> BillingStatement:
    role = owner_role or str(owner.role)
    cycle = await _active_cycle_for_pair(
        db,
        owner_user_id=int(owner.id),
        role=role,
        counterparty_user_id=int(counterparty.id),
        relation_type=relation_type,
        canteen_id=canteen_id,
    )
    cycle_snapshot = {
        "cycle_code": cycle.cycle_code,
        "cycle_type": cycle.cycle_type,
        "start_date": cycle.start_date.isoformat(),
        "end_date": cycle.end_date.isoformat(),
    }
    display_title = _statement_title(role, direction, str(counterparty.role or ""))
    draft = StatementDraft(
        owner_user_id=int(owner.id),
        counterparty_user_id=int(counterparty.id),
        direction=direction,
        role=role,
        amount=amount.quantize(Decimal("0.01")),
        item_count=item_count,
        source_snapshot_json={
            **source_snapshot_json,
            "relation_type": relation_type,
            "counterparty_name": counterparty.company_name or counterparty.username,
            "counterparty_role": counterparty.role,
            "display_title": display_title,
        },
        cycle_snapshot_json=cycle_snapshot,
        canteen_id=canteen_id,
    )
    statement = await create_statement_from_draft(db, draft, cycle, confirmed=False)
    statement.remark = display_title
    await attach_statement_to_reconciliation(
        db,
        statement,
        owner=owner,
        counterparty=counterparty,
        relation_type=relation_type,
        direction=direction,
        role=role,
        cycle=cycle,
        canteen_id=canteen_id,
    )
    return statement


async def create_receive_billing_statements(db: AsyncSession, order: Order) -> list[BillingStatement]:
    """Create paired period statements when the client confirms receiving an order."""
    client = await _get_user(db, int(order.client_id))
    delivery = await _get_user(db, int(order.delivery_id))
    if not client or not delivery:
        return []
    contract = await assert_active_client_delivery_contract(
        db,
        client_id=int(order.client_id),
        delivery_id=int(order.delivery_id),
        business_date=_order_business_date(order),
    )

    receiving_billing = await build_receiving_billing_snapshot(db, order)
    order_amount = Decimal(str(receiving_billing.get("received_amount") or order.total_amount or 0)).quantize(Decimal("0.01"))
    allocation_amounts = {
        int(k): Decimal(str(v)).quantize(Decimal("0.01"))
        for k, v in (receiving_billing.get("allocation_amounts") or {}).items()
    }
    allocation_ratios = {str(k): v for k, v in (receiving_billing.get("allocation_ratios") or {}).items()}
    order_lines = order.items_json or []
    base_snapshot = {
        "order_ids": [int(order.id)],
        "order_numbers": [order.order_no],
        "orders": [
            {
                "order_id": int(order.id),
                "order_no": order.order_no,
                "amount": float(order_amount),
                "original_amount": float(Decimal(str(order.total_amount or 0)).quantize(Decimal("0.01"))),
                "deduction_amount": float(Decimal(str(receiving_billing.get("deduction_amount") or 0)).quantize(Decimal("0.01"))),
            }
        ],
        "receiving_billing": receiving_billing,
        "contract_id": int(contract.id),
        "contract_no": contract.contract_no,
    }
    allocation_rows = (
        await db.execute(
            select(
                OrderItemAllocation.id,
                OrderItemAllocation.supplier_id,
                OrderItemAllocation.line_no,
                OrderItemAllocation.product_id,
                OrderItemAllocation.quantity,
                OrderItemAllocation.unit_price,
                Product.name,
                Product.spec,
                Product.unit,
                Product.is_designated_factory,
                Product.designated_factory_id,
            )
            .join(Product, Product.id == OrderItemAllocation.product_id)
            .where(OrderItemAllocation.order_id == order.id, OrderItemAllocation.delivery_id == order.delivery_id)
            .order_by(OrderItemAllocation.supplier_id.asc(), OrderItemAllocation.line_no.asc())
        )
    ).all()

    grouped: dict[int, dict] = {}
    for row in allocation_rows:
        uid = int(row.supplier_id)
        counterparty = await assert_delivery_supplier_relation(
            db,
            delivery_id=int(order.delivery_id),
            supplier_or_factory_id=uid,
            product_id=int(row.product_id),
            product_is_designated_factory=bool(row.is_designated_factory),
            product_designated_factory_id=int(row.designated_factory_id or 0),
        )
        quantity = Decimal(str(row.quantity or 0))
        unit_price = Decimal(str(row.unit_price or 0))
        original_amount = (quantity * unit_price).quantize(Decimal("0.01"))
        amount = allocation_amounts.get(int(row.id), original_amount)
        entry = grouped.setdefault(uid, {"amount": Decimal("0.00"), "lines": [], "counterparty": counterparty})
        entry["amount"] += amount
        entry["lines"].append(
            {
                "allocation_id": int(row.id),
                "line_no": int(row.line_no),
                "product_id": int(row.product_id),
                "product_name": row.name,
                "spec": row.spec or "",
                "unit": row.unit,
                "quantity": float(row.quantity or 0),
                "unit_price": float(row.unit_price or 0),
                "amount": float(amount),
                "original_amount": float(original_amount),
                "bill_ratio": float(allocation_ratios.get(str(int(row.id)), 1)),
                "is_factory_item": bool(row.is_designated_factory and row.designated_factory_id == uid),
            }
        )

    order_canteen_id = int(order.canteen_id) if order.canteen_id else None

    created: list[BillingStatement] = []
    created.append(
        await _create_pair_statement(
            db,
            owner=client,
            counterparty=delivery,
            direction="应付",
            amount=order_amount,
            item_count=len(order_lines),
            source_snapshot_json=base_snapshot,
            relation_type="client_delivery",
            canteen_id=order_canteen_id,
        )
    )
    created.append(
        await _create_pair_statement(
            db,
            owner=delivery,
            counterparty=client,
            direction="应收",
            amount=order_amount,
            item_count=len(order_lines),
            source_snapshot_json=base_snapshot,
            relation_type="client_delivery",
            canteen_id=order_canteen_id,
        )
    )
    if not allocation_rows:
        return created

    for uid, entry in grouped.items():
        counterparty = entry.get("counterparty")
        if not counterparty:
            continue
        role = "factory" if any(line["is_factory_item"] for line in entry["lines"]) else str(counterparty.role or "supplier")
        source_snapshot = {
            **base_snapshot,
            "allocations": entry["lines"],
        }
        created.append(
            await _create_pair_statement(
                db,
                owner=delivery,
                counterparty=counterparty,
                direction="应付",
                amount=entry["amount"],
                item_count=len(entry["lines"]),
                source_snapshot_json=source_snapshot,
                relation_type="delivery_supplier",
                canteen_id=order_canteen_id,
            )
        )
        created.append(
            await _create_pair_statement(
                db,
                owner=counterparty,
                counterparty=delivery,
                direction="应收",
                amount=entry["amount"],
                item_count=len(entry["lines"]),
                source_snapshot_json=source_snapshot,
                relation_type="delivery_supplier",
                owner_role=role,
                canteen_id=order_canteen_id,
            )
        )
    return created

