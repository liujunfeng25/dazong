#!/usr/bin/env python3
"""
物化中农价格网行情（薄壳，逻辑在 services/zg_materialize.py，与采集 worker 单一实现）。

产出两张派生表：zgncpjgw_daily_agg + zgncpjgw_price_index（Jevons 几何均值价比指数）。

用法：
  docker compose exec backend python scripts/build_zgncpjgw_agg_index.py            # 全量回填
  docker compose exec backend python scripts/build_zgncpjgw_agg_index.py --date 2026-05-31  # 仅重建某日 daily_agg 再重算指数
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import engine  # noqa: E402
from services.zg_materialize import refresh_derived  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="", help="仅重建该日 daily_agg（YYYY-MM-DD），随后重算指数")
    args = parser.parse_args()

    days = [date.fromisoformat(args.date)] if args.date else None
    result = await refresh_derived(days)
    print(f"[zg_materialize] 完成：处理 {result['days']} 天，daily_agg {result['agg_rows']} 行，price_index {result['index_rows']} 行", flush=True)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
