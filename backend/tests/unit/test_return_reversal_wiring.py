"""P3c 退货红冲 接线：配送商关账后审核通过退货时，
_rebuild_unconfirmed_receive_billing 要按对账单是否已确认选择「红冲」或「重算」。

routers.orders 用了 PEP 604（dict | None）注解，需 py>=3.10 才能在运行时导入，
故本测试在容器(3.11)里跑，本地 3.9 自动跳过。
"""

import asyncio
import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("routers.orders 需要 py>=3.10 才能导入", allow_module_level=True)

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import routers.orders as orders
import routers.bills as bills
from models import BillingStatement


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _WireSession:
    def __init__(self, statements, bills):
        self._statements = statements
        self._bills = bills
        self.deleted = []
        self.executed = []

    async def scalars(self, stmt):
        s = str(stmt)
        if "billing_statements" in s:
            return _Rows(self._statements)
        if "FROM bills" in s or "bills." in s:
            return _Rows(self._bills)
        return _Rows([])

    async def execute(self, stmt):
        self.executed.append(str(stmt))
        return _Rows([])

    async def delete(self, obj):
        self.deleted.append(obj)


def _stmt(status):
    return SimpleNamespace(
        status=status, source_snapshot_json={"order_ids": [10]},
        reconciliation_id=500, role="client", owner_user_id=1, counterparty_user_id=2,
        direction="应付", amount="100.00", statement_no="BS-A",
    )


def _patch_spies(monkeypatch):
    calls = {"reversal": [], "rebuild_statements": [], "rebuild_bills": []}

    async def fake_reversal(db, order, order_return):
        calls["reversal"].append((order, order_return))
        return []

    async def fake_rebuild_statements(db, order):
        calls["rebuild_statements"].append(order)
        return []

    async def fake_rebuild_bills(db, order):
        calls["rebuild_bills"].append(order)
        return []

    monkeypatch.setattr(orders, "create_return_reversal_statements", fake_reversal, raising=False)
    monkeypatch.setattr(orders, "create_receive_billing_statements", fake_rebuild_statements)
    monkeypatch.setattr(orders, "create_receive_bills", fake_rebuild_bills)
    return calls


def test_confirmed_recon_triggers_reversal_not_rebuild(monkeypatch):
    calls = _patch_spies(monkeypatch)
    order = SimpleNamespace(id=10, order_no="SO10", canteen_id=77, client_id=1, delivery_id=2)
    order_return = SimpleNamespace(id=55)
    db = _WireSession(statements=[_stmt("已确认")], bills=[])

    asyncio.run(orders._rebuild_unconfirmed_receive_billing(db, order, order_return))

    assert len(calls["reversal"]) == 1
    assert calls["reversal"][0] == (order, order_return)
    assert calls["rebuild_statements"] == []
    assert calls["rebuild_bills"] == []
    assert db.deleted == []  # 不删原账单


def test_unconfirmed_recon_triggers_rebuild_not_reversal(monkeypatch):
    calls = _patch_spies(monkeypatch)
    order = SimpleNamespace(id=10, order_no="SO10", canteen_id=77, client_id=1, delivery_id=2)
    order_return = SimpleNamespace(id=55)
    db = _WireSession(statements=[_stmt("待确认")], bills=[])

    asyncio.run(orders._rebuild_unconfirmed_receive_billing(db, order, order_return))

    assert calls["reversal"] == []
    assert len(calls["rebuild_statements"]) == 1
    assert len(calls["rebuild_bills"]) == 1


class _EmptySession:
    async def scalars(self, stmt):
        return _Rows([])


def _make_bs(statement_no, amount, role, direction, snapshot, remark=""):
    return BillingStatement(
        id=abs(hash(statement_no)) % 10000, statement_no=statement_no, cycle_id=7,
        reconciliation_id=500, role=role, owner_user_id=1, counterparty_user_id=2,
        direction=direction, status="待确认", amount=Decimal(amount),
        source_snapshot_json=snapshot, remark=remark, created_at=datetime.utcnow(),
    )


def test_serialize_marks_reversal_rows():
    normal = _make_bs(
        "BS-A", "100.00", "client", "应付",
        {"relation_type": "client_delivery", "order_ids": [10], "order_numbers": ["SO10"]},
        remark="我应付给配送商",
    )
    reversal = _make_bs(
        "RV-1", "-20.00", "client", "应付",
        {"kind": "return_reversal", "relation_type": "client_delivery", "order_ids": [10],
         "reverses_return_id": 55, "origin_statement_no": "BS-A"},
        remark="退货红冲",
    )

    out = asyncio.run(bills._serialize_statements(_EmptySession(), [normal, reversal]))
    by_no = {r["statement_no"]: r for r in out}

    assert by_no["BS-A"]["is_reversal"] is False
    assert by_no["RV-1"]["is_reversal"] is True
    assert "红冲" in by_no["RV-1"]["display_title"]
    assert by_no["RV-1"]["amount"] == -20.0


def test_reversal_notifies_only_involved_owners(monkeypatch):
    # 红冲产生 2 条（client owner=1 / supplier owner=3）→ 只推这两个账号，各自一条
    fake_reversals = [
        SimpleNamespace(id=9001, owner_user_id=1, role="client", direction="应付",
                        amount=Decimal("-20.00"),
                        source_snapshot_json={"kind": "return_reversal", "order_numbers": ["SO10"]}),
        SimpleNamespace(id=9002, owner_user_id=3, role="supplier", direction="应收",
                        amount=Decimal("-16.00"),
                        source_snapshot_json={"kind": "return_reversal", "order_numbers": ["SO10"]}),
    ]

    async def fake_reversal(db, order, order_return):
        return fake_reversals

    pushes = []

    async def fake_push(db, *, role, event_type, title, content, route, target_user_ids,
                        object_type="", object_id=0, canteen_id=None):
        pushes.append({"role": role, "targets": list(target_user_ids),
                       "object_id": object_id, "event_type": event_type})

    monkeypatch.setattr(orders, "create_return_reversal_statements", fake_reversal, raising=False)
    monkeypatch.setattr(orders, "push_notification", fake_push)

    order = SimpleNamespace(id=10, order_no="SO10", canteen_id=77, client_id=1, delivery_id=2)
    order_return = SimpleNamespace(id=55)
    db = _WireSession(statements=[_stmt("已确认")], bills=[])

    asyncio.run(orders._rebuild_unconfirmed_receive_billing(db, order, order_return))

    # 只推给涉及的 2 个 owner，各一条，不广播
    assert len(pushes) == 2
    all_targets = [t for p in pushes for t in p["targets"]]
    assert sorted(all_targets) == [1, 3]
    assert all(len(p["targets"]) == 1 for p in pushes)
    by_target = {p["targets"][0]: p for p in pushes}
    assert by_target[1]["role"] == "client"
    assert by_target[3]["role"] == "supplier"
    assert by_target[1]["object_id"] == 9001
