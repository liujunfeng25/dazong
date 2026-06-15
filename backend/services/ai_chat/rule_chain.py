"""无 API key 时的多步规则链（lookup → 业务工具）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Awaitable, Optional

from services.ai_chat.intent import has_analytics_side_request
from services.ai_chat.session_memory import resolve_relative_day

HOW_TO_HINTS = ("怎么", "如何", "在哪", "哪里", "演示账号", "是啥", "是什么")
REPORT_HINTS = ("日报", "周报", "月报")


def _mixed_how_to_and_analytics(text: str) -> bool:
    t = (text or "").strip()
    if not has_analytics_side_request(t):
        return False
    return any(k in t for k in HOW_TO_HINTS) or any(k in t for k in ("演示账号", "账号是啥", "密码", "链路"))


def _analytics_companion_tool(
    text: str,
    heuristic_tool: Callable[[str, Optional[dict[str, Any]]], tuple[str, dict[str, Any]]],
    entities: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """混合问法第二步：查数/告警/KPI（与 search_docs 配对）。"""
    name, args = heuristic_tool(text, entities)
    if name == "search_docs":
        t = text or ""
        if any(k in t for k in ("告警", "预警", "开放")):
            return "search_alerts", {"limit": 20}
        day = resolve_relative_day(text, date.today())
        if day:
            return "get_kpi_summary", {"scope": "range", "start_date": day[0], "end_date": day[1]}
        if any(k in t for k in ("GMV", "生意", "订单", "单", "KPI", "kpi")):
            return "get_kpi_summary", {"scope": "today"}
        return "get_kpi_summary", {"scope": "today"}
    return name, args


def _pick_initial_tool(
    text_value: str,
    entities: dict[str, Any],
    heuristic_tool: Callable[[str, Optional[dict[str, Any]]], tuple[str, dict[str, Any]]],
    apply_report_day_range: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None,
    today: Optional[date] = None,
) -> tuple[str, dict[str, Any]]:
    t = (text_value or "").strip()
    ref_day = today or date.today()
    session_subject = entities.get("session_subject_name")
    rel_day = resolve_relative_day(text_value, ref_day)
    if rel_day and session_subject and any(k in t for k in ("换", "改", "呢", "再来")):
        return "generate_report", {
            "report_type": "daily",
            "subject_name": str(session_subject),
            "start_date": rel_day[0],
            "end_date": rel_day[1],
        }
    if any(k in t for k in HOW_TO_HINTS) and not has_analytics_side_request(t):
        return "search_docs", {"query": t or "操作手册"}
    if any(k in t for k in REPORT_HINTS) and not any(k in t for k in ("怎么", "如何")):
        if any(k in t for k in ("月报", "本月", "这个月", "上个月", "上月", "当月")):
            rt = "monthly"
        elif any(k in t for k in ("周报", "本周", "这周", "上周")):
            rt = "weekly"
        else:
            rt = "daily"
        gen_args: dict[str, Any] = {"report_type": rt}
        if session_subject:
            gen_args["subject_name"] = session_subject
        if apply_report_day_range:
            gen_args = apply_report_day_range(text_value, gen_args)
        return "generate_report", gen_args
    return heuristic_tool(text_value, entities)


async def run_rule_chain(
    text_value: str,
    *,
    heuristic_tool: Callable[[str, Optional[dict[str, Any]]], tuple[str, dict[str, Any]]],
    dispatch_tool: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    entities: Optional[dict[str, Any]] = None,
    max_steps: int = 3,
    apply_report_day_range: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None,
    today: Optional[date] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """返回 (tool_calls_debug, final_result, reply_hint)。"""
    entities = entities or {}
    debug: list[dict[str, Any]] = []
    final: dict[str, Any] = {"type": "notice", "summary": "暂无匹配分析。"}
    name, args = _pick_initial_tool(text_value, entities, heuristic_tool, apply_report_day_range, today)
    if name.startswith("_"):
        return debug, final, ""

    mixed = _mixed_how_to_and_analytics(text_value)
    if mixed and name != "search_docs":
        doc_result = await dispatch_tool("search_docs", {"query": text_value or "操作手册"})
        debug.append({
            "name": "search_docs",
            "arguments": {"query": text_value or "操作手册"},
            "result_preview": _preview_result(doc_result),
            "citations": doc_result.get("citations") or [],
        })
        name, args = _analytics_companion_tool(text_value, heuristic_tool, entities)

    for _ in range(max_steps):
        result = await dispatch_tool(name, args)
        entry: dict[str, Any] = {
            "name": name,
            "arguments": args,
            "result_preview": _preview_result(result),
        }
        if name == "search_docs":
            entry["citations"] = result.get("citations") or []
        debug.append(entry)
        if result.get("type") != "error":
            final = result
        if name == "lookup_entity_by_name":
            rows = result.get("rows") or []
            if not rows:
                break
            top = rows[0]
            stype = str(top.get("type") or "")
            sid = top.get("id")
            if stype == "delivery" and sid is not None:
                name, args = "get_delivery_metrics", {"delivery_id": int(sid)}
                continue
            if stype == "client" and sid is not None:
                name, args = "get_client_metrics", {"client_id": int(sid)}
                continue
            if stype == "supplier" and sid is not None:
                name, args = "get_supplier_metrics", {"supplier_id": int(sid)}
                continue
        if name == "search_docs":
            if mixed and len(debug) < max_steps:
                name, args = _analytics_companion_tool(text_value, heuristic_tool, entities)
                continue
            break
        if "怎么" in text_value or "如何" in text_value:
            break
        break

    reply = str(final.get("summary") or "已完成分析。")
    return debug, final, reply


def _preview_result(obj: Any) -> str:
    import json

    try:
        value = json.dumps(obj, ensure_ascii=False)
    except Exception:
        value = str(obj)
    return value if len(value) <= 500 else value[:500] + "…"
