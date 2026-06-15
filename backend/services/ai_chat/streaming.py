"""SSE 流式事件辅助（监管 AI 对话）。"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator


def phase_message_for_result(result: dict[str, Any]) -> str:
    debug = result.get("debug") or {}
    intent = str(debug.get("intent") or "")
    provider = str(debug.get("provider") or "")
    if intent == "how_to" or provider == "rag":
        return "正在检索操作手册…"
    if intent == "report" or provider == "fast_path" and "report" in json.dumps(debug, ensure_ascii=False):
        return "正在生成监管报告…"
    if intent in ("national_price", "xinfadi"):
        return "正在查询全国农产品价格…"
    if intent == "analytics" or provider == "fast_path":
        return "正在查询业务数据…"
    return "正在分析监管问题…"


def iter_reply_deltas(reply: str) -> Iterator[str]:
    for chunk in re.split(r"([。；\n])", reply or ""):
        if chunk:
            yield chunk


def sse_training_phase(payload: dict[str, Any]) -> str:
    return f"event: training_phase\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_events_from_result(result: dict[str, Any]) -> Iterator[str]:
    yield f"event: phase\ndata: {json.dumps({'phase': 'running', 'message': phase_message_for_result(result)}, ensure_ascii=False)}\n\n"
    yield f"event: tool\ndata: {json.dumps(result.get('debug') or {}, ensure_ascii=False)}\n\n"
    for chunk in iter_reply_deltas(str(result.get("reply") or "")):
        yield f"event: delta\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
    yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
