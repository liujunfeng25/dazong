"""Answer 合成层：基于工具结果生成通人性监管分析回复。"""

from __future__ import annotations

import re
from typing import Any, Callable, Awaitable, Optional

_MIXED_MARKERS = ("顺便", "同时", "还有", "并且", "另外", "再看", "顺带", "以及")
_COUNT_HINTS = ("几条", "几个", "几单", "几张", "多少", "GMV", "告警")
_HOW_TO_HINTS = ("怎么", "如何", "在哪", "哪里", "入口", "是啥", "是什么", "演示账号", "账号是啥", "密码", "链路")


SYNTHESIS_SYSTEM = (
    "你是大宗供应链监管端 AI 分析助手。请基于已执行的工具结果，用自然、有洞察的中文回答用户。"
    "要求：\n"
    "1. 先直接回应用户问题，再给出关键数字（必须与工具 summary/rows 一致，禁止编造）。\n"
    "2. 用要点组织，附 1–2 句监管判断或下一步建议。\n"
    "3. 若工具返回 ask_clarification/clarify，用一句友好追问转述。\n"
    "4. 若你做了默认假设（如未指定时间而按今天统计），必须说明假设。\n"
    "5. 不要输出原始 JSON，不要复读工具 summary 原文。\n"
    "6. 【禁止答非所问】只回答用户所问；手册类勿堆砌无关 KPI，查数类勿只讲操作步骤。\n"
    "7. 【混合问法】含「顺便/同时/还有」等多意图时，须逐条回答每一部分，不可只答其一。\n"
    "8. 【计数问法】用户问「几条/几个/多少」时，必须给出具体数字（含 0 也要写「0 条」）。\n"
    "9. 【日期一致】回复中的统计日期必须与工具参数 start_date/end_date 或报表标题一致，禁止写错日期。"
)

INTENT_SYNTHESIS_HINTS: dict[str, str] = {
    "how_to": "【操作手册类】步骤清晰、入口明确；若有参考来源须在文末自然提及；不要堆砌无关 KPI。",
    "analytics": "【数据查数类】数字必须与工具 summary/rows 一致；附 1 句监管判断或关注建议。",
    "report": "【报表类】概括报告要点与日期区间/主体；可提示用户展开「报表全文」用 Word/Markdown 导出。",
}


def should_synthesize(
    *,
    tool_calls_debug: list[dict[str, Any]],
    final_tool_result: dict[str, Any],
    reply: str,
    min_tools: int,
) -> bool:
    """单工具且 summary 已足够时跳过合成，降低延迟与成本。"""
    if not tool_calls_debug:
        return False
    if not (reply or "").strip():
        return True
    final_type = str(final_tool_result.get("type") or "")
    if final_type in ("report", "clarify"):
        return True
    if len(tool_calls_debug) >= max(0, int(min_tools)):
        return True
    return False


def count_mixed_sub_intents(text: str) -> int:
    """估算用户问题中的子意图数量（混合问法）。"""
    t = (text or "").strip()
    if not t:
        return 1
    extra = sum(1 for m in _MIXED_MARKERS if m in t)
    return min(1 + extra, 4)


def expects_explicit_count(text: str) -> bool:
    t = (text or "").strip()
    return any(p in t for p in _COUNT_HINTS)


def extract_tool_date_anchors(tool_calls_debug: list[dict[str, Any]]) -> list[str]:
    dates: list[str] = []
    for call in tool_calls_debug:
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            continue
        for key in ("start_date", "end_date"):
            v = str(args.get(key) or "").strip()
            if v and v not in dates:
                dates.append(v)
    return dates


def _reply_has_digit(reply: str) -> bool:
    return bool(re.search(r"\d", reply or ""))


def reply_missing_mixed_coverage(
    user_text: str,
    reply: str,
    tool_calls_debug: list[dict[str, Any]],
) -> list[str]:
    """返回未覆盖的子意图标签，供合成重试提示。"""
    missing: list[str] = []
    t = (user_text or "").strip()
    r = (reply or "").strip()
    if not t:
        return missing
    tool_names = {str(c.get("name") or "") for c in tool_calls_debug}

    wants_how_to = any(k in t for k in _HOW_TO_HINTS)
    wants_metrics = expects_explicit_count(t) or any(k in t for k in ("GMV", "告警", "生意", "订单", "KPI", "kpi"))

    if wants_how_to:
        covered = "search_docs" in tool_names or any(k in r for k in ("手册", "入口", "步骤", "/monitor", "侧栏", "demo123"))
        if not covered:
            missing.append("操作说明/手册步骤")

    if wants_metrics:
        analytics_tools = {"get_kpi_summary", "search_alerts", "search_orders", "get_today_orders", "generate_report"}
        if not (tool_names & analytics_tools):
            missing.append("查数/统计")
        elif expects_explicit_count(t) and not _reply_has_digit(r):
            missing.append("具体数字（几条/多少，含 0 也要写）")

    if count_mixed_sub_intents(t) >= 2 and wants_how_to and wants_metrics:
        if len(missing) == 0 and (not _reply_has_digit(r) or "手册" not in r and "/monitor" not in r):
            if not _reply_has_digit(r):
                missing.append("混合问法中的查数部分")
            if not any(k in r for k in ("手册", "入口", "步骤", "/monitor", "稽核", "demo123", "账号")):
                missing.append("混合问法中的操作说明部分")

    return missing


