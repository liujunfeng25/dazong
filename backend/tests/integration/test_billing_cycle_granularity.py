"""账期规则颗粒化：client↔delivery 腿派生规则细到食堂，未定制规则跟随全局。

- 同校两食堂 → 各派生一条规则，参数继承全局；
- 全局规则修改后，未定制（is_customized=False）的派生规则在下次解析时同步参数；
  已定制的保持独立；
- delivery↔supplier 腿无食堂概念：传入任何 canteen_id 都命中同一条对子规则。

全部用真实 DB（容器内 MySQL）+ 事务回滚，不污染演示库。
"""
import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from database import SessionLocal
from models import ClientCanteen, User
from services.billing_service import (
    _active_cycle_for_pair,
    ensure_relation_billing_rule,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _fixtures(db):
    client = await db.scalar(select(User).where(User.role == "client"))
    delivery = await db.scalar(select(User).where(User.role == "delivery"))
    canteen_ids = (await db.scalars(select(ClientCanteen.id).limit(2))).all()
    assert client and delivery and len(canteen_ids) >= 2, "演示库缺少 client/delivery/食堂数据"
    return client, delivery, [int(c) for c in canteen_ids]


async def _resolve(db, owner, cp, relation, canteen_id):
    return await _active_cycle_for_pair(
        db,
        owner_user_id=int(owner.id),
        role=str(owner.role),
        counterparty_user_id=int(cp.id),
        relation_type=relation,
        canteen_id=canteen_id,
    )


def test_two_canteens_derive_two_cycles_inheriting_global():
    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, (c1, c2) = await _fixtures(db)
                rule = await ensure_relation_billing_rule(db, "client_delivery")

                a = await _resolve(db, client, delivery, "client_delivery", c1)
                b = await _resolve(db, client, delivery, "client_delivery", c2)

                assert int(a.id) != int(b.id), "两个食堂应各派生一条账期规则"
                assert int(a.canteen_id) == c1 and int(b.canteen_id) == c2
                for cyc in (a, b):
                    assert cyc.cycle_type == rule.cycle_type
                    assert int(cyc.close_day) == int(rule.close_day)
                    assert int(cyc.confirm_due_days) == int(rule.confirm_due_days)
                    assert int(cyc.payment_due_days) == int(rule.payment_due_days)
                    assert not bool(cyc.is_customized)
            finally:
                await db.rollback()

    _run(check())


def test_uncustomized_follows_global_but_customized_stays():
    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, (c1, _) = await _fixtures(db)
                rule = await ensure_relation_billing_rule(db, "client_delivery")

                derived = await _resolve(db, client, delivery, "client_delivery", c1)
                assert not bool(derived.is_customized)

                # 改全局 → 未定制的派生规则在下次解析时同步
                rule.close_day = 9
                rule.payment_due_days = 21
                await db.flush()
                again = await _resolve(db, client, delivery, "client_delivery", c1)
                assert int(again.id) == int(derived.id)
                assert int(again.close_day) == 9, "未定制规则应跟随全局参数"
                assert int(again.payment_due_days) == 21

                # 定制后 → 不再跟随
                again.is_customized = True
                again.close_day = 15
                await db.flush()
                rule.close_day = 3
                await db.flush()
                third = await _resolve(db, client, delivery, "client_delivery", c1)
                assert int(third.id) == int(derived.id)
                assert int(third.close_day) == 15, "已定制规则不应被全局覆盖"
            finally:
                await db.rollback()

    _run(check())


def test_supplier_leg_ignores_canteen():
    async def check():
        async with SessionLocal() as db:
            try:
                _, delivery, (c1, c2) = await _fixtures(db)
                supplier = await db.scalar(select(User).where(User.role == "supplier"))
                assert supplier, "演示库缺少 supplier"

                a = await _resolve(db, delivery, supplier, "delivery_supplier", c1)
                b = await _resolve(db, delivery, supplier, "delivery_supplier", c2)

                assert int(a.id) == int(b.id), "供货腿不应按食堂派生规则"
                assert a.canteen_id is None
            finally:
                await db.rollback()

    _run(check())


def test_both_legs_of_pair_share_one_canonical_cycle():
    """同一结算对子的应付/应收两腿必须共用一条规则（否则单边定制会导致镜像账期错位）。"""
    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, (c1, _) = await _fixtures(db)
                # 应付腿：owner=client；应收镜像腿：owner=delivery, counterparty=client
                pay_leg = await _resolve(db, client, delivery, "client_delivery", c1)
                recv_leg = await _active_cycle_for_pair(
                    db,
                    owner_user_id=int(delivery.id),
                    role="delivery",
                    counterparty_user_id=int(client.id),
                    relation_type="client_delivery",
                    canteen_id=c1,
                )
                assert int(pay_leg.id) == int(recv_leg.id), "两腿应共用同一条规则，定制才能双边一致"
                assert pay_leg.role == "client", "client_delivery 规则应归一到 client 侧"
            finally:
                await db.rollback()

    _run(check())


def test_canteen_lookup_is_null_safe():
    async def check():
        async with SessionLocal() as db:
            try:
                client, delivery, (c1, _) = await _fixtures(db)
                with_canteen = await _resolve(db, client, delivery, "client_delivery", c1)
                without = await _resolve(db, client, delivery, "client_delivery", None)
                assert int(with_canteen.id) != int(without.id), "None 与具体食堂不应命中同一条规则"
                assert without.canteen_id is None
            finally:
                await db.rollback()

    _run(check())
