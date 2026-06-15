#!/usr/bin/env python3
"""
一次性迁移：把对账单从「学校(client 用户)粒度」重建为「食堂粒度」。

步骤：
  1. 给 client↔delivery 腿中 canteen_id 为空的账单明细，从订单回填 canteen_id；
  2. 留底旧对账单（按 我方×对手方×relation×方向×账期 聚合 settled/confirmed_at）；
  3. 清空 reconciliation_statements + 明细 reconciliation_id 置空；
  4. 用新聚合 key（含食堂）重跑 backfill_reconciliations，状态由成员明细推断重建；
  5. 旧「部分结清」的已结金额按新拆出各单的应付净额比例分摊（舍入差额放最后一张）。

幂等可重跑：分摊按比例确定性分配，重跑结果一致。

用法（Docker）:
  docker compose exec backend-dev python scripts/rebuild_reconciliations_by_canteen.py
  docker compose exec backend-dev python scripts/rebuild_reconciliations_by_canteen.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select, update

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal  # noqa: E402
from models import BillingStatement, Order, ReconciliationStatement  # noqa: E402
from services.billing_service import backfill_reconciliations  # noqa: E402


def _key(row) -> tuple:
    return (
        int(row.owner_user_id),
        int(row.counterparty_user_id),
        str(getattr(row, "relation_type", "") or ""),
        str(row.direction),
        str(row.period_label),
    )


async def _backfill_statement_canteens(db) -> int:
    """client↔delivery 腿明细缺 canteen_id 的，经快照 order_ids → orders.canteen_id 回填。"""
    rows = (
        await db.scalars(select(BillingStatement).where(BillingStatement.canteen_id.is_(None)))
    ).all()
    fixed = 0
    for s in rows:
        snap = s.source_snapshot_json or {}
        if snap.get("relation_type") != "client_delivery":
            continue
        order_ids = [int(x) for x in (snap.get("order_ids") or []) if x]
        if not order_ids:
            continue
        cid = await db.scalar(
            select(Order.canteen_id).where(Order.id.in_(order_ids), Order.canteen_id.isnot(None)).limit(1)
        )
        if cid is not None:
            s.canteen_id = int(cid)
            fixed += 1
    await db.flush()
    return fixed


async def _snapshot_old(db) -> dict[tuple, dict]:
    """旧对账单留底。同 key 多张（已按食堂拆过再重跑时）合并：settled 求和、confirmed_at 取最早。"""
    old: dict[tuple, dict] = {}
    rows = (await db.scalars(select(ReconciliationStatement))).all()
    for r in rows:
        k = _key(r)
        ent = old.setdefault(k, {"settled": Decimal("0.00"), "confirmed_at": None, "statuses": Counter()})
        ent["settled"] += Decimal(str(r.settled_amount or 0))
        ent["statuses"][str(r.status)] += 1
        if r.confirmed_at and (ent["confirmed_at"] is None or r.confirmed_at < ent["confirmed_at"]):
            ent["confirmed_at"] = r.confirmed_at
    return old


async def _redistribute_settlements(db, old: dict[tuple, dict]) -> int:
    """把旧单已结金额回填到重建后的同 key 各食堂单：缺口按应付净额比例分摊。"""
    rows = (await db.scalars(select(ReconciliationStatement))).all()
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[_key(r)].append(r)

    touched = 0
    for k, recons in groups.items():
        ent = old.get(k)
        if not ent:
            continue
        if ent["confirmed_at"]:
            for r in recons:
                if r.confirmed_at is None and str(r.status) in ("已确认", "部分结清", "已结清"):
                    r.confirmed_at = ent["confirmed_at"]
        current = sum((Decimal(str(r.settled_amount or 0)) for r in recons), Decimal("0.00"))
        deficit = (ent["settled"] - current).quantize(Decimal("0.01"))
        if deficit <= 0:
            continue
        # 按应付净额比例分摊（确定性：按 id 排序，舍入差额放最后一张），上限不超过各自净额
        targets = sorted(recons, key=lambda r: int(r.id))
        payables = {
            int(r.id): max(
                Decimal("0.00"),
                (Decimal(str(r.total_amount or 0)) + Decimal(str(r.adjust_amount or 0))
                 - Decimal(str(r.settled_amount or 0))),
            )
            for r in targets
        }
        room_total = sum(payables.values(), Decimal("0.00"))
        if room_total <= 0:
            continue
        deficit = min(deficit, room_total)
        remaining = deficit
        for i, r in enumerate(targets):
            room = payables[int(r.id)]
            if i == len(targets) - 1:
                add = min(remaining, room)
            else:
                add = min((deficit * room / room_total).quantize(Decimal("0.01")), room, remaining)
            if add <= 0:
                continue
            r.settled_amount = (Decimal(str(r.settled_amount or 0)) + add).quantize(Decimal("0.01"))
            payable = Decimal(str(r.total_amount or 0)) + Decimal(str(r.adjust_amount or 0))
            r.status = "已结清" if r.settled_amount >= payable else "部分结清"
            remaining -= add
            touched += 1
    await db.flush()
    return touched


async def run(dry_run: bool) -> None:
    async with SessionLocal() as db:
        fixed = await _backfill_statement_canteens(db)
        old = await _snapshot_old(db)
        old_settled_total = sum((e["settled"] for e in old.values()), Decimal("0.00"))

        await db.execute(update(BillingStatement).values(reconciliation_id=None))
        await db.execute(delete(ReconciliationStatement))
        await db.flush()
        db.expire_all()

        n = await backfill_reconciliations(db, commit=False)
        redistributed = await _redistribute_settlements(db, old)

        recons = (await db.scalars(select(ReconciliationStatement))).all()
        by_status = Counter(str(r.status) for r in recons)
        new_settled_total = sum((Decimal(str(r.settled_amount or 0)) for r in recons), Decimal("0.00"))
        split_count = sum(1 for r in recons if r.canteen_id is not None)

        print(f"明细补食堂: {fixed} 条")
        print(f"旧对账单组(留底 key): {len(old)} 组，旧已结总额 ¥{old_settled_total}")
        print(f"重挂明细: {n} 条 → 重建对账单: {len(recons)} 张（带食堂 {split_count} 张）")
        print(f"状态分布: {dict(by_status)}")
        print(f"已结金额回填: 动了 {redistributed} 张，新已结总额 ¥{new_settled_total}")
        if new_settled_total != old_settled_total:
            print(f"⚠ 已结总额差异 ¥{(old_settled_total - new_settled_total).quantize(Decimal('0.01'))}"
                  "（旧单超额结清/无可分摊空间时会出现，请人工核对）")

        if dry_run:
            await db.rollback()
            print("dry-run：已回滚，库未改动")
        else:
            await db.commit()
            print("已提交")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="对账单按食堂粒度重建")
    parser.add_argument("--dry-run", action="store_true", help="只演练并打印结果，不落库")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
