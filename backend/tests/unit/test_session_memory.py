from datetime import date, timedelta

from services.ai_chat.session_memory import (
    SessionMemory,
    apply_memory_entities,
    load_session,
    remember_turn_summary,
    resolve_relative_day,
    update_session_from_tool,
)


def test_session_memory_prompt():
    mem = SessionMemory(last_subject_name="中农食迅", last_subject_type="delivery", last_subject_id=3)
    text = mem.to_prompt()
    assert "中农食迅" in text
    assert "delivery#3" in text


def test_update_from_lookup():
    sid = "test-session-memory-1"
    update_session_from_tool(
        sid,
        "lookup_entity_by_name",
        {"name": "中农"},
        {"rows": [{"name": "中农食迅", "type": "delivery", "id": 9}]},
    )
    mem = load_session(sid)
    assert mem.last_subject_name == "中农食迅"
    assert mem.last_subject_id == 9


def test_apply_memory_entities():
    mem = SessionMemory(last_order_no="OD123456")
    entities = apply_memory_entities(mem, {"has_pronoun": True})
    assert entities["latest_order_no"] == "OD123456"


def test_apply_memory_entities_includes_subject_type():
    mem = SessionMemory(last_subject_name="中农食迅", last_subject_type="delivery", last_subject_id=9)
    entities = apply_memory_entities(mem, {})
    assert entities["session_subject_name"] == "中农食迅"
    assert entities["session_subject_type"] == "delivery"
    assert entities["session_subject_id"] == 9


def test_resolve_relative_day():
    today = date(2026, 5, 29)
    r = resolve_relative_day("换成昨天呢", today)
    assert r == ("2026-05-28", "2026-05-28")


def test_remember_turn_summary():
    sid = "test-session-memory-2"
    remember_turn_summary(sid, "问", "答" * 50)
    mem = load_session(sid)
    assert mem.turn_summaries
