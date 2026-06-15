#!/usr/bin/env python3
"""从结构化 ai_chat 日志中抽取高频用户问法，辅助更新 06b-FAQ。

用法（每周或发版前）：
  grep 'ai_chat_turn' backend.log | python3 backend/scripts/ai_chat_faq_maintenance.py
  # 或 Docker：
  docker compose --profile dev logs backend-dev 2>&1 | python3 backend/scripts/ai_chat_faq_maintenance.py

输出 Top 问法预览；请人工审核后写入 docs/操作手册/11-常见问题.md，
再执行：python3 backend/scripts/index_docs_rag.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter


def main() -> int:
    counter: Counter[str] = Counter()
    for line in sys.stdin:
        if "ai_chat_turn" not in line:
            continue
        try:
            payload = json.loads(line.split("ai_chat_turn", 1)[-1].strip())
        except json.JSONDecodeError:
            try:
                payload = json.loads(line[line.index("{") :])
            except (ValueError, json.JSONDecodeError):
                continue
        preview = str(payload.get("user_preview") or "").strip()
        if preview:
            counter[preview] += 1
    if not counter:
        print("未从 stdin 解析到 ai_chat_turn 记录。", file=sys.stderr)
        return 1
    print("Top 问法（请人工合并进 06b-AI助手FAQ.md 后重建 RAG 索引）：\n")
    for text, n in counter.most_common(15):
        print(f"  [{n:4d}] {text}")
    print("\n下一步：编辑 docs/操作手册/11-常见问题.md → make docs-build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
