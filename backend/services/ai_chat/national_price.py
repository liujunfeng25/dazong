"""全国农产品价格（zgncpjgw）— 监管 AI 问答数据源。"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.zg_materialize import make_sku_key, split_sku_key

AGG_TBL = "zgncpjgw_daily_agg"
FORECAST_TBL = "zgncpjgw_forecast_snapshots"

_TIME_STRIP_WORDS = (
    "昨天", "昨日", "今天", "今日", "前天", "明天", "明日", "后天",
    "上周", "本周", "这周", "最近", "近期", "历史", "走势", "行情",
    "价格", "价钱", "多少钱", "什么价", "参考价", "预测", "大概",
    "大约", "左右", "一下", "查询", "查一下", "给我", "请问", "的",
    "多少", "怎么样", "如何", "是什么", "什么", "一周前", "上个月",
)
_GRADE_HINTS = ("一级", "二级", "三级", "四级", "手选", "散装", "精品")


@dataclass
class ParsedPriceQuery:
    raw_text: str
    product_query: str
    goods_name_hint: str
    grade_hint: str
    target_date: Optional[date]
    intent: Literal["history", "forecast", "history_range"]


def parse_price_query(text_value: str) -> ParsedPriceQuery:
    """从自然语言问价中提取品名、等级、目标日期与意图。"""
    raw = (text_value or "").strip()
    t = raw
    target_date: Optional[date] = None
    today = _today()

    m = re.search(r"(\d{1,2})\s*天前", t)
    if m:
        target_date = today - timedelta(days=int(m.group(1)))
    elif "一周前" in t or "上个星期" in t:
        target_date = today - timedelta(days=7)
    elif any(k in t for k in ("前天",)):
        target_date = today - timedelta(days=2)
    elif any(k in t for k in ("昨天", "昨日")):
        target_date = today - timedelta(days=1)
    elif any(k in t for k in ("今天", "今日", "当天")):
        target_date = today

    grade_hint = ""
    for g in _GRADE_HINTS:
        if g in t:
            grade_hint = g
            break

    future_hit = any(k in t for k in ("明天", "明日", "明儿", "后天", "未来", "以后", "下周", "预测"))
    history_range_hit = any(k in t for k in ("历史", "走势", "趋势", "最近", "近期"))
    if future_hit and not target_date:
        intent: Literal["history", "forecast", "history_range"] = "forecast"
    elif history_range_hit or (target_date and not future_hit):
        intent = "history_range" if history_range_hit and not target_date else "history"
    else:
        intent = "history" if target_date else "forecast" if future_hit else "history_range"

    cleaned = t
    for word in sorted(
        (
            *_TIME_STRIP_WORDS,
            "明儿", "明儿个", "未来", "以后", "下周", "公斤", "一斤", "一公斤",
            "全国农产品", "中农价格网", "新发地", "批发价", "菜价",
        ),
        key=len,
        reverse=True,
    ):
        cleaned = cleaned.replace(word, "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，。！？?、.")

    goods_name_hint = ""
    m_name = re.search(r"([\u4e00-\u9fffA-Za-z0-9（）()·\-\[\]]{2,32})", cleaned)
    if m_name:
        goods_name_hint = m_name.group(1).strip()
        if "（" in goods_name_hint:
            goods_name_hint = goods_name_hint.split("（")[0].strip()
        else:
            goods_name_hint = goods_name_hint.split()[0] if goods_name_hint.split() else goods_name_hint

    product_query = cleaned
    if grade_hint and grade_hint not in product_query:
        product_query = f"{product_query} {grade_hint}".strip()
    if not product_query and goods_name_hint:
        product_query = f"{goods_name_hint} {grade_hint}".strip() if grade_hint else goods_name_hint
    if product_query in {"西红柿", "圣女果番茄"}:
        product_query = "番茄"
        goods_name_hint = "番茄"
    if product_query == "马铃薯":
        product_query = "土豆"
        goods_name_hint = "土豆"

    return ParsedPriceQuery(
        raw_text=raw,
        product_query=product_query[:48],
        goods_name_hint=goods_name_hint[:24],
        grade_hint=grade_hint,
        target_date=target_date,
        intent=intent,
    )


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _fmt_day(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return fallback


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def sku_label(goods_name: str, spec: str, unit: str) -> str:
    if spec:
        return f"{goods_name} {spec}".strip()
    return goods_name + (f"（{unit}）" if unit else "")


def _attach_sku_labels(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base_counts = Counter((it["goods_name"], it.get("spec", ""), it.get("unit", "")) for it in items)
    out = []
    for it in items:
        gn, spec, unit = it["goods_name"], it.get("spec", "") or "", it.get("unit", "") or ""
        label = sku_label(gn, spec, unit)
        scate = it.get("scate_name", "") or ""
        if base_counts[(gn, spec, unit)] > 1 and scate:
            label = f"{label} · {scate}"
        out.append({
            **it,
            "sku_key": make_sku_key(gn, spec, unit, it.get("cate_id", 0), scate),
            "label": label,
        })
    return out


async def _latest_agg_date(db: AsyncSession) -> Optional[date]:
    res = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{AGG_TBL}`"))
    row = res.fetchone()
    if not row or not row.mx:
        return None
    raw = row.mx
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


async def search_sku_candidates(db: AsyncSession, query: str, limit: int = 20) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    latest = await _latest_agg_date(db)
    if latest is None:
        return []
    res = await db.execute(
        text(
            f"""
            SELECT goods_name, spec, unit, cate_id, cate_name, scate_name, province_count, sample_count
            FROM `{AGG_TBL}`
            WHERE crawl_date = :d AND goods_name LIKE :q AND median_price > 0
            ORDER BY province_count DESC, sample_count DESC, goods_name
            LIMIT :lim
            """
        ),
        {"d": latest, "q": f"%{q}%", "lim": limit},
    )
    items = [
        {
            "goods_name": r.goods_name,
            "spec": r.spec or "",
            "unit": r.unit or "",
            "cate_id": r.cate_id or 0,
            "cate_name": r.cate_name or "",
            "scate_name": r.scate_name or "",
        }
        for r in res.fetchall()
        if r.goods_name
    ]
    return _attach_sku_labels(items)


def pick_one_sku(
    raw_query: str,
    candidates: list[dict[str, Any]],
    *,
    grade_hint: str = "",
) -> tuple[Optional[str], list[str]]:
    """返回 (sku_key, label_list_for_ambiguous)。"""
    if not candidates:
        return None, []
    if grade_hint:
        graded = [c for c in candidates if grade_hint in str(c.get("label") or "")]
        if len(graded) == 1:
            return str(graded[0].get("sku_key") or ""), [str(c.get("label") or "") for c in candidates]
        if len(graded) > 1:
            candidates = graded
    labels = [str(c.get("label") or "").strip() for c in candidates if str(c.get("label") or "").strip()]
    keys = [str(c.get("sku_key") or "") for c in candidates]
    q = str(raw_query or "").strip()
    q_low = q.lower()
    for c in candidates:
        lb = str(c.get("label") or "").strip()
        if lb == q or lb.replace(" ", "") == q.replace(" ", ""):
            return str(c.get("sku_key") or ""), labels
    exact = [(k, lb) for k, lb in zip(keys, labels) if lb.lower() == q_low]
    if len(exact) == 1:
        return exact[0][0], labels
    starts = [(k, lb) for k, lb in zip(keys, labels) if lb.lower().startswith(q_low) or q_low in lb.lower()]
    if len(starts) == 1:
        return starts[0][0], labels
    # 同一品名多规格：用户只说了「土豆」「大白菜」等短词时，取覆盖度最高的第一条
    exact_goods = [c for c in candidates if str(c.get("goods_name") or "").strip() == q]
    if exact_goods:
        return str(exact_goods[0].get("sku_key") or ""), labels
    name_hits = [
        c for c in candidates
        if q in str(c.get("goods_name") or "") or str(c.get("goods_name") or "").startswith(q)
    ]
    if name_hits:
        goods_names = {str(c.get("goods_name") or "") for c in name_hits}
        if len(goods_names) == 1:
            return str(name_hits[0].get("sku_key") or ""), labels
    if len(candidates) == 1:
        return keys[0], labels
    return None, labels


async def resolve_sku_from_parsed(
    db: AsyncSession,
    parsed: ParsedPriceQuery,
) -> tuple[Optional[str], list[str], str]:
    """返回 (sku_key, labels, product_label)。"""
    search_q = parsed.goods_name_hint or parsed.product_query.split("（")[0].split()[0]
    if not search_q:
        return None, [], ""
    candidates = await search_sku_candidates(db, search_q, limit=20)
    sku_key, labels = pick_one_sku(
        parsed.product_query or search_q,
        candidates,
        grade_hint=parsed.grade_hint,
    )
    product_label = labels[0] if sku_key and labels else ""
    if sku_key:
        product_label, _ = await _series_for_sku(db, sku_key)
    return sku_key, labels, product_label


async def _series_for_sku(db: AsyncSession, sku_key: str) -> tuple[str, list[dict[str, Any]]]:
    name, spec, unit, _cate_id, scate = split_sku_key(sku_key)
    if not name:
        return "", []
    res = await db.execute(
        text(
            f"""
            SELECT crawl_date, median_price
            FROM `{AGG_TBL}`
            WHERE sku_key = :sk AND median_price > 0
            ORDER BY crawl_date
            """
        ),
        {"sk": sku_key},
    )
    rows = [{"date": _fmt_day(r.crawl_date), "avg_price": float(r.median_price)} for r in res.fetchall()]
    label = sku_label(name, spec, unit) + (f" · {scate}" if scate else "")
    return label, rows


async def _load_snapshot(
    db: AsyncSession,
    sku_key: str,
    days: int,
) -> Optional[dict[str, Any]]:
    res = await db.execute(
        text(
            f"""
            SELECT forecast_json, metrics_json, sample_count, data_latest_date, trained_at, winner_model
            FROM `{FORECAST_TBL}`
            WHERE sku_key = :sk AND scope = 'national' AND district_id = 0
            LIMIT 1
            """
        ),
        {"sk": sku_key},
    )
    row = res.fetchone()
    if not row:
        return None
    payload = _json_loads(row.forecast_json, {})
    metrics = _json_loads(row.metrics_json, {})
    ensemble = payload.get("ensemble") or []
    if not ensemble:
        return None
    return {
        "ensemble": ensemble[:days],
        "product": payload.get("product") or "",
        "sample_count": int(row.sample_count or metrics.get("sample_count") or 0),
        "data_latest_date": _fmt_day(row.data_latest_date),
        "trained_at": row.trained_at.isoformat() if row.trained_at else None,
        "winner_model": row.winner_model or metrics.get("winner_model") or "",
        "reliability": metrics.get("reliability") or payload.get("reliability") or "low",
        "reliability_label": metrics.get("reliability_label") or payload.get("reliability_label") or "谨慎参考",
        "model_version": row.winner_model or "zgncpjgw_automl",
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    yhat = _num(row.get("yhat", row.get("price")))
    lower = _num(row.get("yhat_lower", row.get("lower")))
    upper = _num(row.get("yhat_upper", row.get("upper")))
    return {
        "date": str(row.get("date") or ""),
        "yhat": round(yhat, 4),
        "price": round(yhat, 4),
        "yhat_lower": round(lower, 4),
        "yhat_upper": round(upper, 4),
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "confidence": round(_num(row.get("confidence")), 4),
        "trend": row.get("trend") or "flat",
    }


async def _live_anchored(db: AsyncSession, sku_key: str, days: int) -> dict[str, Any]:
    from routers.xinfadi import _anchored_forecast

    label, series = await _series_for_sku(db, sku_key)
    if len(series) < 14:
        return {
            "status": "insufficient",
            "product": label,
            "ensemble": [],
            "message": f"有效历史不足 14 天，暂无法预测（当前 {len(series)} 天）。",
            "sample_count": len(series),
        }
    fc = _anchored_forecast(series, int(days))
    if not fc or not fc.get("ensemble"):
        return {"status": "failed", "product": label, "ensemble": [], "message": "预测计算失败。"}
    return {
        "status": "ok",
        "product": label,
        "ensemble": [_normalize_row(x) for x in fc["ensemble"]],
        "anchor_price": fc.get("anchor_price"),
        "model_version": "zgncpjgw_anchored_live",
        "reliability": "mid",
        "reliability_label": "实时锚定",
        "sample_count": len(series),
    }


def forecast_rows_from_offset(
    ensemble: list[dict[str, Any]],
    days: int,
    start_day: Optional[date] = None,
) -> list[dict[str, Any]]:
    target = start_day or (_today() + timedelta(days=1))
    future = []
    for row in ensemble:
        try:
            row_day = date.fromisoformat(str(row.get("date") or "")[:10])
        except ValueError:
            continue
        if row_day >= target:
            future.append(row)
    return future[: max(1, min(30, int(days or 7)))]


async def forecast_for_query(
    db: AsyncSession,
    *,
    query_text: str,
    mode: str = "future",
    days: int = 7,
    target_offset: int = 1,
    parsed: Optional[ParsedPriceQuery] = None,
) -> dict[str, Any]:
    """与 chat _tool_xinfadi_forecast 返回结构兼容。"""
    mode = str(mode or "future").strip().lower()
    if mode not in {"tomorrow", "future"}:
        mode = "future"
    target_offset = max(1, min(30, int(target_offset or 1)))
    pq = parsed or parse_price_query(query_text)
    query = pq.product_query or pq.goods_name_hint
    days = max(1, min(30, int(days or 7)))
    need_days = max(days, target_offset + 1)

    if not query and not pq.goods_name_hint:
        return {
            "ok": False,
            "status": "need_clarify",
            "type": "forecast",
            "source": "zgncpjgw",
            "query": pq.raw_text,
            "candidates": [],
            "summary": "请告诉我更准确的品名（例如：大白菜、土豆、西红柿）。",
            "rows": [],
        }

    sku_key, labels, product_label = await resolve_sku_from_parsed(db, pq)
    if not labels:
        return {
            "ok": False,
            "status": "not_found",
            "type": "forecast",
            "source": "zgncpjgw",
            "query": query or pq.raw_text,
            "candidates": [],
            "summary": f"全国农产品价格库中未找到「{pq.goods_name_hint or query}」相关 SKU。",
            "rows": [],
        }
    if not sku_key:
        return {
            "ok": False,
            "status": "ambiguous",
            "type": "forecast",
            "source": "zgncpjgw",
            "query": query or pq.goods_name_hint,
            "candidates": labels[:8],
            "summary": f"你说的「{query or pq.goods_name_hint}」可能对应多个规格，请补充更准确品名后再查。",
            "rows": [],
        }
    snap = await _load_snapshot(db, sku_key, need_days)
    source = "zgncpjgw_snapshot"
    live_meta: dict[str, Any] = {}
    if snap and snap.get("ensemble"):
        ensemble = [_normalize_row(x) for x in snap["ensemble"]]
        model_version = snap.get("winner_model") or snap.get("model_version") or "zgncpjgw_automl"
        reliability = snap.get("reliability")
        reliability_label = snap.get("reliability_label")
        trained_at = snap.get("trained_at")
    else:
        live = await _live_anchored(db, sku_key, need_days)
        st = str(live.get("status") or "")
        if st == "insufficient":
            return {
                "ok": False,
                "status": "needs_training",
                "type": "forecast",
                "source": "zgncpjgw",
                "product": live.get("product") or product_label,
                "query": query,
                "sku_key": sku_key,
                "summary": (
                    str(live.get("message") or "")
                    + " 请在数据挖掘中心「全国农产品价格」Tab 点击「更新当前预测」后再问。"
                ),
                "rows": [],
            }
        if st != "ok":
            return {
                "ok": False,
                "status": st or "failed",
                "type": "forecast",
                "source": "zgncpjgw",
                "product": live.get("product") or product_label,
                "query": query,
                "summary": str(live.get("message") or "预测计算失败。"),
                "rows": [],
            }
        ensemble = live.get("ensemble") or []
        source = "zgncpjgw_live"
        model_version = live.get("model_version") or "zgncpjgw_anchored_live"
        reliability = live.get("reliability")
        reliability_label = live.get("reliability_label")
        trained_at = None
        live_meta = {"anchor_price": live.get("anchor_price")}

    future = forecast_rows_from_offset(ensemble, days, _today() + timedelta(days=target_offset))
    if not future:
        return {
            "ok": False,
            "status": "unavailable",
            "type": "forecast",
            "source": source,
            "product": product_label,
            "query": query,
            "sku_key": sku_key,
            "summary": f"{product_label} 的预测窗口不覆盖目标日期，请缩短查询天数或先更新预测。",
            "rows": [],
            "model_version": model_version,
        }

    product = product_label or query
    tomorrow = future[0]
    src_note = "全国农产品价格预测快照" if source == "zgncpjgw_snapshot" else "全国行情实时锚定"
    return {
        "ok": True,
        "status": "ok",
        "type": "forecast",
        "source": source,
        "title": f"{product} 未来 {len(future)} 天预测",
        "columns": [
            {"key": "date", "label": "日期"},
            {"key": "price", "label": "预测价"},
            {"key": "lower", "label": "下界"},
            {"key": "upper", "label": "上界"},
        ],
        "rows": future,
        "query": query,
        "product": product,
        "sku_key": sku_key,
        "days": days,
        "mode": mode,
        "target_offset": target_offset,
        "tomorrow": tomorrow,
        "future": future,
        "model_version": model_version,
        "model_trained_at": trained_at,
        "reliability": reliability,
        "reliability_label": reliability_label,
        "anchor_price": live_meta.get("anchor_price"),
        "summary": f"{product} 的预测已按{src_note}计算（与数据挖掘中心全国农产品价格一致，版本 {model_version or '—'}）。",
        "fallback": False,
        "algorithmic": True,
        "unified_from_xinfadi": bool("新发地" in pq.raw_text),
    }


async def history_for_query(
    db: AsyncSession,
    query_text: str,
    limit: int = 60,
    *,
    parsed: Optional[ParsedPriceQuery] = None,
    target_date: Optional[date] = None,
) -> dict[str, Any]:
    pq = parsed or parse_price_query(query_text)
    target = target_date or pq.target_date

    if not pq.product_query and not pq.goods_name_hint:
        return {
            "ok": False,
            "type": "national_price",
            "title": "全国农产品价格",
            "columns": [],
            "rows": [],
            "summary": "请提供品名。",
        }

    sku_key, labels, label = await resolve_sku_from_parsed(db, pq)
    if not labels:
        return {
            "ok": False,
            "type": "national_price",
            "title": f"{pq.goods_name_hint or '行情'}",
            "columns": [{"key": "date", "label": "日期"}, {"key": "product_name", "label": "品名"}, {"key": "avg_price", "label": "均价"}],
            "rows": [],
            "summary": f"全国农产品价格库中未找到「{pq.goods_name_hint or pq.product_query}」相关 SKU。",
            "parsed_product": pq.product_query,
        }
    if not sku_key:
        text_labels = "、".join(labels[:8])
        return {
            "ok": False,
            "type": "national_price",
            "title": f"{pq.goods_name_hint} 行情",
            "columns": [],
            "rows": [],
            "summary": f"多个可能品名：{text_labels}。请补充规格后再查。",
            "candidates": labels[:8],
        }

    _, series = await _series_for_sku(db, sku_key)
    if target:
        day_str = target.isoformat()
        row = next((r for r in series if r.get("date") == day_str), None)
        if row:
            price = round(_num(row.get("avg_price")), 3)
            return {
                "ok": True,
                "type": "national_price",
                "title": f"{label} {day_str} 价格",
                "target_date": day_str,
                "product": label,
                "sku_key": sku_key,
                "price": price,
                "columns": [{"key": "date", "label": "日期"}, {"key": "product_name", "label": "品名"}, {"key": "avg_price", "label": "均价(元/斤)"}],
                "rows": [{"date": day_str, "product_name": label, "avg_price": price}],
                "summary": f"{label} 在 {day_str} 的全国农产品均价为 {price} 元/斤。",
            }
        nearest = series[-1] if series else None
        hint = f"最近有数据日期为 {nearest['date']}（{nearest['avg_price']} 元/斤）。" if nearest else "暂无历史序列。"
        return {
            "ok": False,
            "type": "national_price",
            "title": f"{label} {day_str}",
            "target_date": day_str,
            "product": label,
            "sku_key": sku_key,
            "columns": [],
            "rows": [],
            "summary": f"{label} 在 {day_str} 暂无全国均价记录。{hint}",
        }

    rows = [
        {"date": r["date"], "product_name": label, "avg_price": round(_num(r["avg_price"]), 3)}
        for r in reversed(series[-limit:])
    ]
    return {
        "ok": True,
        "type": "national_price",
        "title": f"{label} 全国行情",
        "columns": [{"key": "date", "label": "日期"}, {"key": "product_name", "label": "品名"}, {"key": "avg_price", "label": "均价(元/斤)"}],
        "rows": rows[:20],
        "summary": f"匹配到 {len(series)} 天全国农产品价格数据。",
        "sku_key": sku_key,
        "product": label,
    }
