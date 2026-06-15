from services.ai_chat.rag.retriever import _bm25_scores, _normalize, search_docs


def test_bm25_scores_nonempty():
    chunks = [
        {"chunk_id": "a", "text": "稽核链路查询操作步骤", "audience": "monitor", "tier": "A"},
        {"chunk_id": "b", "text": "演示账号密码说明", "audience": "monitor", "tier": "A"},
    ]
    scores = _bm25_scores("稽核链路", chunks, "monitor")
    assert scores.get("a", 0) > 0


def test_normalize():
    assert _normalize({"a": 2.0, "b": 1.0})["a"] == 1.0


def test_search_docs_fallback_without_index(monkeypatch):
    monkeypatch.setattr("services.ai_chat.rag.retriever.settings.rag_enabled", True)
    monkeypatch.setattr("services.ai_chat.rag.retriever._load_chunks", lambda use_embedded: [])
    assert search_docs("稽核") == []
