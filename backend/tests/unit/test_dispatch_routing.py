"""LLM-first 路由：fast_path 白名单与 prompt 契约。"""

from services.ai_chat.prompts import build_agent_system_prompt


def test_agent_prompt_has_few_shot():
    p = build_agent_system_prompt("2026-05-29")
    assert "昨天生意咋样" in p
    assert "ask_clarification" in p or "澄清" in p
    assert "会话记忆" in p or "上下文" in p


def test_agent_prompt_includes_schema():
    p = build_agent_system_prompt("2026-05-29")
    assert "orders" in p
    assert "GMV" in p
