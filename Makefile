.PHONY: dev-up dev-down dev-logs dev-restart-backend prod-up prod-down prod-build
.PHONY: ai-chat-index ai-chat-verify ai-chat-unit ai-chat-regression ai-chat-ci
.PHONY: docs-build docs-check docs-docx docs-rag

COMPOSE_DEV := docker compose --profile dev
COMPOSE_PROD := docker compose --profile prod
PYTHON ?= python3

dev-up:
	$(COMPOSE_DEV) up -d

dev-down:
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f --tail=100

dev-restart-backend:
	$(COMPOSE_DEV) restart backend

prod-build:
	$(COMPOSE_PROD) build

prod-up:
	$(COMPOSE_PROD) up -d --build

prod-down:
	$(COMPOSE_PROD) down

# --- 监管 AI 对话质量门禁 ---
ai-chat-index:
	python3 backend/scripts/index_docs_rag.py
	python3 backend/scripts/index_docs_rag_embeddings.py
	python3 backend/scripts/verify_rag_index.py

ai-chat-verify:
	python3 backend/scripts/verify_rag_index.py

ai-chat-unit:
	PYTHONPATH=backend python3 -m pytest \
		backend/tests/unit/test_ai_chat_rag.py \
		backend/tests/unit/test_chat_xinfadi_live_forecast.py \
		backend/tests/unit/test_ai_chat_intent.py \
		backend/tests/unit/test_tool_payload_compact.py \
		backend/tests/unit/test_session_memory.py \
		backend/tests/unit/test_session_memory_seed.py \
		backend/tests/unit/test_hybrid_rag.py \
		backend/tests/unit/test_dispatch_routing.py \
		backend/tests/unit/test_ai_chat_synthesis_rule_chain.py \
		backend/tests/unit/test_heuristic_routing.py -q

ai-chat-regression:
	$(COMPOSE_DEV) exec -T backend-dev python scripts/chat_quality_regression_dazong.py

ai-chat-ci:
	bash backend/scripts/run_ai_chat_ci.sh

# --- 文档：Markdown 是事实源，DOCX 与 RAG 是生成物 ---
docs-docx:
	$(PYTHON) scripts/generate_system_docx.py

docs-rag:
	$(PYTHON) backend/scripts/index_docs_rag.py

docs-build: docs-docx docs-rag

docs-check:
	$(PYTHON) scripts/check_docs_consistency.py
