"""P3c 退货红冲：对账单已确认后再发生退货时，按增量扣减生成负额红冲计划。

核心算法是纯函数 compute_return_reversals，不碰 DB：喂入订单现有账单明细、
对账单状态、退货行、分摊行，产出一批红冲计划（负额，挂回原对账单）。
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from models import BillingStatement, OrderReturnLine, ReconciliationStatement
from services.billing_service import compute_return_reversals, create_return_reversal_statements


def _cd_statements(deduction_already=0.0):
    """客户↔配送 一对已挂确认对账单的账单明细。"""
    snap = {
        "relation_type": "client_delivery",
        "orders": [{"order_id": 10, "deduction_amount": deduction_already}],
    }
    return [
        SimpleNamespace(
            role="client", owner_user_id=1, counterparty_user_id=2, direction="应付",
            reconciliation_id=500, amount=Decimal("100.00"), statement_no="BS-A",
            source_snapshot_json=dict(snap),
        ),
        SimpleNamespace(
            role="delivery", owner_user_id=2, counterparty_user_id=1, direction="应收",
            reconciliation_id=501, amount=Decimal("100.00"), statement_no="BS-B",
            source_snapshot_json=dict(snap),
        ),
    ]


def _supplier_leg_statements():
    """配送↔供货 一对已挂确认对账单的明细；快照里带 allocations（含供货价）。"""
    snap = {
        "relation_type": "delivery_supplier",
        "orders": [{"order_id": 10, "deduction_amount": 0.0}],
        "allocations": [
            {"allocation_id": 101, "product_id": 201, "unit_price": 8.0, "quantity": 5.0, "deduction_amount": 0.0},
        ],
    }
    return [
        SimpleNamespace(
            role="delivery", owner_user_id=2, counterparty_user_id=3, direction="应付",
            reconciliation_id=600, amount=Decimal("40.00"), statement_no="BS-S1",
            source_snapshot_json=dict(snap),
        ),
        SimpleNamespace(
            role="supplier", owner_user_id=3, counterparty_user_id=2, direction="应收",
            reconciliation_id=601, amount=Decimal("40.00"), statement_no="BS-S2",
            source_snapshot_json=dict(snap),
        ),
    ]


def test_supplier_leg_reversal_uses_supplier_price():
    # 客户售价 10/kg → 客户侧扣减 20；供货价 8/kg → 供货侧红冲 16（证明用供货价而非售价）
    statements = _cd_statements(deduction_already=0.0) + _supplier_leg_statements()
    recon_status = {500: "已确认", 501: "已确认", 600: "已确认", 601: "已确认"}
    return_lines = [
        SimpleNamespace(product_id=201, delta_kg=Decimal("2"), deduction_amount=Decimal("20.00")),
    ]

    plans = compute_return_reversals(
        statements=statements, recon_status=recon_status,
        return_lines=return_lines, allocations=[],
    )

    by_key = {(p["role"], p["owner_user_id"], p["counterparty_user_id"], p["direction"]): p for p in plans}
    # 客户↔配送 一对 -20，配送↔供货 一对 -16，共 4 条
    assert len(plans) == 4
    assert by_key[("client", 1, 2, "应付")]["amount"] == Decimal("-20.00")
    assert by_key[("delivery", 2, 1, "应收")]["amount"] == Decimal("-20.00")
    assert by_key[("delivery", 2, 3, "应付")]["amount"] == Decimal("-16.00")
    assert by_key[("delivery", 2, 3, "应付")]["reconciliation_id"] == 600
    assert by_key[("supplier", 3, 2, "应收")]["amount"] == Decimal("-16.00")
    assert by_key[("supplier", 3, 2, "应收")]["reconciliation_id"] == 601


def _reversal_statements(amount, role, owner, counterparty, direction, recon_id, relation="client_delivery"):
    """已落库的红冲明细（负额），用于验证幂等。"""
    return SimpleNamespace(
        role=role, owner_user_id=owner, counterparty_user_id=counterparty, direction=direction,
        reconciliation_id=recon_id, amount=Decimal(amount), statement_no="RV-X",
        source_snapshot_json={"kind": "return_reversal", "relation_type": relation,
                              "orders": [{"order_id": 10, "deduction_amount": 0.0}]},
    )


def test_reversal_is_idempotent_with_prior_reversal_present():
    # 首次红冲 -20 已落库；同样的退货再算一次不应再产出红冲。
    statements = _cd_statements(deduction_already=0.0) + [
        _reversal_statements("-20.00", "client", 1, 2, "应付", 500),
        _reversal_statements("-20.00", "delivery", 2, 1, "应收", 501),
    ]
    recon_status = {500: "已确认", 501: "已确认"}
    return_lines = [
        SimpleNamespace(product_id=201, delta_kg=Decimal("2"), deduction_amount=Decimal("20.00")),
    ]

    plans = compute_return_reversals(
        statements=statements, recon_status=recon_status,
        return_lines=return_lines, allocations=[],
    )
    assert plans == []


def test_reversal_tops_up_when_return_grows_after_prior_reversal():
    # 首次已红冲 -20；退货又扩大到累计应扣 30 → 只补红冲增量 -10。
    statements = _cd_statements(deduction_already=0.0) + [
        _reversal_statements("-20.00", "client", 1, 2, "应付", 500),
        _reversal_statements("-20.00", "delivery", 2, 1, "应收", 501),
    ]
    recon_status = {500: "已确认", 501: "已确认"}
    return_lines = [
        SimpleNamespace(product_id=201, delta_kg=Decimal("3"), deduction_amount=Decimal("30.00")),
    ]

    plans = compute_return_reversals(
        statements=statements, recon_status=recon_status,
        return_lines=return_lines, allocations=[],
    )
    amounts = {p["role"]: p["amount"] for p in plans}
    assert amounts["client"] == Decimal("-10.00")
    assert amounts["delivery"] == Decimal("-10.00")


def test_client_delivery_reversal_when_recon_confirmed():
    statements = _cd_statements(deduction_already=0.0)
    recon_status = {500: "已确认", 501: "已确认"}
    return_lines = [
        SimpleNamespace(product_id=201, delta_kg=Decimal("2"), deduction_amount=Decimal("20.00")),
    ]

    plans = compute_return_reversals(
        statements=statements,
        recon_status=recon_status,
        return_lines=return_lines,
        allocations=[],
    )

    by_key = {(p["role"], p["owner_user_id"], p["counterparty_user_id"], p["direction"]): p for p in plans}
    assert len(plans) == 2
    assert by_key[("client", 1, 2, "应付")]["amount"] == Decimal("-20.00")
    assert by_key[("client", 1, 2, "应付")]["reconciliation_id"] == 500
    assert by_key[("client", 1, 2, "应付")]["origin_statement_no"] == "BS-A"
    assert by_key[("delivery", 2, 1, "应收")]["amount"] == Decimal("-20.00")
    assert by_key[("delivery", 2, 1, "应收")]["reconciliation_id"] == 501


def test_reversal_is_incremental_over_already_billed_deduction():
    # 账单已体现 5.00 扣减，本次退货累计应扣 20.00 → 只红冲增量 15.00
    statements = _cd_statements(deduction_already=5.0)
    recon_status = {500: "已确认", 501: "已确认"}
    return_lines = [
        SimpleNamespace(product_id=201, delta_kg=Decimal("2"), deduction_amount=Decimal("20.00")),
    ]

    plans = compute_return_reversals(
        statements=statements, recon_status=recon_status,
        return_lines=return_lines, allocations=[],
    )

    amounts = {p["role"]: p["amount"] for p in plans}
    assert amounts["client"] == Decimal("-15.00")
    assert amounts["delivery"] == Decimal("-15.00")


def test_no_reversal_when_recon_not_confirmed():
    # 对账单仍进行中 → 不红冲（由现有重算逻辑改原额）
    statements = _cd_statements(deduction_already=0.0)
    recon_status = {500: "进行中", 501: "待确认"}
    return_lines = [
        SimpleNamespace(product_id=201, delta_kg=Decimal("2"), deduction_amount=Decimal("20.00")),
    ]

    plans = compute_return_reversals(
        statements=statements, recon_status=recon_status,
        return_lines=return_lines, allocations=[],
    )
    assert plans == []


def test_no_reversal_when_no_incremental_deduction():
    # 账单已体现的扣减 >= 本次累计应扣 → 无增量，不红冲
    statements = _cd_statements(deduction_already=20.0)
    recon_status = {500: "已确认", 501: "已确认"}
    return_lines = [
        SimpleNamespace(product_id=201, delta_kg=Decimal("2"), deduction_amount=Decimal("20.00")),
    ]

    plans = compute_return_reversals(
        statements=statements, recon_status=recon_status,
        return_lines=return_lines, allocations=[],
    )
    assert plans == []


class _ShellSession:
    """壳测试用假会话：按模型类型分发查询。"""

    def __init__(self, order_statements, recons, return_lines):
        self._order_statements = order_statements
        self._recons = {int(r.id): r for r in recons}
        self._return_lines = return_lines
        self.added = []
        self._next_id = 9000

    async def get(self, model, row_id):
        if model is ReconciliationStatement:
            return self._recons.get(int(row_id))
        return None

    async def scalars(self, stmt):
        s = str(stmt)
        if "order_return_lines" in s:
            return _Rows(self._return_lines)
        if "billing_statements" in s:
            return _Rows(self._order_statements)
        return _Rows([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def _bs(role, owner, cp, direction, recon_id, statement_no, cycle_id=7):
    snap = {"relation_type": "client_delivery", "order_ids": [10],
            "orders": [{"order_id": 10, "deduction_amount": 0.0}]}
    return BillingStatement(
        id=hash(statement_no) % 1000, statement_no=statement_no, cycle_id=cycle_id,
        reconciliation_id=recon_id, role=role, owner_user_id=owner, counterparty_user_id=cp,
        direction=direction, status="已确认", amount=Decimal("100.00"),
        source_snapshot_json=snap, canteen_id=77,
    )


def test_shell_creates_negative_statements_and_bumps_adjust_amount():
    order = SimpleNamespace(id=10, order_no="SO10", client_id=1, delivery_id=2, canteen_id=77)
    order_return = SimpleNamespace(id=55)
    order_statements = [
        _bs("client", 1, 2, "应付", 500, "BS-A"),
        _bs("delivery", 2, 1, "应收", 501, "BS-B"),
    ]
    recons = [
        ReconciliationStatement(
            id=500, statement_no="RC-500", relation_type="client_delivery", cycle_id=7,
            role="client", owner_user_id=1, counterparty_user_id=2, direction="应付",
            period_label="2026-06", status="已确认", total_amount=Decimal("100.00"),
            adjust_amount=Decimal("0.00"), settled_amount=Decimal("0.00"), item_count=1,
        ),
        ReconciliationStatement(
            id=501, statement_no="RC-501", relation_type="client_delivery", cycle_id=7,
            role="delivery", owner_user_id=2, counterparty_user_id=1, direction="应收",
            period_label="2026-06", status="已确认", total_amount=Decimal("100.00"),
            adjust_amount=Decimal("0.00"), settled_amount=Decimal("0.00"), item_count=1,
        ),
    ]
    return_lines = [
        OrderReturnLine(order_return_id=55, line_index=1, product_id=201, product_name="白菜",
                        ordered_kg=Decimal("5"), received_kg=Decimal("3"), delta_kg=Decimal("2"),
                        reason_code="short", deduction_amount=Decimal("20.00")),
    ]

    db = _ShellSession(order_statements, recons, return_lines)
    created = asyncio.run(create_return_reversal_statements(db, order, order_return))

    assert len(created) == 2
    assert all(isinstance(s, BillingStatement) for s in created)
    assert all(Decimal(str(s.amount)) == Decimal("-20.00") for s in created)
    assert all((s.source_snapshot_json or {}).get("kind") == "return_reversal" for s in created)
    assert all((s.source_snapshot_json or {}).get("reverses_return_id") == 55 for s in created)
    # 对账单：adjust_amount 累加负值、item_count +1、total_amount 不变
    by_id = {int(r.id): r for r in recons}
    assert Decimal(str(by_id[500].adjust_amount)) == Decimal("-20.00")
    assert Decimal(str(by_id[500].total_amount)) == Decimal("100.00")
    assert by_id[500].item_count == 2
    assert Decimal(str(by_id[501].adjust_amount)) == Decimal("-20.00")
    assert by_id[501].item_count == 2
