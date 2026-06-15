"""DashScope 文本 embedding（操作手册 hybrid RAG）。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger("dazong.ai_chat.rag")


async def embed_texts(texts: list[str]) -> list[list[float]]:
    api_key = (settings.ai_api_key or "").strip()
    if not api_key or not texts:
        return []
    url = f"{(settings.ai_base_url or '').rstrip('/')}/embeddings"
    payload = {
        "model": settings.rag_embedding_model,
        "input": texts,
        "dimensions": int(settings.rag_embedding_dimensions),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0), trust_env=False) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    items = sorted(data.get("data") or [], key=lambda x: int(x.get("index") or 0))
    return [list(item.get("embedding") or []) for item in items]


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(embed_texts(texts))
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(embed_texts(texts))).result()
