"""二次爬虫核验：针对疑似脏数据 SKU 定向重抓并对比官网是否已修正。"""
from __future__ import annotations

from datetime import date
from statistics import median
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.zg_data_quality import (
    HIGH_RATIO,
    MEDIUM_RATIO,
    ensure_quality_table,
    now_naive,
    parse_evidence,
    sync_quality_flags_for_day,
)
from services.zg_materialize import _price_to_float, refresh_derived, split_sku_key

RAW_TBL = settings.zgncpjgw_price_table or "zgncpjgw_price_crawl"
QUALITY_TBL = "data_quality_flags"

RecrawlRunner = Callable[[date, set[int], int], Awaitable[None]]


def prices_changed(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    rel_threshold: float = 0.005,
    abs_threshold: float = 0.01,
) -> bool:
    """任一关键省份价格相对/绝对变化超过阈值则视为官网已更新。"""
    for key in ("min_price", "max_price"):
        old = before.get(key)
        new = after.get(key)
        if old is None or new is None:
            continue
        old_f, new_f = float(old), float(new)
        if abs(new_f - old_f) > abs_threshold:
            return True
        if old_f > 0 and abs(new_f - old_f) / old_f > rel_threshold:
            return True
    return False


def quality_action_status(action: str) -> Optional[str]:
    """人工处置 action → 目标 status（不含已废弃的 confirm）。"""
    return {
        "correct": "corrected",
        "isolate": "quarantined",
        "restore": "open",
    }.get((action or "").strip().lower())


async def _district_ids_for_names(db: AsyncSession, names: list[str]) -> set[int]:
    uniq = sorted({n.strip() for n in names if n and str(n).strip()})
    if not uniq:
        return set()
    placeholders = ", ".join(f":n{i}" for i in range(len(uniq)))
    params = {f"n{i}": name for i, name in enumerate(uniq)}
    result = await db.execute(
        text(
            f"""
            SELECT DISTINCT district_id, district_name
            FROM `{RAW_TBL}`
            WHERE district_name IN ({placeholders}) AND district_id IS NOT NULL
            """
        ),
        params,
    )
    return {int(row.district_id) for row in result.fetchall() if row.district_id is not None}


async def _sku_province_prices(
    db: AsyncSession,
    *,
    data_date: date,
    goods_name: str,
    spec: str,
    unit: str,
    cate_id: int,
    scate_name: str,
    provinces: list[str],
) -> dict[str, float]:
    uniq = sorted({p.strip() for p in provinces if p and str(p).strip()})
    if not uniq:
        return {}
    placeholders = ", ".join(f":p{i}" for i in range(len(uniq)))
    params: dict[str, Any] = {
        "d": data_date,
        "gn": goods_name,
        "spec": spec or "",
        "unit": unit or "",
        "cate_id": cate_id,
        "scate": scate_name or "",
    }
    for i, prov in enumerate(uniq):
        params[f"p{i}"] = prov
    result = await db.execute(
        text(
            f"""
            SELECT district_name, price
            FROM `{RAW_TBL}`
            WHERE crawl_date = :d
              AND goods_name = :gn
              AND IFNULL(spec, '') = :spec
              AND IFNULL(unit, '') = :unit
              AND IFNULL(cate_id, 0) = :cate_id
              AND IFNULL(scate_name, '') = :scate
              AND district_name IN ({placeholders})
            """
        ),
        params,
    )
    buckets: dict[str, list[float]] = {}
    for row in result.fetchall():
        prov = str(row.district_name or "").strip()
        price = _price_to_float(row.price)
        if prov and price is not None and price > 0:
            buckets.setdefault(prov, []).append(float(price))
    return {prov: float(median(vals)) for prov, vals in buckets.items() if vals}


def _ratio_from_prices(min_price: Optional[float], max_price: Optional[float]) -> Optional[float]:
    if min_price is None or max_price is None or min_price <= 0:
        return None
    return round(max_price / min_price, 3)


