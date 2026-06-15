"""中农价格网行情物化层（单一实现，脚本与采集 worker 共用）。

把原始表 zgncpjgw_price_crawl 压成两张可秒查的派生表：
  1) zgncpjgw_daily_agg   每 (crawl_date, goods_name) → 主单位 + 中位价/均价/样本数/省覆盖
  2) zgncpjgw_price_index 每 (idx_date, cate_id) → Jevons 几何均值价比指数（cate_id=0 为全国总指数）

价格指数采用 CPI 基层指数标准做法（Jevons 几何均值价比，单位无关、抗离群）：
  index(c,t) = 100 * exp( mean_{g in 篮子c} ln( median_price[g,t] / median_price[g,base] ) )
基期 base = 数据最早日。

对外入口：refresh_derived(days)
  - days 给定：仅增量重建这些日期的 daily_agg，再全量重算 price_index（读 daily_agg，几秒）。
  - days=None：全量重建所有日期。
采集/补抓完成后调用本函数即可让指数/异动/预测"变活"。
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date
from statistics import median as _median, mean as _mean
from typing import Any, Optional

from sqlalchemy import text

from config import settings
from database import engine

RAW = settings.zgncpjgw_price_table or "zgncpjgw_price_crawl"
AGG = "zgncpjgw_daily_agg"
IDX = "zgncpjgw_price_index"

# SKU = 品名 + 一级分类(cate_id) + 二级分类(scate_name) + 规格 + 单位（五维全同才算一个 SKU）。
# 用 U+001F 拼 key（数据中不出现该字符）。
SKU_SEP = ""


def make_sku_key(goods_name: str, spec: str, unit: str, cate_id=0, scate_name: str = "") -> str:
    return SKU_SEP.join([goods_name or "", spec or "", unit or "", str(cate_id or 0), scate_name or ""])


def split_sku_key(sku_key: str) -> tuple[str, str, str, int, str]:
    parts = (sku_key or "").split(SKU_SEP)
    while len(parts) < 5:
        parts.append("")
    try:
        cate_id = int(parts[3] or 0)
    except ValueError:
        cate_id = 0
    return parts[0], parts[1], parts[2], cate_id, parts[4]


_PRICE_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _price_to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    nums = _PRICE_NUM_RE.findall(str(value).strip())
    if not nums:
        return None
    try:
        vals = [float(n) for n in nums]
    except ValueError:
        return None
    return sum(vals) / len(vals) if vals else None


async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS `{AGG}` (
                    `crawl_date` DATE NOT NULL,
                    `sku_key` VARCHAR(640) NOT NULL,
                    `goods_name` VARCHAR(256) NOT NULL,
                    `spec` VARCHAR(512) NOT NULL DEFAULT '',
                    `unit` VARCHAR(64) NOT NULL DEFAULT '',
                    `cate_id` INT NOT NULL DEFAULT 0,
                    `cate_name` VARCHAR(128) NOT NULL DEFAULT '',
                    `scate_name` VARCHAR(128) NOT NULL DEFAULT '',
                    `median_price` DECIMAL(12,2) NOT NULL DEFAULT 0,
                    `mean_price` DECIMAL(12,2) NOT NULL DEFAULT 0,
                    `sample_count` INT NOT NULL DEFAULT 0,
                    `province_count` INT NOT NULL DEFAULT 0,
                    PRIMARY KEY (`crawl_date`, `sku_key`(255)),
                    KEY `idx_agg_goods` (`goods_name`(64)),
                    KEY `idx_agg_cate_day` (`cate_id`, `crawl_date`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
                """
            )
        )
        await conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS `{IDX}` (
                    `idx_date` DATE NOT NULL,
                    `cate_id` INT NOT NULL,
                    `cate_name` VARCHAR(128) NOT NULL DEFAULT '',
                    `index_value` DECIMAL(10,3) NOT NULL DEFAULT 100,
                    `basket_size` INT NOT NULL DEFAULT 0,
                    PRIMARY KEY (`idx_date`, `cate_id`),
                    KEY `idx_index_cate` (`cate_id`, `idx_date`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )


async def all_raw_days() -> list[date]:
    async with engine.connect() as conn:
        res = await conn.execute(text(f"SELECT DISTINCT crawl_date FROM `{RAW}` ORDER BY crawl_date"))
        return [r[0] for r in res.fetchall()]


async def build_agg_for_day(day: date) -> int:
    """重建某日的 daily_agg：拉该日全部行，按 **SKU(品名,规格,单位,分类,子类)** 聚合各省中位价。幂等。"""
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                f"SELECT goods_name, spec, unit, cate_id, cate_name, scate_name, district_name, price "
                f"FROM `{RAW}` WHERE crawl_date = :d"
            ),
            {"d": day},
        )
        rows = res.fetchall()

    # 质量规则在物化入口统一执行：高风险/人工隔离 SKU 不进入日聚合，
    # 确保指数、异动与预测训练继承同一份干净口径。
    from database import SessionLocal
    from services.zg_data_quality import quality_map_for_days, should_exclude_quality, sync_quality_flags_for_day

    async with SessionLocal() as quality_db:
        await sync_quality_flags_for_day(quality_db, day, raw_rows=list(rows))
        quality_map = await quality_map_for_days(quality_db, [day], sync_missing=False)
        await quality_db.commit()

    by_sku: dict[str, dict] = {}
    for gn, spec, unit, cate_id, cate_name, scate_name, district, price in rows:
        if not gn:
            continue
        p = _price_to_float(price)
        if p is None:
            continue
        key = make_sku_key(gn, spec or "", unit or "", cate_id or 0, scate_name or "")
        quality_meta = quality_map.get((day, key, district or ""))
        if should_exclude_quality(quality_meta, "strict"):
            continue
        if quality_meta and quality_meta.get("corrected_price") is not None:
            p = float(quality_meta["corrected_price"])
        s = by_sku.setdefault(
            key,
            {"gn": gn, "spec": spec or "", "unit": unit or "", "cate_id": cate_id or 0,
             "cate_name": cate_name or "", "scate_name": scate_name or "", "prices": [], "prov": set()},
        )
        s["prices"].append(p)
        if district:
            s["prov"].add(district)

    out = []
    for key, s in by_sku.items():
        prices = s["prices"]
        out.append(
            {
                "d": day, "sku": key, "gn": s["gn"], "spec": s["spec"], "unit": s["unit"],
                "cid": s["cate_id"], "cname": s["cate_name"], "scname": s["scate_name"],
                "med": round(_median(prices), 2), "mean": round(_mean(prices), 2),
                "n": len(prices), "prov": len(s["prov"]),
            }
        )

    async with engine.begin() as conn:
        await conn.execute(text(f"DELETE FROM `{AGG}` WHERE crawl_date = :d"), {"d": day})
        for i in range(0, len(out), 1000):
            chunk = out[i : i + 1000]
            await conn.execute(
                text(
                    f"""
                    INSERT INTO `{AGG}`
                      (crawl_date, sku_key, goods_name, spec, unit, cate_id, cate_name, scate_name, median_price, mean_price, sample_count, province_count)
                    VALUES (:d, :sku, :gn, :spec, :unit, :cid, :cname, :scname, :med, :mean, :n, :prov)
                    ON DUPLICATE KEY UPDATE
                      goods_name=VALUES(goods_name), spec=VALUES(spec), unit=VALUES(unit),
                      cate_id=VALUES(cate_id), cate_name=VALUES(cate_name), scate_name=VALUES(scate_name),
                      median_price=VALUES(median_price), mean_price=VALUES(mean_price),
                      sample_count=VALUES(sample_count), province_count=VALUES(province_count)
                    """
                ),
                chunk,
            )
    return len(out)


