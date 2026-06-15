"""监管 AI 对话结构化日志（便于失败问法沉淀）。"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("dazong.ai_chat")


def log_turn(
    *,
    session_id: Optional[str],
    user_text: str,
    intent: str,
    provider: str,
    tool_calls: list[dict[str, Any]] | None = None,
    rag_chunk_ids: list[str] | None = None,
    fallback: bool = False,
    error: str | None = None,
    duration_ms: int | None = None,
    route: str | None = None,
    synthesis: bool = False,
) -> None:
    tools = tool_calls or []
    tool_names = [str(t.get("name") or "") for t in tools if isinstance(t, dict)]
    payload = {
        "event": "ai_chat_turn",
        "session_id": session_id,
        "intent": intent,
        "provider": provider,
        "route": route or provider,
        "user_preview": (user_text or "")[:200],
        "tool_count": len(tools),
        "tools": tool_names[:8],
        "rag_chunk_ids": rag_chunk_ids or [],
        "fallback": fallback,
        "synthesis": synthesis,
        "error": (error or "")[:220] or None,
        "duration_ms": duration_ms,
    }
    logger.info("%s", json.dumps(payload, ensure_ascii=False))