def _build_price_snapshot(
    evidence: dict[str, Any],
    province_prices: dict[str, float],
) -> dict[str, Any]:
    min_prov = str(evidence.get("min_province") or "")
    max_prov = str(evidence.get("max_province") or "")
    min_price = province_prices.get(min_prov)
    if min_price is None and evidence.get("min_price") is not None:
        min_price = float(evidence["min_price"])
    max_price = province_prices.get(max_prov)
    if max_price is None and evidence.get("max_price") is not None:
        max_price = float(evidence["max_price"])
    return {
        "min_province": min_prov,
        "min_price": min_price,
        "max_province": max_prov,
        "max_price": max_price,
        "ratio": _ratio_from_prices(min_price, max_price),
    }


async def verify_flag_by_recrawl(
    db: AsyncSession,
    flag_id: int,
    *,
    run_recrawl: RecrawlRunner,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    await ensure_quality_table(db)
    row_res = await db.execute(
        text(
            f"""
            SELECT id, data_date, sku_key, goods_name, evidence_json, status
            FROM `{QUALITY_TBL}`
            WHERE id = :id
            """
        ),
        {"id": flag_id},
    )
    flag = row_res.fetchone()
    if not flag:
        raise ValueError("质量标记不存在")

    evidence = parse_evidence(flag.evidence_json)
    goods_name, spec, unit, cate_id, scate_name = split_sku_key(flag.sku_key)
    data_date = flag.data_date
    min_prov = str(evidence.get("min_province") or "")
    max_prov = str(evidence.get("max_province") or "")
    provinces = [p for p in (min_prov, max_prov) if p]

    before_prices = await _sku_province_prices(
        db,
        data_date=data_date,
        goods_name=goods_name,
        spec=spec,
        unit=unit,
        cate_id=cate_id,
        scate_name=scate_name,
        provinces=provinces,
    )
    before = _build_price_snapshot(evidence, before_prices)

    district_ids = await _district_ids_for_names(db, provinces)
    if not district_ids:
        raise ValueError(f"无法解析省份 district_id：{', '.join(provinces) or '—'}")

    await run_recrawl(data_date, district_ids, cate_id)

    after_prices = await _sku_province_prices(
        db,
        data_date=data_date,
        goods_name=goods_name,
        spec=spec,
        unit=unit,
        cate_id=cate_id,
        scate_name=scate_name,
        provinces=provinces,
    )
    after = _build_price_snapshot(evidence, after_prices)
    updated = prices_changed(before, after)

    reviewed_at = now_naive()
    if updated:
        await refresh_derived([data_date])
        await sync_quality_flags_for_day(db, data_date, commit=True)
        refreshed = await db.execute(
            text(f"SELECT status, evidence_json, reason FROM `{QUALITY_TBL}` WHERE id = :id"),
            {"id": flag_id},
        )
        refreshed_row = refreshed.fetchone()
        flag_status = str(refreshed_row.status if refreshed_row else flag.status)
        note = "二次爬虫核验：官网价格已更新，本地数据已同步"
        if flag_status == "resolved":
            message = "官网价格已更新，跨省倍数已恢复正常，本地数据已同步"
        elif after.get("ratio") and float(after["ratio"]) > HIGH_RATIO:
            message = "官网价格已更新，本地数据已同步，但跨省倍数仍偏高，请继续关注或考虑隔离"
        elif after.get("ratio") and float(after["ratio"]) > MEDIUM_RATIO:
            message = "官网价格已更新，本地数据已同步，跨省倍数仍有关注级偏差"
        else:
            message = "官网价格已更新，本地数据已同步"
    else:
        flag_status = str(flag.status)
        note = "二次爬虫核验：数据未变化"
        message = "二次爬虫确认数据并未更新，疑似录入方尚未修正，可继续观察或执行隔离"

    await db.execute(
        text(
            f"""
            UPDATE `{QUALITY_TBL}`
            SET review_note = :note,
                reviewed_by_user_id = :uid,
                reviewed_at = :reviewed_at
            WHERE id = :id
            """
        ),
        {"id": flag_id, "note": note, "uid": user_id, "reviewed_at": reviewed_at},
    )
    await db.commit()

    if updated:
        refreshed = await db.execute(
            text(f"SELECT status FROM `{QUALITY_TBL}` WHERE id = :id"),
            {"id": flag_id},
        )
        row = refreshed.fetchone()
        if row:
            flag_status = str(row.status)

    return {
        "updated": updated,
        "goods_name": str(flag.goods_name or goods_name),
        "before": before,
        "after": after,
        "message": message,
        "flag_status": flag_status,
        "review_note": note,
    }
