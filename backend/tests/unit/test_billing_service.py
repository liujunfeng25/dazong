import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models import BillingStatement, Contract, Order, User
from services.billing_service import create_receive_billing_statements


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, users, allocation_rows, contract=None, quote_exists=True):
        self.users = {int(u.id): u for u in users}
        self.allocation_rows = allocation_rows
        self.contract = contract
        self.quote_exists = quote_exists
        self.added = []
        self._next_id = 1

    async def get(self, model, row_id):
        if model is User:
            return self.users.get(int(row_id))
        return None

    async def scalar(self, _stmt):
        stmt = str(_stmt)
        if "FROM contracts" in stmt:
            return self.contract
        if "FROM supplier_product_quotes" in stmt:
            return 1 if self.quote_exists else None
        return None

    async def scalars(self, _stmt):
        return _Rows(list(self.users.values()))

    async def execute(self, _stmt):
        return _Rows(self.allocation_rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1


def test_receive_billing_statements_create_paired_flows_for_supplier_and_factory():
    client = User(id=1, username="client", role="client", company_name="一中食堂")
    delivery = User(id=2, username="delivery", role="delivery", company_name="安心配送")
    supplier = User(id=3, username="supplier", role="supplier", company_name="绿源供货", supplier_delivery_id=2)
    factory = User(id=4, username="factory", role="factory", company_name="恒温厂家")
    contract = Contract(
        id=88,
        contract_no="CT20260511001",
        client_id=1,
        delivery_id=2,
        category_ids_json=[],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        status="已中标",
        price_float_rate=0,
        category_rates_json=[],
    )
    order = Order(
        id=10,
        order_no="SO20260511001",
        client_id=1,
        delivery_id=2,
        canteen_id=77,
        items_json=[{"name": "白菜"}, {"name": "牛奶"}, {"name": "鸡蛋"}],
        items_snapshot_json=[],
        total_amount=Decimal("100.00"),
        status="收货确认",
    )
    rows = [
        SimpleNamespace(
            id=101,
            supplier_id=3,
            line_no=1,
            product_id=201,
            quantity=Decimal("2"),
            unit_price=Decimal("10.00"),
            name="白菜",
            spec="",
            unit="kg",
            is_designated_factory=False,
            designated_factory_id=None,
        ),
        SimpleNamespace(
            id=102,
            supplier_id=3,
            line_no=2,
            product_id=202,
            quantity=Decimal("3"),
            unit_price=Decimal("10.00"),
            name="鸡蛋",
            spec="",
            unit="kg",
            is_designated_factory=False,
            designated_factory_id=None,
        ),
        SimpleNamespace(
            id=103,
            supplier_id=4,
            line_no=3,
            product_id=203,
            quantity=Decimal("5"),
            unit_price=Decimal("10.00"),
            name="牛奶",
            spec="箱",
            unit="箱",
            is_designated_factory=True,
            designated_factory_id=4,
        ),
    ]
    db = _FakeSession([client, delivery, supplier, factory], rows, contract=contract)

    created = asyncio.run(create_receive_billing_statements(db, order))
    statements = [row for row in created if isinstance(row, BillingStatement)]

    assert len(statements) == 6
    flow_amounts = {(s.role, s.owner_user_id, s.counterparty_user_id, s.direction): s.amount for s in statements}
    assert flow_amounts[("client", 1, 2, "应付")] == Decimal("100.00")
    assert flow_amounts[("delivery", 2, 1, "应收")] == Decimal("100.00")
    assert flow_amounts[("delivery", 2, 3, "应付")] == Decimal("50.00")
    assert flow_amounts[("supplier", 3, 2, "应收")] == Decimal("50.00")
    assert flow_amounts[("delivery", 2, 4, "应付")] == Decimal("50.00")
    assert flow_amounts[("factory", 4, 2, "应收")] == Decimal("50.00")
    # 6 张账单应都带 order.canteen_id=77（一单只送一个食堂）
    assert all(s.canteen_id == 77 for s in statements)


def test_receive_billing_statements_reject_without_active_contract():
    client = User(id=1, username="client", role="client", company_name="一中食堂")
    delivery = User(id=2, username="delivery", role="delivery", company_name="安心配送")
    order = Order(
        id=10,
        order_no="SO20260511001",
        client_id=1,
        delivery_id=2,
        items_json=[],
        items_snapshot_json=[],
        total_amount=Decimal("100.00"),
        status="收货确认",
    )
    db = _FakeSession([client, delivery], [], contract=None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_receive_billing_statements(db, order))
    assert exc.value.status_code == 400
    assert "有效合约" in exc.value.detail


def test_receive_billing_statements_reject_supplier_without_quote():
    client = User(id=1, username="client", role="client", company_name="一中食堂")
    delivery = User(id=2, username="delivery", role="delivery", company_name="安心配送")
    supplier = User(id=3, username="supplier", role="supplier", company_name="绿源供货", supplier_delivery_id=2)
    contract = Contract(
        id=88,
        contract_no="CT20260511001",
        client_id=1,
        delivery_id=2,
        category_ids_json=[],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        status="已中标",
        price_float_rate=0,
        category_rates_json=[],
    )
    order = Order(
        id=10,
        order_no="SO20260511001",
        client_id=1,
        delivery_id=2,
        items_json=[{"name": "白菜"}],
        items_snapshot_json=[],
        total_amount=Decimal("100.00"),
        status="收货确认",
    )
    rows = [
        SimpleNamespace(
            id=101,
            supplier_id=3,
            line_no=1,
            product_id=201,
            quantity=Decimal("2"),
            unit_price=Decimal("10.00"),
            name="白菜",
            spec="",
            unit="kg",
            is_designated_factory=False,
            designated_factory_id=None,
        )
    ]
    db = _FakeSession([client, delivery, supplier], rows, contract=contract, quote_exists=False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_receive_billing_statements(db, order))
    assert exc.value.status_code == 400
    assert "未对该商品报价" in exc.value.detail
    assert not [row for row in db.added if isinstance(row, BillingStatement)]
