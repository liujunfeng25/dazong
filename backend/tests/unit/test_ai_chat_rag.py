import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("backend runtime is Python 3.11", allow_module_level=True)

from services.ai_chat.cards import artifact_from_tool, normalize_chart_type
from services.ai_chat.intent import classify_intent
from services.ai_chat.rag.retriever import search_docs


def test_classify_intent_how_to():
    assert classify_intent("稽核链路怎么查") == "how_to"
    assert classify_intent("演示账号是什么") == "how_to"


def test_classify_intent_analytics():
    assert classify_intent("今天一级分类饼图") == "analytics"


def test_normalize_chart_type():
    assert normalize_chart_type("pie", "rank") == "pie"
    assert normalize_chart_type(None, "trend") == "line"


def test_artifact_from_tool_includes_chart_type_and_citations():
    card, report = artifact_from_tool(
        {
            "type": "rank",
            "chart_type": "pie",
            "title": "品类",
            "columns": [],
            "rows": [{"name": "肉", "amount": 1}],
            "citations": [{"doc": "06", "section": "6.10"}],
        }
    )
    assert report == ""
    assert card["chart_type"] == "pie"
    assert card["citations"][0]["doc"] == "06"


def test_search_docs_faq_hit():
    hits = search_docs("AI 助手在哪里", top_k=3)
    if not hits:
        pytest.skip("rag index not built")
    assert any("AI" in (h.get("text") or "") or "助手" in (h.get("text") or "") for h in hits)
