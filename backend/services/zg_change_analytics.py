"""涨跌比例 / 涨跌幅排名：统计日价 vs 前 N 日均价（日），周/月为首末日对比。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median as _stat_median
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.zg_materialize import make_sku_key, _price_to_float

RAW_TBL = settings.zgncpjgw_price_table or "zgncpjgw_price_crawl"
AGG_TBL = "zgncpjgw_daily_agg"
IDX_TBL = "zgncpjgw_price_index"


def _sku_label(goods_name: str, spec: str, unit: str) -> str:
    if spec:
        return f"{goods_name} {spec}".strip()
    return goods_name + (f"（{unit}）" if unit else "")


def _parse_day(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip().replace("/", "-").split()[0])
    except ValueError:
        return None


def _fmt_day(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


def _cn_day_label(d: date) -> str:
    return f"{d.year}年{d.month}月{d.day}日"


def _week_bounds(latest: date) -> tuple[date, date]:
    """自然周区间：统计日若为本周周一，则用上一完整自然周（周一至周日）。"""
    this_monday = latest - timedelta(days=latest.weekday())
    if latest == this_monday:
        week_end = this_monday - timedelta(days=1)
        week_start = week_end - timedelta(days=6)
    else:
        week_start = this_monday
        week_end = latest
    return week_start, week_end


def _month_bounds(latest: date) -> tuple[date, date]:
    """自然月区间：统计日若为月初，则用上一完整自然月。"""
    first_of_month = latest.replace(day=1)
    if latest == first_of_month:
        month_end = first_of_month - timedelta(days=1)
        month_start = month_end.replace(day=1)
    else:
        month_start = first_of_month
        month_end = latest
    return month_start, month_end


def _cn_range_label(start: date, end: date) -> str:
    if start == end:
        return _cn_day_label(start)
    if start.year == end.year and start.month == end.month:
        return f"{start.year}年{start.month}月{start.day}日-{end.day}日"
    if start.year == end.year:
        return f"{start.year}年{start.month}月{start.day}日-{end.month}月{end.day}日"
    return f"{start.year}年{start.month}月{start.day}日-{end.year}年{end.month}月{end.day}日"


async def _resolve_latest(db: AsyncSession) -> Optional[date]:
    res = await db.execute(text(f"SELECT MAX(idx_date) AS mx FROM `{IDX_TBL}`"))
    row = res.fetchone()
    latest = _parse_day(row.mx) if row and row.mx else None
    if latest is not None:
        return latest
    res = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{AGG_TBL}`"))
    row = res.fetchone()
    return _parse_day(row.mx) if row and row.mx else None


def _classify_pct(pct: float, flat_threshold: float) -> str:
    if pct > flat_threshold:
        return "up"
    if pct < -flat_threshold:
        return "down"
    return "flat"


def _ratio_bucket(recs: list[float], flat_threshold: float) -> dict[str, Any]:
    up = flat = down = 0
    for pct in recs:
        kind = _classify_pct(pct, flat_threshold)
        if kind == "up":
            up += 1
        elif kind == "down":
            down += 1
        else:
            flat += 1
    total = up + flat + down
    if total <= 0:
        return {
            "total_skus": 0,
            "up_count": 0,
            "flat_count": 0,
            "down_count": 0,
            "up_pct": 0.0,
            "flat_pct": 0.0,
            "down_pct": 0.0,
            "dominant": "flat",
            "dominant_pct": 0.0,
        }
    up_pct = round(up / total * 100, 2)
    flat_pct = round(flat / total * 100, 2)
    down_pct = round(down / total * 100, 2)
    dominant, dominant_pct = ("up", up_pct)
    if flat_pct >= up_pct and flat_pct >= down_pct:
        dominant, dominant_pct = "flat", flat_pct
    elif down_pct > up_pct:
        dominant, dominant_pct = "down", down_pct
    return {
        "total_skus": total,
        "up_count": up,
        "flat_count": flat,
        "down_count": down,
        "up_pct": up_pct,
        "flat_pct": flat_pct,
        "down_pct": down_pct,
        "dominant": dominant,
        "dominant_pct": dominant_pct,
    }


async def _load_province_snaps(
    db: AsyncSession,
    days: list[date],
    *,
    district_id: int,
    cate_id: Optional[int],
    scate: str,
) -> tuple[dict[date, dict[str, dict[str, Any]]], str]:
    if not days:
        return {}, ""
    tbl = RAW_TBL
    clauses = ["district_id = :did"]
    params: dict[str, Any] = {"did": int(district_id)}
    if cate_id is not None:
        clauses.append("cate_id = :cid")
        params["cid"] = cate_id
    if scate.strip():
        clauses.append("scate_name = :scate")
        params["scate"] = scate.strip()
    in_ph = ", ".join(f":d{i}" for i in range(len(days)))
    for i, d in enumerate(days):
        params[f"d{i}"] = d
    clauses.append(f"crawl_date IN ({in_ph})")
    res = await db.execute(
        text(
            f"SELECT crawl_date, goods_name, spec, unit, cate_id, cate_name, scate_name, district_name, price "
            f"FROM `{tbl}` WHERE {' AND '.join(clauses)}"
        ),
        params,
    )
    district_name = ""
    prices: dict[date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    meta: dict[str, dict[str, Any]] = {}
    for r in res.fetchall():
        if not district_name and r.district_name:
            district_name = str(r.district_name)
        v = _price_to_float(r.price)
        if v is None or v <= 0:
            continue
        day = r.crawl_date
        sk = make_sku_key(r.goods_name, r.spec or "", r.unit or "", r.cate_id or 0, r.scate_name or "")
        prices[day][sk].append(v)
        if sk not in meta:
            label = _sku_label(r.goods_name, r.spec or "", r.unit or "")
            if r.scate_name:
                label = f"{label} · {r.scate_name}"
            meta[sk] = {
                "sku_key": sk,
                "label": label,
                "cate_id": int(r.cate_id or 0),
                "cate_name": r.cate_name or "",
            }
    out: dict[date, dict[str, dict[str, Any]]] = {}
    for day, sku_prices in prices.items():
        out[day] = {}
        for sk, vals in sku_prices.items():
            m = meta[sk]
            out[day][sk] = {**m, "p": float(_stat_median(vals)), "prov": 1}
    return out, district_name


async def _load_national_snaps(
    db: AsyncSession,
    days: list[date],
    *,
    cate_id: Optional[int],
    scate: str,
) -> dict[date, dict[str, dict[str, Any]]]:
    if not days:
        return {}
    clauses = ["median_price > 0"]
    params: dict[str, Any] = {}
    if cate_id is not None:
        clauses.append("cate_id = :cid")
        params["cid"] = cate_id
    if scate.strip():
        clauses.append("scate_name = :scate")
        params["scate"] = scate.strip()
    in_ph = ", ".join(f":d{i}" for i in range(len(days)))
    for i, d in enumerate(days):
        params[f"d{i}"] = d
    clauses.append(f"crawl_date IN ({in_ph})")
    res = await db.execute(
        text(
            f"SELECT crawl_date, sku_key, goods_name, spec, unit, cate_id, cate_name, scate_name, "
            f"median_price, province_count FROM `{AGG_TBL}` WHERE {' AND '.join(clauses)}"
        ),
        params,
    )
    out: dict[date, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in res.fetchall():
        label = _sku_label(r.goods_name, r.spec or "", r.unit or "")
        if r.scate_name:
            label = f"{label} · {r.scate_name}"
        out[r.crawl_date][r.sku_key] = {
            "sku_key": r.sku_key,
            "label": label,
            "goods_name": label,
            "cate_id": int(r.cate_id or 0),
            "cate_name": r.cate_name or "",
            "p": float(r.median_price),
            "prov": int(r.province_count or 0),
        }
    return dict(out)


async def _load_all_snaps(
    db: AsyncSession,
    days: list[date],
    *,
    district_id: Optional[int],
    cate_id: Optional[int],
    scate: str,
) -> tuple[dict[date, dict[str, dict[str, Any]]], str]:
    uniq = sorted(set(days))
    if district_id is not None:
        return await _load_province_snaps(
            db, uniq, district_id=int(district_id), cate_id=cate_id, scate=scate
        )
    snaps = await _load_national_snaps(db, uniq, cate_id=cate_id, scate=scate)
    return snaps, ""


def _pct_vs_baseline_avg(
    cur: dict[str, Any],
    snaps: dict[date, dict[str, dict[str, Any]]],
    latest: date,
    baseline_days: int,
    *,
    min_provinces: int,
    skip_min_provinces: bool,
    max_pct: float,
) -> Optional[tuple[float, float, float]]:
    base_prices: list[float] = []
    sk = cur.get("sku_key") or ""
    for i in range(1, baseline_days + 1):
        d = latest - timedelta(days=i)
        row = snaps.get(d, {}).get(sk)
        if not row or row["p"] <= 0.5:
            return None
        if not skip_min_provinces and int(row.get("prov") or 0) < min_provinces:
            return None
        base_prices.append(float(row["p"]))
    if len(base_prices) < baseline_days:
        return None
    if cur["p"] <= 0.5:
        return None
    if not skip_min_provinces and int(cur.get("prov") or 0) < min_provinces:
        return None
    baseline_avg = sum(base_prices) / baseline_days
    if baseline_avg <= 0:
        return None
    pct = (cur["p"] - baseline_avg) / baseline_avg * 100
    if abs(pct) > max_pct:
        return None
    return pct, round(baseline_avg, 2), round(float(cur["p"]), 2)


def _pct_period_end_vs_start(
    snaps: dict[date, dict[str, dict[str, Any]]],
    end_day: date,
    start_day: date,
    *,
    min_provinces: int,
    skip_min_provinces: bool,
    max_pct: float,
) -> list[float]:
    end_snap = snaps.get(end_day) or {}
    start_snap = snaps.get(start_day) or {}
    out: list[float] = []
    for sk, cur in end_snap.items():
        start_row = start_snap.get(sk)
        if not start_row or start_row["p"] <= 0.5 or cur["p"] <= 0.5:
            continue
        if not skip_min_provinces:
            if int(cur.get("prov") or 0) < min_provinces or int(start_row.get("prov") or 0) < min_provinces:
                continue
        pct = (cur["p"] - start_row["p"]) / start_row["p"] * 100
        if abs(pct) > max_pct:
            continue
        out.append(pct)
    return out


def _collect_day_pcts(
    snaps: dict[date, dict[str, dict[str, Any]]],
    latest: date,
    baseline_days: int,
    *,
    min_provinces: int,
    skip_min_provinces: bool,
    max_pct: float,
) -> list[float]:
    cur_snap = snaps.get(latest) or {}
    pcts: list[float] = []
    for sk, cur in cur_snap.items():
        cur = {**cur, "sku_key": sk}
        row = _pct_vs_baseline_avg(
            cur, snaps, latest, baseline_days,
            min_provinces=min_provinces, skip_min_provinces=skip_min_provinces, max_pct=max_pct,
        )
        if row:
            pcts.append(row[0])
    return pcts


def _build_ranking_rows(
    snaps: dict[date, dict[str, dict[str, Any]]],
    latest: date,
    baseline_days: int,
    *,
    min_provinces: int,
    skip_min_provinces: bool,
    max_pct: float,
) -> list[dict[str, Any]]:
    cur_snap = snaps.get(latest) or {}
    recs: list[dict[str, Any]] = []
    for sk, cur in cur_snap.items():
        cur = {**cur, "sku_key": sk}
        row = _pct_vs_baseline_avg(
            cur, snaps, latest, baseline_days,
            min_provinces=min_provinces, skip_min_provinces=skip_min_provinces, max_pct=max_pct,
        )
        if not row:
            continue
        pct, baseline_avg, new_p = row
        recs.append({
            "sku_key": sk,
            "label": cur["label"],
            "goods_name": cur["label"],
            "cate_id": cur["cate_id"],
            "cate_name": cur["cate_name"],
            "old": baseline_avg,
            "new": new_p,
            "pct": round(pct, 1),
        })
    return recs


async def compute_change_ranking(
    db: AsyncSession,
    *,
    district_id: Optional[int] = None,
    cate_id: Optional[int] = None,
    scate: str = "",
    baseline_days: int = 3,
    limit: int = 10,
    max_pct: float = 150.0,
    min_provinces: int = 6,
) -> dict[str, Any]:
    latest = await _resolve_latest(db)
    if latest is None:
        return {
            "latest_date": "",
            "baseline_days": baseline_days,
            "district_id": district_id,
            "district_name": "",
            "gainers": [],
            "losers": [],
        }
    need_days = [latest - timedelta(days=i) for i in range(baseline_days + 1)]
    snaps, district_name = await _load_all_snaps(
        db, need_days, district_id=district_id, cate_id=cate_id, scate=scate
    )
    skip_min_provinces = district_id is not None
    recs = _build_ranking_rows(
        snaps, latest, baseline_days,
        min_provinces=min_provinces, skip_min_provinces=skip_min_provinces, max_pct=max_pct,
    )
    gainers = sorted([r for r in recs if r["pct"] > 0], key=lambda x: x["pct"], reverse=True)[:limit]
    losers = sorted([r for r in recs if r["pct"] < 0], key=lambda x: x["pct"])[:limit]
    return {
        "latest_date": _fmt_day(latest),
        "baseline_days": baseline_days,
        "district_id": district_id,
        "district_name": district_name,
        "gainers": gainers,
        "losers": losers,
    }


async def compute_change_ratio(
    db: AsyncSession,
    *,
    district_id: Optional[int] = None,
    cate_id: Optional[int] = None,
    scate: str = "",
    baseline_days: int = 3,
    flat_threshold_pct: float = 1.0,
    max_pct: float = 150.0,
    min_provinces: int = 6,
) -> dict[str, Any]:
    latest = await _resolve_latest(db)
    empty_period = {
        "label": "",
        "start_date": "",
        "end_date": "",
        "total_skus": 0,
        "up_count": 0,
        "flat_count": 0,
        "down_count": 0,
        "up_pct": 0.0,
        "flat_pct": 0.0,
        "down_pct": 0.0,
        "dominant": "flat",
        "dominant_pct": 0.0,
    }
    if latest is None:
        return {
            "latest_date": "",
            "baseline_days": baseline_days,
            "flat_threshold_pct": flat_threshold_pct,
            "district_id": district_id,
            "district_name": "",
            "day": empty_period,
            "week": empty_period,
            "month": empty_period,
        }

    week_start, week_end = _week_bounds(latest)
    month_start, month_end = _month_bounds(latest)
    need_days_set: set[date] = {latest}
    for i in range(1, baseline_days + 1):
        need_days_set.add(latest - timedelta(days=i))
    d = week_start
    while d <= week_end:
        need_days_set.add(d)
        d += timedelta(days=1)
    d = month_start
    while d <= month_end:
        need_days_set.add(d)
        d += timedelta(days=1)

    snaps, district_name = await _load_all_snaps(
        db, sorted(need_days_set), district_id=district_id, cate_id=cate_id, scate=scate
    )
    skip_min_provinces = district_id is not None

    day_pcts = _collect_day_pcts(
        snaps, latest, baseline_days,
        min_provinces=min_provinces, skip_min_provinces=skip_min_provinces, max_pct=max_pct,
    )
    day_bucket = _ratio_bucket(day_pcts, flat_threshold_pct)
    day_period = {
        **day_bucket,
        "label": _cn_day_label(latest),
        "start_date": _fmt_day(latest),
        "end_date": _fmt_day(latest),
    }

    week_pcts = _pct_period_end_vs_start(
        snaps, week_end, week_start,
        min_provinces=min_provinces, skip_min_provinces=skip_min_provinces, max_pct=max_pct,
    )
    week_bucket = _ratio_bucket(week_pcts, flat_threshold_pct)
    week_period = {
        **week_bucket,
        "label": _cn_range_label(week_start, week_end),
        "start_date": _fmt_day(week_start),
        "end_date": _fmt_day(week_end),
    }

    month_pcts = _pct_period_end_vs_start(
        snaps, month_end, month_start,
        min_provinces=min_provinces, skip_min_provinces=skip_min_provinces, max_pct=max_pct,
    )
    month_bucket = _ratio_bucket(month_pcts, flat_threshold_pct)
    month_period = {
        **month_bucket,
        "label": _cn_range_label(month_start, month_end),
        "start_date": _fmt_day(month_start),
        "end_date": _fmt_day(month_end),
    }

    return {
        "latest_date": _fmt_day(latest),
        "baseline_days": baseline_days,
        "flat_threshold_pct": flat_threshold_pct,
        "district_id": district_id,
        "district_name": district_name,
        "day": day_period,
        "week": week_period,
        "month": month_period,
    }
