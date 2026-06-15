#!/usr/bin/env python3
"""
测试环境：批量释放被未完成车次占用的车辆/订单。

将指定配送商（默认 delivery001）下状态为「待发车 / 有阻塞 / 运输中」的车次
标记为「已取消」，便于重新测试智能排线。

用法（Docker）:
  docker compose exec backend-dev python scripts/clear_active_dispatch_trips.py
  docker compose exec backend-dev python scripts/clear_active_dispatch_trips.py --delivery-id 3
  docker compose exec backend-dev python scripts/clear_active_dispatch_trips.py --dry-run

本机:
  cd backend && PYTHONPATH=. python3 scripts/clear_active_dispatch_trips.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal  # noqa: E402
from models.delivery_dispatch import DeliveryDispatchTrip  # noqa: E402
from models.users import User  # noqa: E402

ACTIVE_STATUSES = ("待发车", "有阻塞", "运输中")
DEFAULT_DELIVERY_USERNAME = "delivery001"


async def _resolve_delivery_id(session, delivery_id: int | None, username: str | None) -> int:
    if delivery_id is not None:
        row = await session.scalar(select(User).where(User.id == int(delivery_id), User.role == "delivery"))
        if not row:
            raise SystemExit(f"配送商 id={delivery_id} 不存在")
        return int(row.id)
    uname = (username or DEFAULT_DELIVERY_USERNAME).strip()
    row = await session.scalar(select(User).where(User.username == uname, User.role == "delivery"))
    if not row:
        raise SystemExit(f"配送商 username={uname!r} 不存在")
    return int(row.id)


async def main() -> None:
    parser = argparse.ArgumentParser(description="取消未完成车次，释放车辆占用（测试用）")
    parser.add_argument("--delivery-id", type=int, default=None, help="配送商 users.id，默认按 username 查")
    parser.add_argument("--username", type=str, default=DEFAULT_DELIVERY_USERNAME, help="配送商登录名")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    args = parser.parse_args()

    async with SessionLocal() as session:
        delivery_id = await _resolve_delivery_id(session, args.delivery_id, args.username)
        trips = (
            await session.scalars(
                select(DeliveryDispatchTrip)
                .where(
                    DeliveryDispatchTrip.delivery_id == delivery_id,
                    DeliveryDispatchTrip.status.in_(ACTIVE_STATUSES),
                )
                .order_by(DeliveryDispatchTrip.planning_date.asc(), DeliveryDispatchTrip.id.asc())
            )
        ).all()

        if not trips:
            print(f"配送商 id={delivery_id}：无未完成车次，车辆应已全部可用。")
            return

        print(f"配送商 id={delivery_id}：将取消 {len(trips)} 条未完成车次：")
        for t in trips:
            print(
                f"  - {t.route_no}  planning_date={t.planning_date}  status={t.status}  vehicle={t.vehicle_no}"
            )

        if args.dry_run:
            print("（dry-run，未写库）")
            return

        now = datetime.utcnow()
        reason = "测试环境批量清理占用（clear_active_dispatch_trips.py）"
        for t in trips:
            t.status = "已取消"
            t.exception_summary_json = {"cancel_reason": reason, "cleared_by_script": True}
            t.updated_at = now

        await session.commit()
        print(f"已取消 {len(trips)} 条车次，车辆与订单占用已释放。")


if __name__ == "__main__":
    asyncio.run(main())