async def rebuild_index() -> int:
    """从 daily_agg 重算全部价格指数（Jevons 几何均值价比）。"""
    async with engine.connect() as conn:
        days_res = await conn.execute(text(f"SELECT DISTINCT crawl_date FROM `{AGG}` ORDER BY crawl_date"))
        days = [r[0] for r in days_res.fetchall()]
        if not days:
            return 0
        base = days[0]
        base_res = await conn.execute(
            text(f"SELECT sku_key, median_price FROM `{AGG}` WHERE crawl_date = :d AND median_price > 0"),
            {"d": base},
        )
        base_price = {sku: float(p) for sku, p in base_res.fetchall()}
        cat_res = await conn.execute(
            text(f"SELECT sku_key, cate_id, cate_name FROM `{AGG}` WHERE crawl_date = :d"),
            {"d": base},
        )
        sku_cate = {sku: (cid, cname) for sku, cid, cname in cat_res.fetchall()}

    rows_out = []
    async with engine.connect() as conn:
        for day in days:
            res = await conn.execute(
                text(f"SELECT sku_key, median_price FROM `{AGG}` WHERE crawl_date = :d AND median_price > 0"),
                {"d": day},
            )
            from database import SessionLocal
            from services.zg_data_quality import quality_map_for_days, quality_weight

            async with SessionLocal() as quality_db:
                quality_map = await quality_map_for_days(quality_db, [day], sync_missing=False)
            acc_sum: dict[int, float] = defaultdict(float)
            acc_cnt: dict[int, float] = defaultdict(float)
            cate_label: dict[int, str] = {0: "全国总指数"}
            for sku, p in res.fetchall():
                bp = base_price.get(sku)
                if not bp or bp <= 0 or float(p) <= 0:
                    continue
                rel = math.log(float(p) / bp)
                cid, cname = sku_cate.get(sku, (0, ""))
                weight = quality_weight(quality_map.get((day, sku, "")))
                acc_sum[cid] += rel * weight
                acc_cnt[cid] += weight
                cate_label[cid] = cname or cate_label.get(cid, "")
                acc_sum[0] += rel * weight
                acc_cnt[0] += weight
            for cid, cnt in acc_cnt.items():
                if cnt <= 0:
                    continue
                idx_val = round(100.0 * math.exp(acc_sum[cid] / cnt), 3)
                rows_out.append(
                    {
                        "d": day,
                        "cid": cid,
                        "cname": cate_label.get(cid, ""),
                        "iv": idx_val,
                        "bs": int(round(cnt)),
                    }
                )

    async with engine.begin() as conn:
        await conn.execute(text(f"DELETE FROM `{IDX}`"))
        for i in range(0, len(rows_out), 1000):
            chunk = rows_out[i : i + 1000]
            await conn.execute(
                text(
                    f"""
                    INSERT INTO `{IDX}` (idx_date, cate_id, cate_name, index_value, basket_size)
                    VALUES (:d, :cid, :cname, :iv, :bs)
                    """
                ),
                chunk,
            )
    return len(rows_out)


async def refresh_derived(days: Optional[list[date]] = None, progress=None) -> dict[str, Any]:
    """对外入口：补抓/采集后调用。days 给定则增量重建这些日的 daily_agg；否则全量。最后重算 price_index。

    progress: 可选回调 progress(done:int, total:int, label:str)，用于前端展示重建进度（总步数=日数+1，最后一步为重算指数）。
    """
    await ensure_tables()
    target = days if days else await all_raw_days()
    total = len(target) + 1  # +1 为最后的指数重算
    agg_rows = 0
    done = 0
    if progress:
        progress(0, total, "准备重建派生指标…")
    for day in target:
        agg_rows += await build_agg_for_day(day)
        done += 1
        if progress:
            progress(done, total, f"重建日聚合 {day.isoformat()}")
    if progress:
        progress(done, total, "重算价格指数…")
    idx_rows = await rebuild_index()
    if progress:
        progress(total, total, "派生指标重建完成")
    return {"days": len(target), "agg_rows": agg_rows, "index_rows": idx_rows}
