"""AI 行情日报：基于库内清洗聚合数据生成市场环境 / 板块异动 / 分类展望 / 分省要点。"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from statistics import mean
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import SessionLocal
from services.zg_change_analytics import compute_change_ranking


async def _with_session(fn):
    """每个并发任务用独立 AsyncSession：SQLAlchemy 的 session 不能跨 gather 并发共用。"""
    async with SessionLocal() as s:
        return await fn(s)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


async def _top_provinces_by_volume(db: AsyncSession, report_day: str, limit: int = 8) -> list[dict[str, Any]]:
    from routers.zgncpjgw import _parse_day, _tbl

    day = _parse_day(report_day)
    if day is None:
        return []
    tbl = _tbl()
    res = await db.execute(
        text(
            f"SELECT district_id, district_name, COUNT(*) AS n FROM `{tbl}` "
            f"WHERE crawl_date = :d GROUP BY district_id, district_name ORDER BY n DESC LIMIT :lim"
        ),
        {"d": day, "lim": limit},
    )
    return [
        {"district_id": int(r.district_id), "district_name": str(r.district_name or ""), "rows": int(r.n or 0)}
        for r in res.fetchall()
        if r.district_id
    ]


def _sector_signals_from_ranking(gainers: list[dict], losers: list[dict], limit: int = 8) -> list[dict[str, Any]]:
    by_cate: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"cate_name": "", "gainer_count": 0, "loser_count": 0, "gainer_pcts": [], "loser_pcts": [], "top_gainer": None}
    )
    for r in gainers:
        c = r.get("cate_name") or "未分类"
        s = by_cate[c]
        s["cate_name"] = c
        s["gainer_count"] += 1
        s["gainer_pcts"].append(_to_float(r.get("pct")))
        if s["top_gainer"] is None or _to_float(r.get("pct")) > _to_float(s["top_gainer"].get("pct")):
            s["top_gainer"] = r
    for r in losers:
        c = r.get("cate_name") or "未分类"
        s = by_cate[c]
        s["cate_name"] = c
        s["loser_count"] += 1
        s["loser_pcts"].append(_to_float(r.get("pct")))
    out: list[dict[str, Any]] = []
    for s in by_cate.values():
        if not s["gainer_count"] and not s["loser_count"]:
            continue
        score = s["gainer_count"] * 2 + s["loser_count"] + (mean(s["gainer_pcts"]) if s["gainer_pcts"] else 0) * 0.1
        tg = s["top_gainer"] or {}
        out.append(
            {
                "cate_name": s["cate_name"],
                "gainer_count": s["gainer_count"],
                "loser_count": s["loser_count"],
                "avg_gain_pct": round(mean(s["gainer_pcts"]), 1) if s["gainer_pcts"] else None,
                "top_gainer_label": tg.get("label") or tg.get("goods_name"),
                "top_gainer_pct": tg.get("pct"),
                "signal_score": round(score, 1),
            }
        )
    out.sort(key=lambda x: (-x["signal_score"], -x["gainer_count"]))
    return out[:limit]


def _category_outlook(categories: list[dict], sector_signals: list[dict], limit: int = 6) -> list[dict[str, Any]]:
    """结合指数涨跌与短期价格动能，给出分类方向研判（规则，可溯源）。"""
    sector_map = {s["cate_name"]: s for s in sector_signals}
    picks: list[dict[str, Any]] = []
    for c in categories or []:
        name = c.get("cate_name") or "—"
        chg = _to_float(c.get("change_pct"))
        sec = sector_map.get(name) or {}
        gc = int(sec.get("gainer_count") or 0)
        lc = int(sec.get("loser_count") or 0)
        if chg >= 2.5 and gc >= 2:
            direction, tag = "偏多", "看涨关注"
            reason = f"指数较基期 {chg:+.1f}%，且近3日均价对比下 {gc} 个品种上涨"
        elif chg <= -2.5 and lc >= 2:
            direction, tag = "偏空", "承压"
            reason = f"指数较基期 {chg:.1f}%，且近3日均价对比下 {lc} 个品种下跌"
        elif gc >= 3 and (sec.get("avg_gain_pct") or 0) >= 15:
            direction, tag = "短线走强", "动能"
            reason = f"板块内 {gc} 个品种领涨，代表品种 {sec.get('top_gainer_label') or '—'} {sec.get('top_gainer_pct')}%"
        elif lc >= 3:
            direction, tag = "短线走弱", "动能"
            reason = f"板块内 {lc} 个品种领跌"
        else:
            direction, tag = "中性", "观望"
            reason = f"指数 {chg:+.1f}%，板块内涨跌品种分布均衡"
        picks.append(
            {
                "cate_name": name,
                "index_latest": c.get("latest"),
                "index_change_pct": chg,
                "direction": direction,
                "tag": tag,
                "reason": reason,
            }
        )
    picks.sort(
        key=lambda x: (
            0 if x["direction"] in ("偏多", "短线走强") else (2 if x["direction"] == "中性" else 1),
            -abs(_to_float(x["index_change_pct"])),
        )
    )
    return picks[:limit]


async def collect_briefing_facts(db: AsyncSession, *, baseline_days: int = 3) -> dict[str, Any]:
    from routers.zgncpjgw import (
        analytics_index,
        analytics_overview,
        analytics_quality,
        analytics_spread,
    )

    idx = await analytics_index(_=None, db=db)
    overview = await analytics_overview(date="", district_id=None, cate_id=None, scate="", _=None, db=db)
    quality = await analytics_quality(_=None, db=db)
    report_date = idx.get("latest_date") or overview.get("snapshot_date") or quality.get("snapshot_date") or ""

    ranking, spread, provinces_raw = await asyncio.gather(
        _with_session(lambda s: compute_change_ranking(s, district_id=None, cate_id=None, scate="", baseline_days=baseline_days, limit=20)),
        _with_session(lambda s: analytics_spread(cate_id=None, scate="", date=report_date, limit=8, min_provinces=6, max_ratio=6.0, _=None, db=s)),
        _with_session(lambda s: _top_provinces_by_volume(s, report_date, limit=8)),
    )

    province_notes: list[dict[str, Any]] = []
    if provinces_raw:
        prov_rankings = await asyncio.gather(
            *[
                _with_session(
                    lambda s, p=p: compute_change_ranking(
                        s,
                        district_id=p["district_id"],
                        cate_id=None,
                        scate="",
                        baseline_days=baseline_days,
                        limit=3,
                    )
                )
                for p in provinces_raw[:6]
            ]
        )
        for p, pr in zip(provinces_raw[:6], prov_rankings):
            g = (pr.get("gainers") or [])[:2]
            l = (pr.get("losers") or [])[:2]
            province_notes.append(
                {
                    "district_id": p["district_id"],
                    "district_name": p["district_name"] or pr.get("district_name"),
                    "top_gainers": [{"label": x.get("label"), "pct": x.get("pct"), "cate_name": x.get("cate_name")} for x in g],
                    "top_losers": [{"label": x.get("label"), "pct": x.get("pct"), "cate_name": x.get("cate_name")} for x in l],
                }
            )

    gainers = ranking.get("gainers") or []
    losers = ranking.get("losers") or []
    categories = list(idx.get("categories") or [])
    sector_signals = _sector_signals_from_ranking(gainers, losers)
    outlook = _category_outlook(categories, sector_signals)

    return {
        "report_date": report_date,
        "baseline_days": baseline_days,
        "overview": overview,
        "quality": quality,
        "index": {
            "base_date": idx.get("base_date"),
            "latest_date": idx.get("latest_date"),
            "overall_latest": idx.get("overall_latest"),
            "overall_change_pct": idx.get("overall_change_pct"),
            "categories": [
                {
                    "cate_name": c.get("cate_name"),
                    "latest": c.get("latest"),
                    "change_pct": c.get("change_pct"),
                    "basket_size": c.get("basket_size"),
                }
                for c in categories
            ],
        },
        "ranking": {
            "baseline_days": baseline_days,
            "gainers": gainers[:10],
            "losers": losers[:10],
        },
        "spread": spread.get("rows") or [],
        "sector_signals": sector_signals,
        "category_outlook": outlook,
        "provinces": province_notes,
    }


def _briefing_to_plain(report: dict[str, Any]) -> str:
    lines = [report.get("headline") or "", ""]
    for sec in report.get("sections") or []:
        lines.append(sec.get("title") or "")
        if sec.get("content"):
            lines.append(sec.get("content"))
        for it in sec.get("items") or []:
            if isinstance(it, dict):
                line = it.get("line") or it.get("text") or ""
                if line:
                    lines.append(f"· {line}")
            else:
                lines.append(f"· {it}")
        lines.append("")
    outlook = report.get("outlook")
    if outlook:
        lines.append("趋势展望")
        lines.append(outlook)
    return "\n".join(lines).strip()


def _template_market_report(facts: dict[str, Any]) -> dict[str, Any]:
    rd = facts.get("report_date") or "—"
    bd = facts.get("baseline_days") or 3
    idx = facts.get("index") or {}
    ov = facts.get("overview") or {}
    q = facts.get("quality") or {}
    chg = _to_float(idx.get("overall_change_pct"))
    ov_dir = "震荡上行" if chg >= 2 else ("承压下行" if chg <= -2 else "窄幅震荡")

    sectors = facts.get("sector_signals") or []
    sector_lines = [
        f"{s['cate_name']}：领涨 {s.get('top_gainer_label') or '—'} {s.get('top_gainer_pct')}%"
        f"（上涨品种 {s['gainer_count']} 个）"
        for s in sectors[:5]
    ] or ["暂无显著板块集中异动"]

    outlook_items = facts.get("category_outlook") or []
    outlook_lines = [
        f"{o['cate_name']}【{o['direction']}】{o['reason']}"
        for o in outlook_items[:5]
    ] or ["各分类涨跌分化，建议结合指数结构观察"]

    prov_lines = []
    for p in facts.get("provinces") or []:
        g = p.get("top_gainers") or []
        hint = "、".join(f"{x.get('label')} +{x.get('pct')}%" for x in g[:2]) if g else "波动平缓"
        prov_lines.append(f"{p.get('district_name')}：{hint}")

    ranking = facts.get("ranking") or {}
    g_top = ranking.get("gainers") or []
    l_top = ranking.get("losers") or []

    sections = [
        {
            "title": "市场环境",
            "content": (
                f"报告日 {rd}，全国农产品价格总指数 {idx.get('overall_latest')}（较基期 {chg:+.2f}%），"
                f"整体呈现{ov_dir}。库内覆盖 {ov.get('distinct_districts')} 省、{ov.get('distinct_skus')} 个 SKU，"
                f"数据健康度 {q.get('health_score')} 分。涨跌对比口径：统计日价相对前 {bd} 日均价。"
            ),
        },
        {
            "title": "板块异动",
            "items": [{"line": ln} for ln in sector_lines],
        },
        {
            "title": "分类展望",
            "items": [{"line": ln} for ln in outlook_lines],
        },
        {
            "title": "分省要点",
            "items": [{"line": ln} for ln in prov_lines] or [{"line": "样本省份暂无显著涨跌集中"}],
        },
        {
            "title": "品种雷达",
            "items": [
                {
                    "line": "涨幅："
                    + ("、".join(f"{x.get('label')} +{x.get('pct')}%" for x in g_top[:5]) or "—")
                },
                {
                    "line": "跌幅："
                    + ("、".join(f"{x.get('label')} {x.get('pct')}%" for x in l_top[:5]) or "—")
                },
            ],
        },
    ]

    sp = facts.get("spread") or []
    if sp:
        sections.append(
            {
                "title": "区域价差",
                "items": [
                    {
                        "line": f"{r.get('goods_name')} 价差 {r.get('spread_pct')}%（{r.get('cheapest')}→{r.get('priciest')}）"
                    }
                    for r in sp[:4]
                ],
            }
        )

    headline = (
        f"{rd} 全国农产品市场环境{ov_dir}；指数 {idx.get('overall_latest')}（{chg:+.2f}%）；"
        f"重点关注 {len([o for o in outlook_items if o.get('direction') in ('偏多', '短线走强')])} 个偏强分类"
    )

    bullish = "、".join(o["cate_name"] for o in outlook_items if o.get("direction") in ("偏多", "短线走强")) or "暂无明显集中看涨板块"

    return {
        "headline": headline,
        "outlook": f"短期建议优先跟踪：{bullish}；对涨幅异常且跨省价差偏大的品种做采购复核。",
        "sections": sections,
        "source": "template",
    }


def _slim_facts_for_llm(facts: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_date": facts.get("report_date"),
        "baseline_days": facts.get("baseline_days"),
        "index": facts.get("index"),
        "overview": {
            k: (facts.get("overview") or {}).get(k)
            for k in ("snapshot_date", "distinct_skus", "distinct_districts", "total_rows")
        },
        "quality": facts.get("quality"),
        "sector_signals": (facts.get("sector_signals") or [])[:8],
        "category_outlook": (facts.get("category_outlook") or [])[:8],
        "ranking": {
            "gainers": (facts.get("ranking") or {}).get("gainers", [])[:8],
            "losers": (facts.get("ranking") or {}).get("losers", [])[:8],
        },
        "provinces": facts.get("provinces"),
        "spread": facts.get("spread")[:5],
    }


async def _llm_market_report(facts: dict[str, Any]) -> Optional[dict[str, Any]]:
    from services.zgncpjgw_daily_report import _dashscope_json_chat, _parse_llm_json

    sys_prompt = (
        "你是大综食材供应链首席行情策略师。根据 JSON 事实数据撰写「市场环境日报」，风格类似股票研报推荐："
        "市场环境、板块异动、哪些分类可能涨/跌、重点省份、品种雷达、区域价差。"
        "硬性规则：所有数字、省名、分类名、品种名必须来自 facts，禁止编造。"
        '输出 JSON：{"headline":"一句总览","outlook":"趋势展望一两句","sections":[{'
        '"title":"市场环境|板块异动|分类展望|分省要点|品种雷达|区域价差",'
        '"content":"段落（仅市场环境用）","items":[{"line":"要点一条"}]}]}。'
        "sections 至少含：市场环境、板块异动、分类展望、分省要点；items 每条一行，简洁有力。"
    )
    draft = _template_market_report(facts)
    user = json.dumps({"facts": _slim_facts_for_llm(facts), "template_draft": draft}, ensure_ascii=False)
    try:
        resp = await asyncio.wait_for(
            _dashscope_json_chat(
                [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
                max_tokens=2048,
            ),
            timeout=55.0,
        )
        content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        parsed = _parse_llm_json(content) or {}
        sections = parsed.get("sections")
        if not isinstance(sections, list) or len(sections) < 3:
            return None
        cleaned = []
        for sec in sections[:8]:
            if not isinstance(sec, dict):
                continue
            title = str(sec.get("title") or "")[:32]
            if not title:
                continue
            items = sec.get("items")
            if isinstance(items, list):
                norm_items = []
                for it in items[:12]:
                    if isinstance(it, dict) and it.get("line"):
                        norm_items.append({"line": str(it.get("line"))[:200]})
                    elif isinstance(it, str):
                        norm_items.append({"line": it[:200]})
                cleaned.append({"title": title, "content": str(sec.get("content") or "")[:800], "items": norm_items})
            else:
                cleaned.append({"title": title, "content": str(sec.get("content") or sec.get("paragraph") or "")[:1200], "items": []})
        if len(cleaned) < 3:
            return None
        return {
            "headline": str(parsed.get("headline") or draft.get("headline"))[:300],
            "outlook": str(parsed.get("outlook") or draft.get("outlook"))[:500],
            "sections": cleaned,
            "source": "llm",
        }
    except Exception:
        return None


async def build_market_insight_report(db: AsyncSession, *, baseline_days: int = 3) -> dict[str, Any]:
    facts = await collect_briefing_facts(db, baseline_days=baseline_days)
    template = _template_market_report(facts)
    report = template
    if (settings.ai_api_key or "").strip():
        llm_report = await _llm_market_report(facts)
        if llm_report:
            report = llm_report
    briefing_text = _briefing_to_plain(report)
    return {
        "briefing": briefing_text,
        "report": report,
        "facts": facts,
        "source": report.get("source", "template"),
        "generated_at": facts.get("report_date"),
    }
