#!/usr/bin/env python3
"""校验 RAG 索引文件存在且非空。CI / Makefile 调用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
INDEX = BACKEND / "data" / "rag" / "chunks.jsonl"
EMBEDDED_INDEX = BACKEND / "data" / "rag" / "chunks.embedded.jsonl"
MIN_CHUNKS = 50


def main() -> int:
    if not INDEX.is_file():
        print(f"RAG index missing: {INDEX}")
        print("Run: python backend/scripts/index_docs_rag.py")
        return 1
    count = 0
    with INDEX.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
                json.loads(line)
    if count < MIN_CHUNKS:
        print(f"RAG index too small: {count} chunks (need >= {MIN_CHUNKS})")
        return 1
    if EMBEDDED_INDEX.is_file():
        embedded_count = 0
        with EMBEDDED_INDEX.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    embedded_count += 1
                    json.loads(line)
        if embedded_count != count:
            print(
                "Embedded RAG index is stale or incomplete: "
                f"{embedded_count} chunks (BM25 has {count})"
            )
            return 1
    print(f"RAG index ok: {count} chunks at {INDEX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
