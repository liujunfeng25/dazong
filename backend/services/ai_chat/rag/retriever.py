"""BM25 + 向量混合文档检索。"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import settings

from services.ai_chat.rag.indexer import default_index_path

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}")


def _tokenize(text: str) -> list[str]:
    t = (text or "").lower()
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(t):
        w = m.group(0)
        if len(w) > 2 and all("\u4e00" <= c <= "\u9fff" for c in w):
            for i in range(len(w) - 1):
                tokens.append(w[i : i + 2])
        else:
            tokens.append(w)
    return tokens


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _index_path() -> Path:
    p = Path(settings.docs_index_path or "")
    if p.is_absolute():
        return p
    return _backend_root() / (settings.docs_index_path or "data/rag/chunks.jsonl")


def _embedded_index_path() -> Path:
    p = Path(settings.docs_embedded_index_path or "")
    if p.is_absolute():
        return p
    return _backend_root() / (settings.docs_embedded_index_path or "data/rag/chunks.embedded.jsonl")


@lru_cache(maxsize=2)
def _load_chunks(use_embedded: bool) -> list[dict[str, Any]]:
    path = _embedded_index_path() if use_embedded else _index_path()
    if use_embedded and not path.is_file():
        path = _index_path()
    if not path.is_file():
        alt = default_index_path()
        if alt.is_file():
            path = alt
        else:
            return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def reload_index() -> None:
    _load_chunks.cache_clear()


def _bm25_scores(query: str, chunks: list[dict[str, Any]], audience: str) -> dict[str, float]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return {}
    tier_w = {"A": 1.25, "B": 1.0, "C": 0.85}
    scores: dict[str, float] = {}
    for ch in chunks:
        aud = ch.get("audience") or "all"
        if aud not in ("all", audience):
            continue
        cid = str(ch.get("chunk_id") or id(ch))
        text = ch.get("text") or ""
        c_tokens = _tokenize(text)
        if not c_tokens:
            continue
        tf = sum(c_tokens.count(qt) for qt in q_tokens)
        if tf == 0:
            if not any(qt in text for qt in q_tokens if len(qt) >= 2):
                continue
            tf = 0.5
        doc_hits = sum(1 for c in chunks if any(qt in (c.get("text") or "") for qt in q_tokens))
        idf = 1.0 + math.log(1 + len(chunks) / (1 + doc_hits))
        score = tf * idf * tier_w.get(ch.get("tier") or "B", 1.0)
        if ch.get("confidence") == "review":
            score *= 0.95
        scores[cid] = score
    return scores


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _vector_scores(query: str, chunks: list[dict[str, Any]], audience: str) -> dict[str, float]:
    if not any(isinstance(ch.get("vector"), list) and ch.get("vector") for ch in chunks):
        return {}
    try:
        from services.ai_chat.rag.embedder import embed_texts_sync

        q_vec = embed_texts_sync([query])
        if not q_vec or not q_vec[0]:
            return {}
        qv = q_vec[0]
    except Exception:
        return {}
    scores: dict[str, float] = {}
    for ch in chunks:
        aud = ch.get("audience") or "all"
        if aud not in ("all", audience):
            continue
        vec = ch.get("vector")
        if not isinstance(vec, list):
            continue
        cid = str(ch.get("chunk_id") or id(ch))
        scores[cid] = max(0.0, _cosine(qv, vec))
    return scores


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    mx = max(scores.values())
    if mx <= 0:
        return {k: 0.0 for k in scores}
    return {k: v / mx for k, v in scores.items()}


def search_docs(
    query: str,
    *,
    top_k: int | None = None,
    audience: str = "monitor",
) -> list[dict[str, Any]]:
    if not settings.rag_enabled:
        return []
    k = top_k or settings.rag_top_k
    embedded = _embedded_index_path().is_file()
    chunks = _load_chunks(embedded)
    if not chunks:
        return []

    bm25 = _normalize(_bm25_scores(query, chunks, audience))
    vec = _normalize(_vector_scores(query, chunks, audience))
    alpha = float(settings.rag_hybrid_alpha)

    scored: list[tuple[float, dict[str, Any]]] = []
    for ch in chunks:
        aud = ch.get("audience") or "all"
        if aud not in ("all", audience):
            continue
        cid = str(ch.get("chunk_id") or id(ch))
        b = bm25.get(cid, 0.0)
        v = vec.get(cid, 0.0)
        if not vec:
            final = b
        elif not bm25:
            final = v
        else:
            final = alpha * b + (1.0 - alpha) * v
        if final <= 0:
            continue
        scored.append((final, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for score, ch in scored[:k]:
        row = dict(ch)
        row.pop("vector", None)
        row["score"] = round(score, 4)
        out.append(row)
    return out
