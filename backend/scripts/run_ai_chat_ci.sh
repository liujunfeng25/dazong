#!/usr/bin/env bash
# 监管 AI 对话 CI：单测 + RAG 索引 +（可选）接口回归
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "== verify RAG index =="
python3 backend/scripts/verify_rag_index.py

echo "== unit tests (ai_chat) =="
cd "$ROOT"
if docker compose --profile dev ps backend-dev 2>/dev/null | grep -q Up; then
  docker compose --profile dev exec -T backend-dev python -m pytest \
    tests/unit/test_ai_chat_rag.py \
    tests/unit/test_chat_national_forecast.py \
    tests/unit/test_ai_chat_intent.py -q
else
  PYTHONPATH=backend python3 -m pytest \
    backend/tests/unit/test_ai_chat_rag.py \
    backend/tests/unit/test_chat_national_forecast.py \
    backend/tests/unit/test_ai_chat_intent.py -q 2>/dev/null || \
  PYTHONPATH=backend python3 -m pytest \
    backend/tests/unit/test_ai_chat_rag.py \
    backend/tests/unit/test_chat_national_forecast.py -q
fi

if [[ "${SKIP_CHAT_REGRESSION:-}" == "1" ]]; then
  echo "== skip chat regression (SKIP_CHAT_REGRESSION=1) =="
  exit 0
fi

echo "== chat API regression (requires backend+mysql) =="
if docker compose --profile dev ps backend-dev 2>/dev/null | grep -q Up; then
  docker compose --profile dev exec -T backend-dev python scripts/chat_quality_regression_dazong.py
else
  echo "backend-dev not running; set SKIP_CHAT_REGRESSION=1 or start: make dev-up"
  exit 1
fi
