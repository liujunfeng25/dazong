#!/usr/bin/env python3
"""仅执行智能分单演示供货商 + 报价种子（幂等）。用法：
  docker compose exec backend python scripts/seed_smart_split_lab_only.py
  cd backend && PYTHONPATH=. python3 scripts/seed_smart_split_lab_only.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, seed_smart_split_lab_suppliers_and_quotes  # noqa: E402


async def main() -> None:
    async with SessionLocal() as session:
        await seed_smart_split_lab_suppliers_and_quotes(session)
    print("seed_smart_split_lab_suppliers_and_quotes 已完成")


if __name__ == "__main__":
    asyncio.run(main())
