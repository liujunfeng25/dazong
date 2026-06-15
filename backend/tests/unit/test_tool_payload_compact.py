from services.ai_chat.tool_payload import compact_tool_result_for_llm


def test_compact_truncates_rows():
    rows = [{"id": i, "name": f"n{i}"} for i in range(50)]
    out = compact_tool_result_for_llm({"type": "table", "summary": "ok", "rows": rows})
    assert len(out["rows"]) == 20
    assert out.get("rows_truncated") is True
    assert out.get("row_count") == 50


def test_compact_clarify():
    out = compact_tool_result_for_llm({"type": "clarify", "question": "请说明时间范围？"})
    assert out.get("question") == "请说明时间范围？"
