"""将 dazong/docs 操作手册切分并写入 JSONL 索引。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# 相对 dazong 项目根目录
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = _BACKEND_ROOT.parent
DOCS_ROOT = PROJECT_ROOT / "docs"

# 只允许索引现行操作手册。计划、迁移记录、宣传稿和运维过程记录不得进入 RAG。
# (相对 docs 的路径, audience, tier)
INDEX_SOURCES: list[tuple[str, str, str]] = [
    ("操作手册/00-系统总览.md", "all", "A"),
    ("操作手册/01-运营端.md", "operation", "A"),
    ("操作手册/02-采购方.md", "client", "A"),
    ("操作手册/03-供货方.md", "supplier", "A"),
    ("操作手册/04-配送商.md", "delivery", "A"),
    ("操作手册/05-工厂端.md", "factory", "A"),
    ("操作手册/06-监管驾驶舱.md", "monitor", "A"),
    ("操作手册/07-智能秤端.md", "client", "A"),
    ("操作手册/08-分检PDA.md", "delivery", "A"),
    ("操作手册/09-司机端.md", "delivery", "A"),
    ("操作手册/10-演示控制台.md", "monitor", "B"),
    ("操作手册/11-常见问题.md", "all", "A"),
]

HEADER_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
REVIEW_MARK = "⚠️"


@dataclass
class DocChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str
    audience: str
    tier: str
    confidence: str
    updated_at: str


def _doc_title_from_path(rel: str) -> str:
    name = Path(rel).stem
    return name.replace("-", " ").replace("_", " ")


def chunk_markdown(rel_path: str, audience: str, tier: str) -> list[DocChunk]:
    full = DOCS_ROOT / rel_path
    if not full.is_file():
        return []
    raw = full.read_text(encoding="utf-8")
    doc_id = rel_path.replace("/", "__")
    doc_title = _doc_title_from_path(rel_path)
    mtime = datetime.fromtimestamp(full.stat().st_mtime, tz=timezone.utc).isoformat()

    parts: list[tuple[str, str]] = []
    last = 0
    current_section = "概述"
    for match in HEADER_RE.finditer(raw):
        start = match.start()
        if start > last:
            body = raw[last:start].strip()
            if body:
                parts.append((current_section, body))
        current_section = match.group(2).strip()
        last = match.end()
    tail = raw[last:].strip()
    if tail:
        parts.append((current_section, tail))
    if not parts:
        parts.append(("全文", raw.strip()))

    chunks: list[DocChunk] = []
    for idx, (section, body) in enumerate(parts):
        if len(body) < 40:
            continue
        # 过长再按段落拆
        paras = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]
        buf = ""
        sub = 0
        for para in paras:
            if len(buf) + len(para) > 900 and buf:
                chunks.append(
                    DocChunk(
                        chunk_id=f"{doc_id}::{idx}::{sub}",
                        doc_id=doc_id,
                        doc_title=doc_title,
                        section=section,
                        text=buf.strip(),
                        audience=audience,
                        tier=tier,
                        confidence="review" if REVIEW_MARK in buf else "ok",
                        updated_at=mtime,
                    )
                )
                buf = para + "\n\n"
                sub += 1
            else:
                buf = (buf + "\n\n" + para).strip() if buf else para
        if buf.strip():
            chunks.append(
                DocChunk(
                    chunk_id=f"{doc_id}::{idx}::{sub}",
                    doc_id=doc_id,
                    doc_title=doc_title,
                    section=section,
                    text=buf.strip(),
                    audience=audience,
                    tier=tier,
                    confidence="review" if REVIEW_MARK in buf else "ok",
                    updated_at=mtime,
                )
            )
    return chunks


def build_index(output_path: Path) -> int:
    all_chunks: list[DocChunk] = []
    for rel, audience, tier in INDEX_SOURCES:
        all_chunks.extend(chunk_markdown(rel, audience, tier))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(asdict(ch), ensure_ascii=False) + "\n")
    return len(all_chunks)


def default_index_path() -> Path:
    return _BACKEND_ROOT / "data" / "rag" / "chunks.jsonl"
