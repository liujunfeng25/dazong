#!/usr/bin/env python3
"""中农价格网派生数据准确度自检：核对 SKU 口径下 daily_agg / price_index 与原始表是否一致。

用法：docker compose exec backend python scripts/validate_zgncpjgw.py
打印每项 PASS/FAIL。
"""
from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path
from statistics import median

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import engine  # noqa: E402
from services.zg_materialize import RAW, AGG, IDX, make_sku_key, _price_to_float  # noqa: E402

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"  [{PASS if ok else FAIL}] {name}{(' — ' + detail) if detail else ''}", flush=True)


async def main() -> None:
    async with engine.connect() as conn:
        latest = (await conn.execute(text(f"SELECT MAX(crawl_date) FROM `{AGG}`"))).scalar()
        print(f"最新日：{latest}", flush=True)

        # 1) 抽样 5 个 SKU：daily_agg.median_price == 原始表该 SKU 当日各省价中位数（手算）
        skus = (await conn.execute(
            text(f"SELECT goods_name, spec, unit, median_price FROM `{AGG}` WHERE crawl_date=:d ORDER BY province_count DESC LIMIT 5"),
            {"d": latest},
        )).fetchall()
        all_ok = True
        for gn, spec, unit, agg_med in skus:
            rows = (await conn.execute(
                text(f"SELECT price FROM `{RAW}` WHERE crawl_date=:d AND goods_name=:g AND spec=:s AND unit=:u"),
                {"d": latest, "g": gn, "s": spec, "u": unit},
            )).fetchall()
            vals = [v for v in (_price_to_float(r[0]) for r in rows) if v is not None]
            manual = round(median(vals), 2) if vals else None
            ok = manual is not None and abs(float(agg_med) - manual) < 0.01
            all_ok = all_ok and ok
            if not ok:
                print(f"     ✗ {gn} {spec}: agg={agg_med} manual={manual}", flush=True)
        check("daily_agg 中位价 == 原始表手算（5 个 SKU）", all_ok)

        # 2) 可乐 听 vs 箱 各归各、价格量级分离
        can = (await conn.execute(
            text(f"SELECT median_price FROM `{AGG}` WHERE crawl_date=:d AND goods_name='[可口可乐]可乐' AND spec='330ml/听'"),
            {"d": latest},
        )).scalar()
        box = (await conn.execute(
            text(f"SELECT median_price FROM `{AGG}` WHERE crawl_date=:d AND goods_name='[可口可乐]可乐' AND spec='330ml*24听/箱'"),
            {"d": latest},
        )).scalar()
        ok = can is not None and box is not None and float(can) < 5 and float(box) > 20
        check("可乐 330ml/听 与 整箱 已分离且量级正确", ok, f"听={can} 箱={box}")

        # 3) 指数 base=100，且抽样 SKU 的 ln 价比与库内一致（重算一个分类的几何均值价比，对比接口表）
        idx_base = (await conn.execute(text(f"SELECT MIN(idx_date) FROM `{IDX}`"))).scalar()
        base_overall = (await conn.execute(
            text(f"SELECT index_value FROM `{IDX}` WHERE cate_id=0 AND idx_date=:d"), {"d": idx_base},
        )).scalar()
        check("价格指数基期=100", base_overall is not None and abs(float(base_overall) - 100.0) < 0.01, f"base={base_overall}")

        # 重算最新日总指数：对比 price_index 表
        base_prices = {sku: float(p) for sku, p in (await conn.execute(
            text(f"SELECT sku_key, median_price FROM `{AGG}` WHERE crawl_date=:d AND median_price>0"), {"d": idx_base},
        )).fetchall()}
        cur_rows = (await conn.execute(
            text(f"SELECT sku_key, median_price FROM `{AGG}` WHERE crawl_date=:d AND median_price>0"), {"d": latest},
        )).fetchall()
        logs = []
        for sku, p in cur_rows:
            bp = base_prices.get(sku)
            if bp and bp > 0 and float(p) > 0:
                logs.append(math.log(float(p) / bp))
        recomputed = round(100.0 * math.exp(sum(logs) / len(logs)), 3) if logs else None
        stored = (await conn.execute(
            text(f"SELECT index_value FROM `{IDX}` WHERE cate_id=0 AND idx_date=:d"), {"d": latest},
        )).scalar()
        ok = recomputed is not None and stored is not None and abs(recomputed - float(stored)) < 0.2
        check("最新日总指数 重算 == 接口表", ok, f"recomputed={recomputed} stored={stored}")

        # 3.5) 鲜/冻同名同规格同单位 → 两条不同 SKU、价不同（分类/子类进 key）
        ph = (await conn.execute(
            text(f"SELECT scate_name, median_price FROM `{AGG}` WHERE crawl_date=:d AND goods_name='[双汇]猪蹄' AND spec='散装' AND unit='斤' ORDER BY scate_name"),
            {"d": latest},
        )).fetchall()
        scates = {r[0]: float(r[1]) for r in ph}
        ok = len(scates) >= 2 and len(set(round(v, 2) for v in scates.values())) >= 2
        check("双汇猪蹄 鲜/冻 为两条不同 SKU 且价不同", ok, str({k: v for k, v in scates.items()}))

        # 4) daily_agg 同 sku_key 内单位恒定（口径纯净，无跨单位混淆）
        bad = (await conn.execute(
            text(f"SELECT COUNT(*) FROM (SELECT sku_key, COUNT(DISTINCT unit) u FROM `{AGG}` WHERE crawl_date=:d GROUP BY sku_key HAVING u>1) t"),
            {"d": latest},
        )).scalar()
        check("每个 SKU 单位恒定（无跨单位混淆）", int(bad or 0) == 0, f"违例 {bad} 个")

    print(f"\n汇总：{sum(results)}/{len(results)} PASS", flush=True)
    await engine.dispose()
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
