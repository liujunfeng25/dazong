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
    Product,
    SupplierProductQuote,
    User,
)


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
    cycle_type: str = "monthly",
    close_day: int = 1,
    confirm_due_days: int = 3,
    payment_due_days: int = 7,
) -> BillingCycle:
    existing = await db.scalar(
        select(BillingCycle).where(
            BillingCycle.owner_user_id == owner_user_id,
            BillingCycle.role == role,
            BillingCycle.scope_type == scope_type,
            BillingCycle.scope_ref_id == scope_ref_id,
            BillingCycle.is_active.is_(True),
        )
    )
    if existing:
        return existing
    today = date.today()
    cycle_code = f"CYC-{role.upper()}-{owner_user_id}-{scope_type}-{scope_ref_id}-{today.strftime('%Y%m%d')}"
    cycle = BillingCycle(
        cycle_code=cycle_code,
        role=role,
        owner_user_id=owner_user_id,
        scope_type=scope_type,
        scope_ref_id=scope_ref_id,
        cycle_type=cycle_type,
        start_date=today.replace(day=1),
        end_date=today,
        close_day=close_day,
        confirm_due_days=confirm_due_days,
        payment_due_days=payment_due_days,
        is_active=True,
        is_confirmed=False,
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
        confirmed_at=datetime.utcnow() if confirmed else None,
        due_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(statement)
    await db.flush()
    await _send_billing_notification(
        db,
        owner_user_id=draft.owner_user_id,
        title="已生成账单",
        content=f"账单 {statement.statement_no} 已生成，请及时确认。",
        object_type="billing_statement",
        object_id=int(statement.id),
        route=f"/{draft.role}/bills",
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
) -> BillingCycle:
    rule = await relation_rule_for_billing(db, relation_type)
    return await ensure_default_billing_cycle(
        db,
        owner_user_id=owner_user_id,
        role=role,
        scope_type="counterparty",
        scope_ref_id=counterparty_user_id,
        cycle_type=rule.cycle_type,
        close_day=rule.close_day,
        confirm_due_days=rule.confirm_due_days,
        payment_due_days=rule.payment_due_days,
    )


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
) -> BillingStatement:
    role = owner_role or str(owner.role)
    cycle = await _active_cycle_for_pair(
        db,
        owner_user_id=int(owner.id),
        role=role,
        counterparty_user_id=int(counterparty.id),
        relation_type=relation_type,
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
    )
    statement = await create_statement_from_draft(db, draft, cycle, confirmed=False)
    statement.remark = display_title
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

    order_amount = Decimal(str(order.total_amount or 0)).quantize(Decimal("0.01"))
    order_lines = order.items_json or []
    base_snapshot = {
        "order_ids": [int(order.id)],
        "order_numbers": [order.order_no],
        "orders": [
            {
                "order_id": int(order.id),
                "order_no": order.order_no,
                "amount": float(order_amount),
            }
        ],
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
        amount = (quantity * unit_price).quantize(Decimal("0.01"))
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
                "is_factory_item": bool(row.is_designated_factory and row.designated_factory_id == uid),
            }
        )

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
            )
        )
    return created


async def auto_generate_demo_month_statement(
    db: AsyncSession,
    *,
    client_id: int,
    delivery_id: int,
    orders: list[Order],
):
    cycle = await ensure_default_billing_cycle(
        db,
        owner_user_id=client_id,
        role="client",
        scope_type="canteen",
        scope_ref_id=0,
    )
    drafts = await build_statement_drafts_from_orders(
        db,
        owner_user_id=client_id,
        role="client",
        counterparty_user_id=delivery_id,
        direction="应付",
        orders=orders,
        cycle=cycle,
    )
    created: list[BillingStatement] = []
    for draft in drafts:
        created.append(await create_statement_from_draft(db, draft, cycle, confirmed=True))
    return created


async def bootstrap_cycle_and_statements(
    db: AsyncSession,
    *,
    client_id: int,
    delivery_id: int,
    orders: list[Order],
) -> list[BillingStatement]:
    cycle = await ensure_default_billing_cycle(
        db,
        owner_user_id=client_id,
        role="client",
        scope_type="canteen",
        scope_ref_id=0,
    )
    drafts = await build_statement_drafts_from_orders(
        db,
        owner_user_id=client_id,
        role="client",
        counterparty_user_id=delivery_id,
        direction="应付",
        orders=orders,
        cycle=cycle,
    )
    created: list[BillingStatement] = []
    for draft in drafts:
        created.append(await create_statement_from_draft(db, draft, cycle, confirmed=False))
    return created
