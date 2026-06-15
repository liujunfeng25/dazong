"""how_to / RAG 编排（与 routers/chat._dispatch 配合）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Awaitable, Optional

from config import settings
from services.ai_chat.cards import citations_from_rag
from services.ai_chat.rag.retriever import search_docs


async def answer_how_to(
    text_value: str,
    *,
    llm_answer: Optional[Callable[[list[dict[str, Any]]], Awaitable[str]]] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """基于操作手册 RAG 回答「怎么用」类问题。"""
    hits = search_docs(text_value, audience="monitor")
    citations = citations_from_rag(hits)
    reply = ""

    if hits and llm_answer and (settings.ai_api_key or "").strip():
        ctx_parts = []
        for h in hits:
            ctx_parts.append(
                f"### {h.get('doc_title')} — {h.get('section')}\n{(h.get('text') or '')[:1400]}"
            )
        rag_context = "\n\n".join(ctx_parts)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是大宗供应链监管端操作手册助手。仅根据下列手册摘录回答「怎么用、在哪、步骤」类问题。"
                    "禁止编造订单号、金额、GMV 等实时业务数字（应提示用户用数据分析功能查询）。"
                    "摘录中含 ⚠️ 的内容须提醒「以运营配置为准」。回答用简洁中文要点。"
                    f"\n\n{rag_context}"
                ),
            },
            {"role": "user", "content": text_value},
        ]
        try:
            reply = (await llm_answer(messages)).strip()
        except Exception:
            reply = ""

    if not reply and hits:
        top = hits[0]
        reply = (
            f"根据操作手册 **{top.get('doc_title')}**（§{top.get('section')}）：\n\n"
            f"{(top.get('text') or '')[:900]}"
        )
    if not reply:
        reply = (
            "未在操作手册中找到直接匹配的说明。你可以尝试换关键词（如「稽核」「广播」「AI 助手」「演示账号」），"
            "或问我「能查哪些数据」了解分析能力范围。"
        )

    if citations:
        cite_lines = "\n".join(f"- {c['doc']} §{c['section']}" for c in citations)
        reply = f"{reply}\n\n**参考来源**\n{cite_lines}"

    rows = [
        {
            "doc": h.get("doc_title"),
            "section": h.get("section"),
            "excerpt": ((h.get("text") or "")[:160] + "…") if len(h.get("text") or "") > 160 else (h.get("text") or ""),
            "score": h.get("score"),
        }
        for h in hits[:5]
    ]
    data_card = {
        "type": "table",
        "chart_type": "none",
        "title": "相关手册摘录",
        "columns": [
            {"key": "doc", "label": "文档"},
            {"key": "section", "label": "章节"},
            {"key": "excerpt", "label": "摘要"},
        ],
        "rows": rows,
        "citations": citations,
    } if rows else None

    sid = session_id or f"chat-{datetime.utcnow().strftime('%Y%m%d')}"
    return {
        "reply": reply,
        "data_card": data_card,
        "report_content": "",
        "session_id": sid,
        "debug": {
            "intent": "how_to",
            "provider": "rag",
            "rag_chunks": [
                {"chunk_id": h.get("chunk_id"), "doc": h.get("doc_title"), "section": h.get("section"), "score": h.get("score")}
                for h in hits
            ],
        },
    }
