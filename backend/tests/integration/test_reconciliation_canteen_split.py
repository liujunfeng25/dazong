"""对账单按食堂粒度拆分：client↔delivery 腿的聚合 key 含 canteen_id。

同校两食堂的账单明细必须归并到两张对账单，镜像（应付↔应收）也不得跨食堂配对；
delivery↔supplier 腿（canteen_id 为 None）保持原样一张。
同时验证统一后的金额口径：total = 非红冲成员之和，adjust = 红冲成员之和。

全部用真实 DB（容器内 MySQL）+ 事务回滚，不污染演示库。
"""
import asyncio
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from database import SessionLocal
from models import BillingCycle, BillingStatement, ClientCanteen, ReconciliationStatement, User
from services.billing_service import attach_statement_to_reconciliation, backfill_reconciliations


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _fixtures(db):
    """取演示库现成的 client/delivery 用户与两个食堂 id，建一条测试账期规则。"""
    client = await db.scalar(select(User).where(User.role == "client"))
    delivery = await db.scalar(select(User).where(User.role == "delivery"))
    canteen_ids = (await db.scalars(select(ClientCanteen.id).limit(2))).all()
    assert client and delivery and len(canteen_ids) >= 2, "演示库缺少 client/delivery/食堂数据"
    cycle = BillingCycle(
        cycle_code=f"CYC-TEST-{uuid4().hex[:8]}",
        role="client",
        owner_user_id=int(client.id),
        cycle_type="monthly",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        close_day=1,
        confirm_due_days=3,
        payment_due_days=7,
    )
    db.add(cycle)
    await db.flush()
    return client, delivery, [int(c) for c in canteen_ids], cycle


def _statement(cycle, owner_id, cp_id, role, direction, amount, canteen_id, *, reversal=False, relation="client_delivery"):
    snap = {"relation_type": relation}
    if reversal:
        snap["kind"] = "return_reversal"
    return BillingStatement(
        statement_no=f"BS-TEST-{uuid4().hex[:10]}",
        cycle_id=int(cycle.id),
        role=role,
        owner_user_id=int(owner_id),
        counterparty_user_id=int(cp_id),
        canteen_id=canteen_id,
        direction=direction,
        status="待确认",
        amount=Decimal(amount),
        source_snapshot_json=snap,
        # created_at 为 server_default，显式赋值避免 flush 后属性过期触发同步懒加载
        created_at=datetime.utcnow(),
    )


async def _attach(db, stmt, *, owner, counterparty, direction, role, cycle, canteen_id, relation="client_delivery"):
    return await attach_statement_to_reconciliation(
        db, stmt,
        owner=owner, counterparty=counterparty,
        relation_type=relation, direction=direction, role=role,
        cycle=cycle, canteen_id=canteen_id,
    )


def test_attach_splits_reconciliations_by_canteen_and_mirrors_within_canteen():
    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, (c1, c2), cycle = await _fixtures(db)

                s1 = _statement(cycle, client.id, delivery.id, "client", "应付", "100.00", c1)
                s2 = _statement(cycle, delivery.id, client.id, "delivery", "应收", "100.00", c1)
                s3 = _statement(cycle, client.id, delivery.id, "client", "应付", "60.00", c2)
                s4 = _statement(cycle, delivery.id, client.id, "delivery", "应收", "60.00", c2)
                db.add_all([s1, s2, s3, s4])
                await db.flush()

                r1 = await _attach(db, s1, owner=client, counterparty=delivery, direction="应付", role="client", cycle=cycle, canteen_id=c1)
                r2 = await _attach(db, s2, owner=delivery, counterparty=client, direction="应收", role="delivery", cycle=cycle, canteen_id=c1)
                r3 = await _attach(db, s3, owner=client, counterparty=delivery, direction="应付", role="client", cycle=cycle, canteen_id=c2)
                r4 = await _attach(db, s4, owner=delivery, counterparty=client, direction="应收", role="delivery", cycle=cycle, canteen_id=c2)

                # 不同食堂 → 不同对账单
                assert int(r1.id) != int(r3.id), "两个食堂的应付明细不应归并到同一张对账单"
                assert int(r2.id) != int(r4.id)
                assert int(r1.canteen_id) == c1 and int(r3.canteen_id) == c2

                # 镜像只在同食堂内配对，不得跨食堂
                assert int(r1.mirror_id) == int(r2.id) and int(r2.mirror_id) == int(r1.id)
                assert int(r3.mirror_id) == int(r4.id) and int(r4.mirror_id) == int(r3.id)

                # 金额各自累计
                assert Decimal(str(r1.total_amount)) == Decimal("100.00")
                assert Decimal(str(r3.total_amount)) == Decimal("60.00")
            finally:
                await db.rollback()

    _run(check())