def needs_completeness_retry(
    user_text: str,
    reply: str,
    tool_calls_debug: list[dict[str, Any]],
) -> bool:
    return bool(reply_missing_mixed_coverage(user_text, reply, tool_calls_debug))


def build_completeness_reminder(
    user_text: str,
    reply: str,
    tool_calls_debug: list[dict[str, Any]],
) -> str:
    missing = reply_missing_mixed_coverage(user_text, reply, tool_calls_debug)
    dates = extract_tool_date_anchors(tool_calls_debug)
    parts = ["请重写回答，修正以下问题："]
    for item in missing:
        parts.append(f"- 遗漏：{item}")
    if dates:
        parts.append(f"- 统计/报表日期必须写为：{'、'.join(dates)}（与工具参数一致）")
    parts.append("- 混合问法须逐条回应，禁止只答一部分。")
    return "\n".join(parts)


def _collect_citations(tool_calls_debug: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for call in tool_calls_debug:
        if str(call.get("name") or "") != "search_docs":
            continue
        for cite in call.get("citations") or []:
            if not isinstance(cite, dict):
                continue
            doc = str(cite.get("doc") or "")
            section = str(cite.get("section") or "")
            key = f"{doc}|{section}"
            if key in seen:
                continue
            seen.add(key)
            out.append({"doc": doc, "section": section})
    return out


def build_synthesis_messages(
    user_text: str,
    *,
    tool_summaries: list[str],
    session_hint: str = "",
    draft_reply: str = "",
    intent: str = "",
    citations: Optional[list[dict[str, str]]] = None,
    tool_calls_debug: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    system = SYNTHESIS_SYSTEM
    hint = INTENT_SYNTHESIS_HINTS.get(intent or "")
    if hint:
        system = f"{system}\n{hint}"
    parts = [f"用户问题：{user_text}"]
    if count_mixed_sub_intents(user_text) >= 2:
        parts.append("【混合问法检查清单】用户问了多个子问题，回答须逐条覆盖，不可只答其一。")
    if expects_explicit_count(user_text):
        parts.append("【计数要求】用户问了数量，必须给出具体数字（0 也要明确写「0 条/0 单」）。")
    if tool_calls_debug:
        dates = extract_tool_date_anchors(tool_calls_debug)
        if dates:
            parts.append(f"【日期锚点】回复中的日期必须与工具一致：{'、'.join(dates)}")
    if session_hint:
        parts.append(f"会话上下文：{session_hint}")
    if tool_summaries:
        parts.append("工具执行摘要：\n" + "\n---\n".join(tool_summaries))
    if citations:
        cite_lines = "\n".join(f"- {c.get('doc', '')} §{c.get('section', '')}" for c in citations)
        parts.append("手册参考来源（回答中应自然提及）：\n" + cite_lines)
    if draft_reply:
        parts.append(f"初稿（可改写润色，数字不可改）：{draft_reply}")
    parts.append("请给出最终回答。")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


async def synthesize_answer(
    user_text: str,
    *,
    tool_calls_debug: list[dict[str, Any]],
    llm_chat: Callable[[list[dict[str, Any]], Optional[list]], Awaitable[dict[str, Any]]],
    first_choice: Callable[[dict[str, Any]], dict[str, Any]],
    session_hint: str = "",
    draft_reply: str = "",
    intent: str = "",
) -> str:
    summaries: list[str] = []
    for call in tool_calls_debug:
        name = str(call.get("name") or "")
        preview = str(call.get("result_preview") or "")
        if name and preview:
            summaries.append(f"[{name}] {preview}")
    if not summaries and draft_reply:
        return draft_reply.strip()
    citations = _collect_citations(tool_calls_debug)
    messages = build_synthesis_messages(
        user_text,
        tool_summaries=summaries,
        session_hint=session_hint,
        draft_reply=draft_reply,
        intent=intent,
        citations=citations or None,
        tool_calls_debug=tool_calls_debug,
    )
    try:
        resp = await llm_chat(messages, None)
        content = str((first_choice(resp).get("content") or "")).strip()
        if content and needs_completeness_retry(user_text, content, tool_calls_debug):
            retry_msgs = [
                *messages,
                {"role": "assistant", "content": content},
                {"role": "user", "content": build_completeness_reminder(user_text, content, tool_calls_debug)},
            ]
            resp2 = await llm_chat(retry_msgs, None)
            retry_content = str((first_choice(resp2).get("content") or "")).strip()
            if retry_content:
                content = retry_content
        return content or draft_reply
    except Exception:
        return draft_reply
