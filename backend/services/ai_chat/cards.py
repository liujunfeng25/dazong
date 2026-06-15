"""data_card / 工具结果 → 前端卡片契约。"""

from __future__ import annotations

from typing import Any, Optional


def normalize_chart_type(raw: Any, card_type: str = "") -> str:
    hint = str(raw or "").strip().lower()
    if hint in {"pie", "bar", "line", "none"}:
        return hint
    if card_type == "trend":
        return "line"
    if card_type == "rank":
        return "bar"
    return "none"


def artifact_from_tool(tool_result: dict[str, Any]) -> tuple[Optional[dict[str, Any]], str]:
    report = str(tool_result.get("report_content") or "")
    if tool_result.get("type") == "report":
        return None, report
    card_type = str(tool_result.get("type") or "table")
    return {
        "type": card_type,
        "chart_type": normalize_chart_type(tool_result.get("chart_type"), card_type),
        "title": tool_result.get("title") or "数据卡片",
        "columns": tool_result.get("columns") or [],
        "rows": tool_result.get("rows") or [],
        "row_count": tool_result.get("row_count"),
        "sql": tool_result.get("sql"),
        "citations": tool_result.get("citations") or [],
    }, report


def citations_from_rag(hits: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for h in hits:
        doc = str(h.get("doc_title") or h.get("doc_id") or "")
        section = str(h.get("section") or "")
        key = f"{doc}|{section}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"doc": doc, "section": section})
    return out
