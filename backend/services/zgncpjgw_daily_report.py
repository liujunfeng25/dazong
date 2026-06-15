"""全国农产品价格 LLM PDF 日报：事实数据来自库内聚合，LLM 仅负责叙述与排版。"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.zgncpjgw_credentials import _PLAYWRIGHT_LOCK


@dataclass
class ReportFilter:
    report_date: Optional[str] = None
    district_id: Optional[int] = None
    cate_id: Optional[int] = None
    scate: str = ""
    appendix_sku_key: str = ""
    appendix_start_date: str = ""
    appendix_end_date: str = ""


def _now_cn_iso() -> str:
    from zoneinfo import ZoneInfo
    from datetime import datetime

    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat()


def _escape_html(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _summarize_index(idx: dict[str, Any], tail: int = 14) -> dict[str, Any]:
    dates = list(idx.get("dates") or [])
    overall = list(idx.get("overall") or [])
    if tail and len(dates) > tail:
        dates = dates[-tail:]
        overall = overall[-tail:]
    cats = []
    for c in (idx.get("categories") or [])[:8]:
        s = list(c.get("series") or [])
        if tail and len(s) > tail:
            s = s[-tail:]
        cats.append(
            {
                "cate_name": c.get("cate_name"),
                "latest": c.get("latest"),
                "change_pct": c.get("change_pct"),
                "basket_size": c.get("basket_size"),
                "series_tail": s,
            }
        )
    return {
        "base_date": idx.get("base_date"),
        "latest_date": idx.get("latest_date"),
        "overall_latest": idx.get("overall_latest"),
        "overall_change_pct": idx.get("overall_change_pct"),
        "basket_meta": idx.get("basket_meta"),
        "dates_tail": dates,
        "overall_tail": overall,
        "categories": cats,
    }


async def collect_facts(db: AsyncSession, flt: ReportFilter) -> dict[str, Any]:
    """聚合真实库内数据，供 LLM 只读引用（禁止编造数字）。"""
    from routers.zgncpjgw import (
        _parse_day,
        _tbl,
        analytics_compare,
        analytics_index,
        analytics_movers,
        analytics_overview,
        analytics_quality,
        analytics_spread,
        analytics_timeseries,
    )
    from sqlalchemy import text

    tbl = _tbl()
    report_day: Optional[date] = _parse_day(flt.report_date)
    if report_day is None:
        mx_res = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{tbl}`"))
        mx_row = mx_res.fetchone()
        report_day = _parse_day(mx_row.mx) if mx_row and mx_row.mx else None

    overview = await analytics_overview(
        date=report_day.isoformat() if report_day else "",
        district_id=None,
        cate_id=None,
        scate="",
        _=None,
        db=db,
    )
    quality = await analytics_quality(_=None, db=db)
    idx = await analytics_index(_=None, db=db)
    movers = await analytics_movers(
        window=7,
        limit=8,
        min_provinces=6,
        max_pct=150.0,
        cate_id=None,
        scate="",
        district_id=None,
        _=None,
        db=db,
    )
    spread = await analytics_spread(
        cate_id=None, scate="", date=report_day.isoformat() if report_day else "", limit=8,
        min_provinces=6, max_ratio=6.0, _=None, db=db,
    )

    appendix: Optional[dict[str, Any]] = None
    sku_key = (flt.appendix_sku_key or "").strip()
    if sku_key or flt.district_id is not None or flt.cate_id is not None or flt.scate.strip():
        appendix = {
            "filters": {
                "district_id": flt.district_id,
                "cate_id": flt.cate_id,
                "scate": flt.scate.strip(),
                "date_range": [flt.appendix_start_date, flt.appendix_end_date],
                "sku_key": sku_key,
            },
        }
        appendix["overview_filtered"] = await analytics_overview(
            date=report_day.isoformat() if report_day else "",
            district_id=flt.district_id,
            cate_id=flt.cate_id,
            scate=flt.scate.strip(),
            _=None,
            db=db,
        )
        if sku_key:
            appendix["compare"] = await analytics_compare(
                sku_key=sku_key, date=report_day.isoformat() if report_day else "", _=None, db=db
            )
            start = flt.appendix_start_date or (
                (report_day - timedelta(days=6)).isoformat() if report_day else ""
            )
            end = flt.appendix_end_date or (report_day.isoformat() if report_day else "")
            appendix["timeseries"] = await analytics_timeseries(
                sku_keys=sku_key,
                district_id=flt.district_id,
                start_date=start,
                end_date=end,
                days=30,
                _=None,
                db=db,
            )

    return {
        "report_date": overview.get("snapshot_date") or quality.get("snapshot_date") or idx.get("latest_date"),
        "generated_at_cn": _now_cn_iso(),
        "overview": overview,
        "quality": quality,
        "index": _summarize_index(idx),
        "movers": movers,
        "spread": {
            "latest_date": spread.get("latest_date"),
            "rows": spread.get("rows") or [],
        },
        "appendix": appendix,
    }


def _facts_for_llm(facts: dict[str, Any]) -> dict[str, Any]:
    """供 LLM 阅读的精简事实包（关键数字与 collect_facts 一致，去掉冗长序列）。"""
    ov = facts.get("overview") or {}
    q = facts.get("quality") or {}
    idx = facts.get("index") or {}
    mv = facts.get("movers") or {}
    sp = facts.get("spread") or {}

    def _mv(items: list) -> list[dict[str, Any]]:
        return [
            {"label": x.get("label"), "cate_name": x.get("cate_name"), "pct": x.get("pct")}
            for x in (items or [])[:6]
        ]

    slim: dict[str, Any] = {
        "report_date": facts.get("report_date"),
        "overview": {
            "snapshot_date": ov.get("snapshot_date"),
            "total_rows": ov.get("total_rows"),
            "distinct_skus": ov.get("distinct_skus"),
            "distinct_districts": ov.get("distinct_districts"),
        },
        "quality": {
            k: q.get(k)
            for k in (
                "health_score",
                "parse_rate",
                "suspicious_skus",
                "basket_coverage",
                "freshness_gap_days",
                "snapshot_date",
            )
        },
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
                for c in (idx.get("categories") or [])[:8]
            ],
        },
        "movers": {
            "window": mv.get("window"),
            "gainers": _mv(mv.get("gainers")),
            "losers": _mv(mv.get("losers")),
        },
        "spread": {
            "latest_date": sp.get("latest_date"),
            "rows": [
                {
                    "goods_name": r.get("goods_name"),
                    "spread_pct": r.get("spread_pct"),
                    "cheapest": r.get("cheapest"),
                    "priciest": r.get("priciest"),
                }
                for r in (sp.get("rows") or [])[:8]
            ],
        },
    }
    appendix = facts.get("appendix")
    if not appendix:
        return slim
    aov = appendix.get("overview_filtered") or {}
    cmp_ = appendix.get("compare") or {}
    ap: dict[str, Any] = {
        "filters": appendix.get("filters"),
        "overview_filtered": {
            "total_rows": aov.get("total_rows"),
            "distinct_skus": aov.get("distinct_skus"),
            "distinct_districts": aov.get("distinct_districts"),
        },
        "compare": {
            "label": cmp_.get("label"),
            "labels": (cmp_.get("labels") or [])[:12],
            "values": (cmp_.get("values") or [])[:12],
        },
    }
    ts = appendix.get("timeseries") or {}
    dates = list(ts.get("dates") or [])
    values = list(ts.get("values") or [])
    if dates and values:
        tail = min(7, len(dates))
        ap["timeseries_tail"] = {
            "label": ts.get("label"),
            "dates": dates[-tail:],
            "values": values[-tail:],
        }
    slim["appendix"] = ap
    return slim


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _svg_line_chart(
    dates: list[Any],
    values: list[Any],
    *,
    title: str = "",
    width: int = 500,
    height: int = 190,
) -> str:
    n = min(len(dates or []), len(values or []))
    if n < 2:
        return '<div class="chart-empty">趋势数据不足</div>'
    ds = [str(d)[5:] if d else "" for d in dates[-n:]]
    vs = [_to_float(v) for v in values[-n:]]
    pad_l, pad_r, pad_t, pad_b = 44, 12, 24, 32
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    vmin, vmax = min(vs), max(vs)
    span = vmax - vmin or 1.0
    pts: list[str] = []
    circles: list[str] = []
    for i, v in enumerate(vs):
        x = pad_l + (i / max(n - 1, 1)) * iw
        y = pad_t + ih - ((v - vmin) / span) * ih
        pts.append(f"{x:.1f},{y:.1f}")
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#00e5ff"/>')
    area = f"{pad_l},{pad_t + ih} " + " ".join(pts) + f" {pad_l + iw},{pad_t + ih}"
    y_mid = pad_t + ih / 2
    return f"""
    <svg viewBox="0 0 {width} {height}" class="chart-svg" xmlns="http://www.w3.org/2000/svg">
      <text x="{pad_l}" y="16" class="chart-title">{_escape_html(title)}</text>
      <line x1="{pad_l}" y1="{pad_t + ih}" x2="{pad_l + iw}" y2="{pad_t + ih}" stroke="#94a3b8" stroke-width="1"/>
      <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + ih}" stroke="#94a3b8" stroke-width="1"/>
      <text x="6" y="{pad_t + 8}" font-size="9" fill="#64748b">{vmax:.1f}</text>
      <text x="6" y="{pad_t + ih}" font-size="9" fill="#64748b">{vmin:.1f}</text>
      <polygon points="{area}" fill="url(#gradArea)" opacity="0.35"/>
      <polyline points="{' '.join(pts)}" fill="none" stroke="#00b4d8" stroke-width="2.5"/>
      {''.join(circles)}
      <text x="{pad_l}" y="{height - 8}" font-size="8" fill="#64748b">{_escape_html(ds[0])}</text>
      <text x="{pad_l + iw - 36}" y="{height - 8}" font-size="8" fill="#64748b">{_escape_html(ds[-1])}</text>
      <defs><linearGradient id="gradArea" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#00e5ff"/><stop offset="100%" stop-color="#0a1628" stop-opacity="0"/>
      </linearGradient></defs>
    </svg>"""


def _svg_hbar_chart(
    items: list[tuple[str, float, str]],
    *,
    title: str = "",
    width: int = 500,
    height: int = 200,
) -> str:
    if not items:
        return '<div class="chart-empty">暂无数据</div>'
    row_h = 22
    pad_l, pad_r, pad_t = 120, 48, 26
    ih = len(items) * row_h
    height = max(height, ih + pad_t + 12)
    max_abs = max(abs(v) for _, v, _ in items) or 1.0
    bars: list[str] = []
    for i, (label, val, color) in enumerate(items):
        y = pad_t + i * row_h + 4
        bar_w = abs(val) / max_abs * (width - pad_l - pad_r)
        x0 = pad_l if val >= 0 else pad_l - bar_w
        bars.append(
            f'<text x="4" y="{y + 14}" font-size="9" fill="#334155">{_escape_html(str(label)[:14])}</text>'
            f'<rect x="{x0:.1f}" y="{y}" width="{bar_w:.1f}" height="14" rx="3" fill="{color}"/>'
            f'<text x="{pad_l + (width - pad_l - pad_r) + 6:.1f}" y="{y + 12}" font-size="9" fill="#475569">{val:+.1f}%</text>'
        )
    return f"""
    <svg viewBox="0 0 {width} {height}" class="chart-svg" xmlns="http://www.w3.org/2000/svg">
      <text x="8" y="16" class="chart-title">{_escape_html(title)}</text>
      {''.join(bars)}
    </svg>"""


def _svg_category_bars(categories: list[dict[str, Any]], *, title: str = "") -> str:
    items = [
        (str(c.get("cate_name") or "—")[:8], _to_float(c.get("change_pct")), "#3b82f6")
        for c in (categories or [])[:8]
    ]
    return _svg_hbar_chart(items, title=title or "分类指数较基期涨跌 %")


def _svg_gauge(value: float, *, max_val: float = 100.0, label: str = "") -> str:
    pct = min(max(value / max_val, 0), 1) if max_val else 0
    angle = 180 * pct
    color = "#22c55e" if value >= 85 else ("#f59e0b" if value >= 70 else "#ef4444")
    return f"""
    <svg viewBox="0 0 120 80" class="gauge-svg" xmlns="http://www.w3.org/2000/svg">
      <path d="M 15 65 A 45 45 0 0 1 105 65" fill="none" stroke="#e2e8f0" stroke-width="10" stroke-linecap="round"/>
      <path d="M 15 65 A 45 45 0 0 1 105 65" fill="none" stroke="{color}" stroke-width="10"
            stroke-linecap="round" stroke-dasharray="{141.4 * pct:.1f} 141.4"/>
      <text x="60" y="58" text-anchor="middle" font-size="16" font-weight="700" fill="#0f172a">{value:.1f}</text>
      <text x="60" y="72" text-anchor="middle" font-size="8" fill="#64748b">{_escape_html(label)}</text>
    </svg>"""


def _svg_province_bars(labels: list[Any], values: list[Any], *, title: str = "") -> str:
    items = [
        (str(l)[:6], _to_float(v), "#06b6d4")
        for l, v in zip(labels or [], values or [])
        if l is not None and v is not None
    ][:12]
    if not items:
        return '<div class="chart-empty">暂无跨省对比</div>'
    max_v = max(_to_float(v) for _, v, _ in items) or 1
    width, row_h, pad_l, pad_t = 500, 20, 72, 24
    height = len(items) * row_h + pad_t + 8
    bars: list[str] = []
    for i, (lab, val, color) in enumerate(items):
        y = pad_t + i * row_h
        w = val / max_v * (width - pad_l - 60)
        bars.append(
            f'<text x="4" y="{y + 14}" font-size="9">{_escape_html(lab)}</text>'
            f'<rect x="{pad_l}" y="{y + 2}" width="{w:.1f}" height="12" rx="2" fill="{color}"/>'
            f'<text x="{pad_l + w + 4:.1f}" y="{y + 12}" font-size="8">{val:.2f}</text>'
        )
    return f"""
    <svg viewBox="0 0 {width} {height}" class="chart-svg">
      <text x="8" y="14" class="chart-title">{_escape_html(title)}</text>
      {''.join(bars)}
    </svg>"""


def _decision_board_from_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """基于系统数据生成决策看板（规则引擎，数字可溯源）。"""
    idx = facts.get("index") or {}
    mv = facts.get("movers") or {}
    sp = facts.get("spread") or {}
    q = facts.get("quality") or {}
    ov = facts.get("overview") or {}
    gainers = mv.get("gainers") or []
    losers = mv.get("losers") or []
    sp_rows = sp.get("rows") or []
    chg = _to_float(idx.get("overall_change_pct"))
    items: list[dict[str, str]] = []

    if gainers:
        g = gainers[0]
        items.append(
            {
                "level": "高",
                "tag": "价格异动",
                "title": f"重点关注：{g.get('label') or g.get('goods_name')}",
                "analysis": f"近 {mv.get('window', 7)} 日涨幅 {g.get('pct')}%，分类 {g.get('cate_name') or '—'}。",
                "action": "建议纳入采购议价与食堂成本预警清单，核对是否区域性缺货或集中入库。",
            }
        )
    if sp_rows:
        r = sp_rows[0]
        items.append(
            {
                "level": "高",
                "tag": "跨省价差",
                "title": f"区域套利风险：{r.get('goods_name')}",
                "analysis": f"价差 {r.get('spread_pct')}%（{r.get('cheapest')} → {r.get('priciest')}）。",
                "action": "建议跨省集采统筹，优先向低价省份调配或启动替代 SKU 方案。",
            }
        )
    if chg <= -3:
        items.append(
            {
                "level": "中",
                "tag": "指数走势",
                "title": "全国总指数偏弱",
                "analysis": f"总指数 {idx.get('overall_latest')}，较基期 {chg}%。",
                "action": "建议结合分类指数，对肉类/粮油等权重品类做结构性强弱分析。",
            }
        )
    elif chg >= 3:
        items.append(
            {
                "level": "中",
                "tag": "指数走势",
                "title": "全国总指数偏强",
                "analysis": f"总指数 {idx.get('overall_latest')}，较基期 +{chg}%。",
                "action": "建议提前锁定合约价，关注禽蛋、叶菜等弹性品类成本传导。",
            }
        )
    gap = q.get("freshness_gap_days")
    if gap is not None and int(gap) > 1:
        items.append(
            {
                "level": "中",
                "tag": "数据质量",
                "title": "采集新鲜度滞后",
                "analysis": f"库内最新日与报告日相差 {gap} 天；健康度 {q.get('health_score')}。",
                "action": "建议触发补抓任务，避免监管研判基于过期快照。",
            }
        )
    if losers:
        l = losers[0]
        items.append(
            {
                "level": "低",
                "tag": "降价机会",
                "title": f"议价窗口：{l.get('label') or l.get('goods_name')}",
                "analysis": f"近 {mv.get('window', 7)} 日跌幅 {l.get('pct')}%。",
                "action": "可在覆盖省份≥6 的前提下加大采购量，并对比跨省中位价选源。",
            }
        )
    headline = (
        f"报告日覆盖 {ov.get('distinct_districts')} 省 · {ov.get('distinct_skus')} SKU；"
        f"指数 {idx.get('overall_latest')}（{chg:+.2f}%）；"
        f"识别 {len(items)} 条可执行研判"
    )
    return {
        "headline": headline,
        "items": items[:6],
        "metrics": {
            "overall_index": idx.get("overall_latest"),
            "overall_change_pct": chg,
            "health_score": q.get("health_score"),
            "alert_count": len([x for x in items if x.get("level") == "高"]),
        },
        "source": "rules",
    }


async def _llm_decision_board(facts: dict[str, Any], llm_facts: dict[str, Any]) -> Optional[dict[str, Any]]:
    """LLM 生成决策分析卡片（JSON），数字须来自 facts。"""
    sys_prompt = (
        "你是供应链智能决策引擎。根据 facts 输出监管/采购决策看板。"
        "规则：数字、品种、省份只能来自 facts；禁止编造。"
        '输出 JSON：{"headline":"一句总览","items":[{"level":"高|中|低","tag":"标签","title":"标题",'
        '"analysis":"依据（含数字）","action":"可执行建议"}],"outlook":"一两句趋势展望"}。'
        "items 3-5 条，覆盖异动、价差、指数、数据质量中的真实信号。"
    )
    user = json.dumps({"facts": llm_facts, "rules_draft": _decision_board_from_facts(facts)}, ensure_ascii=False)
    try:
        resp = await asyncio.wait_for(
            _dashscope_json_chat(
                [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
                max_tokens=1536,
            ),
            timeout=50.0,
        )
        content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        parsed = _parse_llm_json(content) or {}
        items = parsed.get("items")
        if not isinstance(items, list) or len(items) < 2:
            return None
        cleaned: list[dict[str, str]] = []
        for it in items[:6]:
            if not isinstance(it, dict):
                continue
            lv = str(it.get("level") or "中")
            if lv not in ("高", "中", "低"):
                lv = "高" if "高" in lv else ("低" if "低" in lv else "中")
            cleaned.append(
                {
                    "level": lv,
                    "tag": str(it.get("tag") or "研判")[:12],
                    "title": str(it.get("title") or "")[:80],
                    "analysis": str(it.get("analysis") or "")[:400],
                    "action": str(it.get("action") or "")[:400],
                }
            )
        if len(cleaned) < 2:
            return None
        return {
            "headline": str(parsed.get("headline") or "")[:300],
            "outlook": str(parsed.get("outlook") or "")[:400],
            "items": cleaned,
            "metrics": _decision_board_from_facts(facts).get("metrics"),
            "source": "llm",
        }
    except Exception:
        return None


async def generate_decision_board(facts: dict[str, Any]) -> dict[str, Any]:
    base = _decision_board_from_facts(facts)
    if not (settings.ai_api_key or "").strip():
        return base
    llm_board = await _llm_decision_board(facts, _facts_for_llm(facts))
    if llm_board:
        if not llm_board.get("headline"):
            llm_board["headline"] = base.get("headline")
        llm_board.setdefault("metrics", base.get("metrics"))
        return llm_board
    return base


def _template_narrative(facts: dict[str, Any]) -> dict[str, Any]:
    ov = facts.get("overview") or {}
    q = facts.get("quality") or {}
    idx = facts.get("index") or {}
    mv = facts.get("movers") or {}
    sp = facts.get("spread") or {}
    rd = facts.get("report_date") or "—"
    gainers = mv.get("gainers") or []
    losers = mv.get("losers") or []
    sp_rows = sp.get("rows") or []

    def _mv_lines(items: list, n: int = 5) -> str:
        return "、".join(f"{x.get('label') or x.get('goods_name')} {x.get('pct')}%" for x in items[:n]) or "暂无显著异动"

    sections = [
        {
            "heading": "一、执行摘要",
            "paragraphs": [
                f"报告日 {rd}，全国农产品价格总指数 {idx.get('overall_latest')}（较基期 {idx.get('overall_change_pct')}%）。"
                f"当日入库 {ov.get('total_rows')} 条、SKU {ov.get('distinct_skus')} 个，覆盖 {ov.get('distinct_districts')} 省。"
                f"数据健康度 {q.get('health_score')} 分，可解析率 {q.get('parse_rate')}%。",
            ],
        },
        {
            "heading": "二、全国指数与分类结构",
            "paragraphs": [
                f"基期 {idx.get('base_date')} = 100。最强分类："
                + (idx.get("categories") or [{}])[0].get("cate_name", "—")
                + f"；关注偏弱分类："
                + ((idx.get("categories") or [{}])[-1].get("cate_name", "—") if idx.get("categories") else "—")
                + "。",
            ],
        },
        {
            "heading": "三、本周价格异动",
            "paragraphs": [
                f"近 {mv.get('window', 7)} 日涨幅靠前：{_mv_lines(gainers)}。",
                f"跌幅靠前：{_mv_lines(losers)}。",
            ],
        },
        {
            "heading": "四、跨省价差与区域风险",
            "paragraphs": [
                "价差最大品种："
                + (
                    "；".join(
                        f"{r.get('goods_name')} {r.get('spread_pct')}%（{r.get('cheapest')}→{r.get('priciest')}）"
                        for r in sp_rows[:5]
                    )
                    or "暂无"
                )
                + "。",
            ],
        },
        {
            "heading": "五、数据质量与采集说明",
            "paragraphs": [
                f"疑似脏数据 SKU {q.get('suspicious_skus')} 个；指数篮子覆盖 {q.get('basket_coverage')}%。"
                f"新鲜度滞后 {q.get('freshness_gap_days')} 天。",
            ],
        },
        {
            "heading": "六、监管建议",
            "paragraphs": [
                "建议对涨幅异常且跨省价差偏大的 SKU 做重点复核与采购议价。",
                "建议持续监控数据新鲜度，滞后超过 2 天应触发补抓。",
            ],
        },
        {
            "heading": "七、智能决策分析",
            "paragraphs": [
                "系统已融合全国指数、7 日异动、跨省价差与数据健康度，由规则引擎与大模型协同输出分级研判（高/中/低）及可执行动作，详见下文决策看板。",
            ],
        },
    ]
    appendix = facts.get("appendix")
    if appendix:
        aov = appendix.get("overview_filtered") or {}
        sections.append(
            {
                "heading": "附录：当前筛选口径",
                "paragraphs": [
                    f"筛选条件下当日记录 {aov.get('total_rows')} 条、SKU {aov.get('distinct_skus')} 个。",
                    (
                        f"主选 SKU 各省中位价：{(appendix.get('compare') or {}).get('label', '—')}；"
                        f"覆盖 {len((appendix.get('compare') or {}).get('labels') or [])} 省。"
                        if appendix.get("compare")
                        else "未指定主选 SKU。"
                    ),
                ],
            }
        )
    return {
        "title": f"全国农产品价格日报 · {rd}",
        "sections": sections,
        "source": "template",
    }


def _normalize_narrative(data: dict[str, Any]) -> dict[str, Any]:
    """将 LLM 输出规整为 {title, sections:[{heading, paragraphs:[str]}]}。"""
    sections: list[dict[str, Any]] = []
    for sec in data.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        paras = sec.get("paragraphs")
        if isinstance(paras, str):
            paras = [paras]
        elif not isinstance(paras, list):
            paras = []
        paras = [str(p).strip() for p in paras if p is not None and str(p).strip()]
        heading = str(sec.get("heading") or "").strip()
        if heading and paras:
            sections.append({"heading": heading, "paragraphs": paras})
    return {
        "title": str(data.get("title") or "").strip(),
        "sections": sections,
    }


def _validate_narrative(data: dict[str, Any]) -> bool:
    sections = data.get("sections") or []
    if not isinstance(sections, list) or len(sections) < 4:
        return False
    for sec in sections:
        if not isinstance(sec, dict):
            return False
        if not str(sec.get("heading") or "").strip():
            return False
        paras = sec.get("paragraphs")
        if isinstance(paras, str):
            paras = [paras]
        if not isinstance(paras, list) or not any(isinstance(p, str) and p.strip() for p in paras):
            return False
    return True


def _repair_llm_json_text(text: str) -> str:
    """修复 DashScope 偶发把 paragraphs 写成裸字符串而非数组的 JSON。"""
    def _repl(m: re.Match[str]) -> str:
        body = m.group(1)
        return f'"paragraphs": [{json.dumps(body, ensure_ascii=False)}]'

    return re.sub(
        r'"paragraphs"\s*:\s*\n?\s*"((?:[^"\\]|\\.)*)"',
        _repl,
        text,
        flags=re.DOTALL,
    )


def _parse_llm_json(content: str) -> Optional[dict[str, Any]]:
    text = (content or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()

    def _loads(candidate: str) -> Optional[dict[str, Any]]:
        for raw in (candidate, _repair_llm_json_text(candidate)):
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                continue
        return None

    parsed = _loads(text)
    if parsed:
        return parsed
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return _loads(text[start : end + 1])
    return None


async def _dashscope_json_chat(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """DashScope JSON 模式，提升日报章节结构解析成功率。"""
    import httpx

    api_key = (settings.ai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("AI_API_KEY 未配置")
    payload: dict[str, Any] = {
        "model": settings.ai_model_answer or "qwen-plus",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{(settings.ai_base_url or '').rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=5.0), trust_env=False) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


async def _polish_section_with_llm(
    heading: str,
    draft_paragraphs: list[str],
    llm_facts: dict[str, Any],
) -> list[str]:
    """单章润色：draft 含系统真实数字，LLM 仅优化表述。"""
    sys_prompt = (
        "你是农产品价格日报撰稿人。根据 draft（系统真实数字草稿）与 facts 润色本章。"
        "规则：数字、品种名、省份只能来自 draft 或 facts，禁止编造。"
        '只输出 JSON：{"paragraphs":["段落1","段落2"]}，paragraphs 为 1-2 条中文字符串。'
    )
    user_payload = {
        "heading": heading,
        "draft": draft_paragraphs,
        "facts": llm_facts,
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))
    resp = await asyncio.wait_for(
        _dashscope_json_chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
            max_tokens=1024,
        ),
        timeout=45.0,
    )
    content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    parsed = _parse_llm_json(content) or {}
    paras = parsed.get("paragraphs")
    if isinstance(paras, str):
        paras = [paras]
    if isinstance(paras, list):
        cleaned = [str(p).strip() for p in paras if p is not None and str(p).strip()]
        if cleaned:
            return cleaned
    return list(draft_paragraphs)


async def generate_narrative(facts: dict[str, Any]) -> dict[str, Any]:
    """基于库内 facts 生成模板草稿，再并行 LLM 润色各章；无 key 或全失败时回退模板。"""
    template = _template_narrative(facts)
    api_key = (settings.ai_api_key or "").strip()
    if not api_key:
        template["source"] = "template_no_api_key"
        return template

    llm_facts = _facts_for_llm(facts)
    tasks = [
        _polish_section_with_llm(sec["heading"], list(sec.get("paragraphs") or []), llm_facts)
        for sec in template.get("sections") or []
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    sections: list[dict[str, Any]] = []
    polished = 0
    for sec, res in zip(template.get("sections") or [], results):
        heading = sec.get("heading") or ""
        if isinstance(res, list) and res:
            sections.append({"heading": heading, "paragraphs": res})
            polished += 1
        else:
            sections.append({"heading": heading, "paragraphs": list(sec.get("paragraphs") or [])})

    out = {
        "title": template.get("title") or f"全国农产品价格日报 · {facts.get('report_date') or ''}",
        "sections": sections,
    }
    need = max(4, len(sections) // 2)
    if polished >= need:
        out["source"] = "llm"
    elif polished:
        out["source"] = "llm_partial"
    else:
        out["source"] = "template_llm_fallback"
    return out


def _render_decision_board_html(board: dict[str, Any]) -> str:
    level_cls = {"高": "risk-high", "中": "risk-mid", "低": "risk-low"}
    items_html: list[str] = []
    for it in board.get("items") or []:
        lv = str(it.get("level") or "中")
        if lv not in level_cls:
            lv = "中" if "中" in lv else ("高" if "高" in lv else "低")
        cls = level_cls.get(lv, "risk-mid")
        items_html.append(
            f"""<article class="decision-card {cls}">
              <div class="dc-head"><span class="dc-level">{_escape_html(lv)}</span>
                <span class="dc-tag">{_escape_html(it.get('tag') or '')}</span></div>
              <h4>{_escape_html(it.get('title') or '')}</h4>
              <p class="dc-analysis"><strong>研判</strong> {_escape_html(it.get('analysis') or '')}</p>
              <p class="dc-action"><strong>建议</strong> {_escape_html(it.get('action') or '')}</p>
            </article>"""
        )
    metrics = board.get("metrics") or {}
    outlook = board.get("outlook") or ""
    outlook_html = f'<p class="decision-outlook">{_escape_html(outlook)}</p>' if outlook else ""
    return f"""
    <section class="decision-board page-break-avoid">
      <div class="section-head"><span class="ai-badge">AI 决策引擎</span><h2>智能决策分析看板</h2></div>
      <p class="decision-headline">{_escape_html(board.get('headline') or '')}</p>
      <div class="decision-metrics">
        <span>总指数 <b>{_escape_html(metrics.get('overall_index'))}</b></span>
        <span>较基期 <b>{_to_float(metrics.get('overall_change_pct')):+.2f}%</b></span>
        <span>健康度 <b>{_escape_html(metrics.get('health_score'))}</b></span>
        <span>高优先级 <b class="alert-num">{metrics.get('alert_count', 0)}</b> 项</span>
        <span class="board-src">来源 {_escape_html(board.get('source') or 'rules')}</span>
      </div>
      <div class="decision-grid">{''.join(items_html)}</div>
      {outlook_html}
    </section>"""


def _render_charts_html(facts: dict[str, Any]) -> str:
    idx = facts.get("index") or {}
    mv = facts.get("movers") or {}
    sp = facts.get("spread") or {}
    q = facts.get("quality") or {}
    gainers = mv.get("gainers") or []
    losers = mv.get("losers") or []
    mover_items = (
        [(str(g.get("label") or "")[:14], _to_float(g.get("pct")), "#10b981") for g in gainers[:5]]
        + [(str(l.get("label") or "")[:14], -abs(_to_float(l.get("pct"))), "#f43f5e") for l in losers[:5]]
    )
    spread_items = [
        (str(r.get("goods_name") or "")[:12], _to_float(r.get("spread_pct")), "#8b5cf6")
        for r in (sp.get("rows") or [])[:6]
    ]
    trend = _svg_line_chart(
        idx.get("dates_tail") or [],
        idx.get("overall_tail") or [],
        title="全国农产品价格总指数 · 近14日",
    )
    cats = _svg_category_bars(idx.get("categories") or [], title="主要分类较基期涨跌")
    movers = _svg_hbar_chart(mover_items, title="7日涨跌幅 TOP（涨绿 / 跌红）")
    spreads = _svg_hbar_chart(
        spread_items,
        title="跨省价差 % TOP",
    )
    gauge = _svg_gauge(_to_float(q.get("health_score")), label="数据健康度")
    appendix = facts.get("appendix") or {}
    cmp_ = appendix.get("compare") or {}
    appendix_chart = ""
    if cmp_.get("labels"):
        appendix_chart = f"""
        <div class="chart-panel full">
          <h3>附录 · {_escape_html(cmp_.get('label') or '主选SKU')} 各省中位价</h3>
          {_svg_province_bars(cmp_.get('labels'), cmp_.get('values'))}
        </div>"""
    ts = appendix.get("timeseries") or {}
    if ts.get("dates") and ts.get("values"):
        appendix_chart += f"""
        <div class="chart-panel full">
          <h3>附录 · 近7日均价走势</h3>
          {_svg_line_chart(ts.get('dates'), ts.get('values'), title=_escape_html(ts.get('label') or ''))}
        </div>"""
    return f"""
    <section class="charts-section">
      <div class="section-head"><span class="ai-badge">数据可视化</span><h2>行情图表（系统聚合）</h2></div>
      <div class="chart-grid">
        <div class="chart-panel"><h3>指数趋势</h3>{trend}</div>
        <div class="chart-panel gauge-panel"><h3>质量仪表盘</h3>{gauge}</div>
        <div class="chart-panel"><h3>分类结构</h3>{cats}</div>
        <div class="chart-panel"><h3>价格异动</h3>{movers}</div>
        <div class="chart-panel wide"><h3>跨省价差</h3>{spreads}</div>
      </div>
      {appendix_chart}
    </section>"""


def render_html(
    facts: dict[str, Any],
    narrative: dict[str, Any],
    decision_board: Optional[dict[str, Any]] = None,
) -> str:
    ov = facts.get("overview") or {}
    q = facts.get("quality") or {}
    idx = facts.get("index") or {}
    title = _escape_html(narrative.get("title") or f"全国农产品价格日报 · {facts.get('report_date')}")
    source = narrative.get("source") or "unknown"
    gen_at = _escape_html(facts.get("generated_at_cn") or _now_cn_iso())

    sections_html = []
    for sec in narrative.get("sections") or []:
        heading = _escape_html(sec.get("heading") or "")
        paras = sec.get("paragraphs") or []
        if isinstance(paras, str):
            paras = [paras]
        p_html = "".join(f"<p>{_escape_html(p)}</p>" for p in paras if p)
        sections_html.append(f"<section><h2>{heading}</h2>{p_html}</section>")

    movers = facts.get("movers") or {}
    sp = facts.get("spread") or {}

    def _table(headers: list[str], rows: list[list[Any]]) -> str:
        th = "".join(f"<th>{_escape_html(h)}</th>" for h in headers)
        body = ""
        for row in rows:
            body += "<tr>" + "".join(f"<td>{_escape_html(c)}</td>" for c in row) + "</tr>"
        return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"

    gainers = movers.get("gainers") or []
    losers = movers.get("losers") or []
    mv_table = _table(
        ["类型", "品种", "分类", "涨跌%"],
        [["涨", g.get("label"), g.get("cate_name"), g.get("pct")] for g in gainers[:6]]
        + [["跌", l.get("label"), l.get("cate_name"), l.get("pct")] for l in losers[:6]],
    )
    sp_table = _table(
        ["品种", "价差%", "最低省", "最高省"],
        [
            [r.get("goods_name"), r.get("spread_pct"), r.get("cheapest"), r.get("priciest")]
            for r in (sp.get("rows") or [])[:8]
        ],
    )

    appendix = facts.get("appendix")
    appendix_html = ""
    if appendix:
        aov = appendix.get("overview_filtered") or {}
        cmp_ = appendix.get("compare") or {}
        appendix_html = f"""
        <section class="appendix">
          <div class="section-head"><h2>附录 · 当前筛选口径</h2></div>
          <p>筛选记录 <b>{aov.get('total_rows')}</b> 条 · SKU <b>{aov.get('distinct_skus')}</b> · 省 <b>{aov.get('distinct_districts')}</b></p>
          {_table(['省份','中位价'], list(zip(cmp_.get('labels') or [], cmp_.get('values') or []))[:12]) if cmp_.get('labels') else ''}
        </section>
        """

    board = decision_board or _decision_board_from_facts(facts)
    charts_html = _render_charts_html(facts)
    decision_html = _render_decision_board_html(board)
    chg = _to_float(idx.get("overall_change_pct"))
    chg_cls = "up" if chg > 0 else ("down" if chg < 0 else "")

    kpi_cards = f"""
    <div class="kpi-grid">
      <div class="kpi-card"><span class="kpi-label">当日入库</span><span class="kpi-val">{ov.get('total_rows', 0):,}</span><span class="kpi-sub">条</span></div>
      <div class="kpi-card"><span class="kpi-label">SKU 覆盖</span><span class="kpi-val">{ov.get('distinct_skus', 0):,}</span><span class="kpi-sub">{ov.get('distinct_districts')} 省</span></div>
      <div class="kpi-card accent"><span class="kpi-label">全国总指数</span><span class="kpi-val">{idx.get('overall_latest')}</span><span class="kpi-sub {chg_cls}">{chg:+.2f}%</span></div>
      <div class="kpi-card"><span class="kpi-label">数据健康度</span><span class="kpi-val">{q.get('health_score')}</span><span class="kpi-sub">解析 {q.get('parse_rate')}%</span></div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <style>
    @page {{ size: A4; margin: 14mm 12mm; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif;
            font-size: 10.5pt; color: #0f172a; line-height: 1.55; margin: 0; background: #f8fafc; }}
    .cover {{
      background: linear-gradient(135deg, #0a1628 0%, #0d4f6c 45%, #0077b6 100%);
      color: #fff; padding: 28px 24px 32px; border-radius: 12px; margin-bottom: 20px;
      page-break-after: avoid;
    }}
    .cover-badge {{ display: inline-block; font-size: 8pt; letter-spacing: 0.12em;
      background: rgba(0,229,255,.25); border: 1px solid rgba(0,229,255,.5);
      padding: 4px 10px; border-radius: 20px; margin-bottom: 12px; }}
    .cover h1 {{ font-size: 22pt; margin: 0 0 8px; border: none; color: #fff; font-weight: 700; }}
    .cover .meta {{ color: rgba(255,255,255,.85); margin: 0; font-size: 9.5pt; }}
    .cover-tags {{ margin-top: 14px; display: flex; flex-wrap: wrap; gap: 8px; }}
    .cover-tags span {{ font-size: 8pt; background: rgba(255,255,255,.12); padding: 4px 10px; border-radius: 6px; }}
    .ai-badge {{ font-size: 8pt; background: linear-gradient(90deg,#7c3aed,#06b6d4); color: #fff;
      padding: 3px 10px; border-radius: 4px; margin-right: 8px; vertical-align: middle; }}
    .section-head {{ display: flex; align-items: center; margin: 20px 0 12px; }}
    .section-head h2 {{ margin: 0; font-size: 14pt; color: #0d4f6c; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 18px; }}
    .kpi-card {{ background: #fff; border-radius: 10px; padding: 12px 14px;
      border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(15,23,42,.06); }}
    .kpi-card.accent {{ border-color: #00b4d8; background: linear-gradient(180deg,#f0f9ff,#fff); }}
    .kpi-label {{ display: block; font-size: 8.5pt; color: #64748b; }}
    .kpi-val {{ display: block; font-size: 18pt; font-weight: 700; color: #0f172a; }}
    .kpi-sub {{ font-size: 8.5pt; color: #64748b; }}
    .kpi-sub.up {{ color: #dc2626; }}
    .kpi-sub.down {{ color: #16a34a; }}
    .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .chart-panel {{ background: #fff; border-radius: 10px; padding: 10px 12px;
      border: 1px solid #e2e8f0; page-break-inside: avoid; }}
    .chart-panel.wide {{ grid-column: 1 / -1; }}
    .chart-panel.full {{ grid-column: 1 / -1; margin-top: 10px; }}
    .chart-panel h3 {{ margin: 0 0 6px; font-size: 10pt; color: #475569; }}
    .gauge-panel {{ display: flex; flex-direction: column; align-items: center; }}
    .chart-svg {{ width: 100%; height: auto; }}
    .chart-title {{ font-size: 9pt; fill: #334155; font-weight: 600; }}
    .chart-empty {{ color: #94a3b8; font-size: 9pt; padding: 24px; text-align: center; }}
    .narrative section {{ background: #fff; border-radius: 10px; padding: 14px 16px;
      margin-bottom: 12px; border-left: 4px solid #00b4d8; box-shadow: 0 1px 4px rgba(0,0,0,.04); }}
    .narrative h2 {{ font-size: 12pt; color: #1565c0; margin: 0 0 8px; }}
    .narrative p {{ margin: 0 0 8px; color: #334155; }}
    .decision-board {{ background: linear-gradient(180deg,#f5f3ff 0%,#fff 40%);
      border: 1px solid #c4b5fd; border-radius: 12px; padding: 16px; margin: 18px 0; }}
    .decision-headline {{ font-size: 11pt; color: #4c1d95; margin: 0 0 12px; font-weight: 600; }}
    .decision-metrics {{ display: flex; flex-wrap: wrap; gap: 12px 20px; font-size: 9pt;
      color: #475569; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px dashed #ddd6fe; }}
    .decision-metrics b {{ color: #0f172a; }}
    .alert-num {{ color: #dc2626; }}
    .board-src {{ margin-left: auto; color: #7c3aed; }}
    .decision-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .decision-card {{ background: #fff; border-radius: 8px; padding: 12px; border: 1px solid #e2e8f0; }}
    .decision-card.risk-high {{ border-left: 4px solid #ef4444; }}
    .decision-card.risk-mid {{ border-left: 4px solid #f59e0b; }}
    .decision-card.risk-low {{ border-left: 4px solid #22c55e; }}
    .dc-head {{ margin-bottom: 6px; }}
    .dc-level {{ font-size: 8pt; font-weight: 700; padding: 2px 8px; border-radius: 4px;
      background: #fee2e2; color: #b91c1c; margin-right: 6px; }}
    .risk-mid .dc-level {{ background: #fef3c7; color: #b45309; }}
    .risk-low .dc-level {{ background: #dcfce7; color: #15803d; }}
    .dc-tag {{ font-size: 8pt; color: #64748b; }}
    .decision-card h4 {{ margin: 0 0 6px; font-size: 10.5pt; color: #0f172a; }}
    .dc-analysis, .dc-action {{ font-size: 9pt; margin: 0 0 6px; color: #475569; }}
    .decision-outlook {{ font-size: 9.5pt; color: #5b21b6; margin: 12px 0 0;
      padding: 10px; background: rgba(124,58,237,.08); border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 9pt; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 6px 8px; text-align: left; }}
    th {{ background: #f1f5f9; color: #334155; }}
    .data-tables {{ background: #fff; border-radius: 10px; padding: 14px; margin-top: 16px; }}
    .data-tables h2 {{ font-size: 11pt; color: #475569; margin: 12px 0 8px; }}
    footer {{ margin-top: 20px; font-size: 8.5pt; color: #94a3b8; text-align: center;
      padding-top: 12px; border-top: 1px solid #e2e8f0; }}
    .page-break-avoid {{ page-break-inside: avoid; }}
  </style>
</head>
<body>
  <header class="cover">
    <div class="cover-badge">DAZONG · 数据智能挖掘中心</div>
    <h1>{title}</h1>
    <p class="meta">生成时间（北京时间）{gen_at} · 叙述 {_escape_html(source)} · 库表 zgncpjgw_price_crawl</p>
    <div class="cover-tags">
      <span>大模型润色</span><span>规则引擎研判</span><span>SVG 行情图表</span><span>监管决策看板</span>
    </div>
  </header>
  {kpi_cards}
  {charts_html}
  {decision_html}
  <div class="narrative">
    <div class="section-head"><span class="ai-badge">LLM 正文</span><h2>分析正文</h2></div>
    {''.join(sections_html)}
  </div>
  <div class="data-tables page-break-avoid">
    <div class="section-head"><h2>数据明细表</h2></div>
    <h2>异动榜</h2>{mv_table}
    <h2>跨省价差榜</h2>{sp_table}
  </div>
  {appendix_html}
  <footer>大综食材供应链 · 全国农产品价格智能日报 · 数字以库内采集为准 · Powered by DashScope + Playwright</footer>
</body>
</html>"""


def _html_to_pdf_sync(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with _PLAYWRIGHT_LOCK:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="networkidle", timeout=60_000)
                return page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "12mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
                )
            finally:
                browser.close()


async def html_to_pdf(html: str) -> bytes:
    return await asyncio.wait_for(asyncio.to_thread(_html_to_pdf_sync, html), timeout=120.0)


async def build_daily_report(
    db: AsyncSession,
    flt: ReportFilter,
    *,
    output_format: str = "json",
) -> tuple[dict[str, Any], Optional[bytes]]:
    facts = await collect_facts(db, flt)
    narrative, decision_board = await asyncio.gather(
        generate_narrative(facts),
        generate_decision_board(facts),
    )
    html = render_html(facts, narrative, decision_board)
    payload: dict[str, Any] = {
        "title": narrative.get("title"),
        "sections": narrative.get("sections"),
        "decision_board": decision_board,
        "facts": facts,
        "source": narrative.get("source"),
        "generated_at": facts.get("generated_at_cn"),
        "html_preview": html[:12000] if output_format == "json" else None,
    }
    pdf_bytes: Optional[bytes] = None
    if output_format == "pdf":
        pdf_bytes = await html_to_pdf(html)
    return payload, pdf_bytes
