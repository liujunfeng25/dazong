"""Rebuild ZG quality flags and all derived analytics.

Usage:
    python scripts/rebuild_zg_data_quality.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, engine
from services.zg_data_quality import ensure_quality_table
from services.zg_materialize import all_raw_days, refresh_derived


async def main() -> None:
    async with SessionLocal() as db:
        await ensure_quality_table(db)
        await db.commit()
    days = await all_raw_days()
    print(f"rebuilding quality and derived analytics for {len(days)} days")

    def progress(done: int, total: int, label: str) -> None:
        print(f"[{done}/{total}] {label}")

    result = await refresh_derived(days, progress=progress)
    async with SessionLocal() as db:
        await db.execute(text("DELETE FROM zgncpjgw_forecast_snapshots"))
        await db.commit()
    print({**result, "forecast_snapshots_invalidated": True})
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
