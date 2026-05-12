#!/usr/bin/env python3
"""
幂等维护 client_canteens（与 database.seed_client_canteens_and_backfill_orders 一致）：
仅当某采购方尚无任何食堂记录时，补一条「默认食堂」；已有食堂的不改动。

Docker:
  docker compose exec backend python scripts/ensure_client_canteens_by_org.py

本机:
  cd backend && PYTHONPATH=. python3 scripts/ensure_client_canteens_by_org.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, engine, seed_client_canteens_and_backfill_orders  # noqa: E402


async def main() -> None:
    try:
        async with SessionLocal() as session:
            await seed_client_canteens_and_backfill_orders(session)
        print("已为无食堂记录的采购方补齐「默认食堂」（含订单 canteen_id 回填）。")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
