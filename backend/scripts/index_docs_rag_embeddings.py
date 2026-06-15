#!/usr/bin/env python3
"""为 RAG 分块构建 DashScope embedding 索引。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from services.ai_chat.rag.embedder import embed_texts_sync  # noqa: E402
from services.ai_chat.rag.retriever import reload_index  # noqa: E402


def _chunks_path() -> Path:
    p = Path(settings.docs_index_path or "data/rag/chunks.jsonl")
    if p.is_absolute():
        return p
    return BACKEND / p


def _out_path() -> Path:
    p = Path(settings.docs_embedded_index_path or "data/rag/chunks.embedded.jsonl")
    if p.is_absolute():
        return p
    return BACKEND / p


def main() -> int:
    src = _chunks_path()
    if not src.is_file():
        print(f"缺少 BM25 索引：{src}，请先运行 index_docs_rag.py")
        return 1
    rows: list[dict] = []
    with src.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        print("chunks.jsonl 为空")
        return 1
    out = _out_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    temp_out = out.with_name(f".{out.name}.tmp")
    temp_out.unlink(missing_ok=True)
    api_key = (settings.ai_api_key or "").strip()
    if not api_key:
        print("AI_API_KEY 未配置，跳过 embedding，复制 BM25 索引")
        with temp_out.open("w", encoding="utf-8") as wf:
            for row in rows:
                wf.write(json.dumps(row, ensure_ascii=False) + "\n")
        temp_out.replace(out)
        reload_index()
        return 0
    batch_size = 16
    try:
        with temp_out.open("w", encoding="utf-8") as wf:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                texts = [str(r.get("text") or r.get("section") or "")[:2000] for r in batch]
                vectors = embed_texts_sync(texts)
                if len(vectors) != len(batch):
                    print(f"embedding 批次 {i} 数量不匹配")
                    temp_out.unlink(missing_ok=True)
                    return 1
                for row, vec in zip(batch, vectors):
                    item = dict(row)
                    item["vector"] = vec
                    wf.write(json.dumps(item, ensure_ascii=False) + "\n")
                print(f"embedded {min(i + batch_size, len(rows))}/{len(rows)}")
        temp_out.replace(out)
    except Exception:
        temp_out.unlink(missing_ok=True)
        raise
    reload_index()
    print(f"写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
