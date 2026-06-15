#!/usr/bin/env python3
"""重建 AI 操作手册 RAG 索引。用法: cd dazong && python backend/scripts/index_docs_rag.py"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.ai_chat.rag.indexer import build_index, default_index_path
from services.ai_chat.rag.retriever import reload_index


def _embedded_index_path() -> Path:
    from config import settings

    path = Path(settings.docs_embedded_index_path or "data/rag/chunks.embedded.jsonl")
    if path.is_absolute():
        return path
    return BACKEND / path


def main() -> None:
    out = default_index_path()
    n = build_index(out)
    # Markdown 分块变化后，旧向量索引的文本和 chunk_id 都可能已经过期。
    _embedded_index_path().unlink(missing_ok=True)
    reload_index()
    print(f"Indexed {n} chunks -> {out}")


if __name__ == "__main__":
    main()