def test_attach_keeps_single_reconciliation_when_canteen_is_none():
    """canteen 为 None 时行为不变：同对手方同账期仍是一张。"""
    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, _, cycle = await _fixtures(db)
                s1 = _statement(cycle, delivery.id, client.id, "delivery", "应付", "40.00", None)
                s2 = _statement(cycle, delivery.id, client.id, "delivery", "应付", "25.00", None)
                db.add_all([s1, s2])
                await db.flush()

                r1 = await _attach(db, s1, owner=delivery, counterparty=client, direction="应付", role="delivery", cycle=cycle, canteen_id=None)
                r2 = await _attach(db, s2, owner=delivery, counterparty=client, direction="应付", role="delivery", cycle=cycle, canteen_id=None)

                assert int(r1.id) == int(r2.id), "canteen 为 None 时应仍归并同一张对账单"
                assert Decimal(str(r1.total_amount)) == Decimal("65.00")
            finally:
                await db.rollback()

    _run(check())


def test_supplier_leg_does_not_split_even_when_statements_carry_canteen():
    """delivery↔supplier 腿明细虽带 canteen_id（来自订单），但供货腿对账单不按食堂拆。"""
    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, (c1, c2), cycle = await _fixtures(db)
                s1 = _statement(cycle, delivery.id, client.id, "delivery", "应付", "40.00", c1, relation="delivery_supplier")
                s2 = _statement(cycle, delivery.id, client.id, "delivery", "应付", "25.00", c2, relation="delivery_supplier")
                db.add_all([s1, s2])
                await db.flush()

                r1 = await _attach(db, s1, owner=delivery, counterparty=client, direction="应付", role="delivery", cycle=cycle, canteen_id=c1, relation="delivery_supplier")
                r2 = await _attach(db, s2, owner=delivery, counterparty=client, direction="应付", role="delivery", cycle=cycle, canteen_id=c2, relation="delivery_supplier")

                assert int(r1.id) == int(r2.id), "供货腿不应按食堂拆单"
                assert r1.canteen_id is None, "供货腿对账单不应带具体食堂（避免首条明细的食堂误导）"
                assert Decimal(str(r1.total_amount)) == Decimal("65.00")
            finally:
                await db.rollback()

    _run(check())


def test_backfill_splits_by_canteen_and_routes_reversal_into_adjust():
    """重建路径：按食堂分单，红冲成员进 adjust_amount、不混入 total_amount。"""
    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, (c1, c2), cycle = await _fixtures(db)

                s1 = _statement(cycle, client.id, delivery.id, "client", "应付", "100.00", c1)
                s2 = _statement(cycle, client.id, delivery.id, "client", "应付", "60.00", c2)
                rv = _statement(cycle, client.id, delivery.id, "client", "应付", "-20.00", c1, reversal=True)
                # 供货腿明细带食堂，但回填后不应按食堂拆
                p1 = _statement(cycle, delivery.id, client.id, "delivery", "应付", "30.00", c1, relation="delivery_supplier")
                p2 = _statement(cycle, delivery.id, client.id, "delivery", "应付", "10.00", c2, relation="delivery_supplier")
                db.add_all([s1, s2, rv, p1, p2])
                await db.flush()

                await backfill_reconciliations(db, commit=False)

                r1 = await db.get(ReconciliationStatement, int(s1.reconciliation_id))
                r2 = await db.get(ReconciliationStatement, int(s2.reconciliation_id))
                assert int(s1.reconciliation_id) != int(s2.reconciliation_id)
                assert int(rv.reconciliation_id) == int(s1.reconciliation_id), "红冲应随食堂归并到同食堂对账单"

                assert Decimal(str(r1.total_amount)) == Decimal("100.00"), "total 应为非红冲成员之和"
                assert Decimal(str(r1.adjust_amount)) == Decimal("-20.00"), "红冲应累计进 adjust"
                assert Decimal(str(r2.total_amount)) == Decimal("60.00")
                assert Decimal(str(r2.adjust_amount)) == Decimal("0.00")

                assert int(p1.reconciliation_id) == int(p2.reconciliation_id), "供货腿回填不应按食堂拆"
                rp = await db.get(ReconciliationStatement, int(p1.reconciliation_id))
                assert rp.canteen_id is None
            finally:
                await db.rollback()

    _run(check())


def test_recompute_reconciliation_does_not_double_count_reversal():
    """读侧 _recompute：净额=total+adjust 只抵扣一次红冲。"""
    from routers.bills import _recompute_reconciliation

    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, (c1, _), cycle = await _fixtures(db)
                s1 = _statement(cycle, client.id, delivery.id, "client", "应付", "100.00", c1)
                db.add(s1)
                await db.flush()
                recon = await _attach(db, s1, owner=client, counterparty=delivery, direction="应付", role="client", cycle=cycle, canteen_id=c1)

                rv = _statement(cycle, client.id, delivery.id, "client", "应付", "-20.00", c1, reversal=True)
                rv.reconciliation_id = int(recon.id)
                db.add(rv)
                # 模拟落库路径：红冲累加 adjust
                recon.adjust_amount = Decimal("-20.00")
                await db.flush()

                await _recompute_reconciliation(db, recon)

                assert Decimal(str(recon.total_amount)) == Decimal("100.00"), "total 不应混入红冲负额"
                assert Decimal(str(recon.adjust_amount)) == Decimal("-20.00")
                payable = Decimal(str(recon.total_amount)) + Decimal(str(recon.adjust_amount))
                assert payable == Decimal("80.00")
            finally:
                await db.rollback()

    _run(check())
