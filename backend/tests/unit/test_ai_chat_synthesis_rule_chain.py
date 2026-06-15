from datetime import date

import pytest

from services.ai_chat.rule_chain import _pick_initial_tool
from services.ai_chat.synthesis import build_synthesis_messages, should_synthesize


def test_should_synthesize_skips_single_simple_tool():
    assert not should_synthesize(
        tool_calls_debug=[{"name": "get_kpi_summary", "result_preview": "ok"}],
        final_tool_result={"type": "table", "summary": "3 单"},
        reply="昨天共 3 单。",
        min_tools=2,
    )


def test_should_synthesize_for_report():
    assert should_synthesize(
        tool_calls_debug=[{"name": "generate_report", "result_preview": "ok"}],
        final_tool_result={"type": "report", "summary": "日报"},
        reply="已生成日报。",
        min_tools=2,
    )


def test_should_synthesize_when_reply_empty():
    assert should_synthesize(
        tool_calls_debug=[{"name": "get_kpi_summary", "result_preview": "ok"}],
        final_tool_result={"type": "table", "summary": "3 单"},
        reply="",
        min_tools=2,
    )


def test_should_synthesize_multi_tool():
    debug = [
        {"name": "lookup_entity_by_name", "result_preview": "a"},
        {"name": "get_delivery_metrics", "result_preview": "b"},
    ]
    assert should_synthesize(
        tool_calls_debug=debug,
        final_tool_result={"type": "table", "summary": "ok"},
        reply="综合回复",
        min_tools=2,
    )


def test_build_synthesis_messages_includes_citations_and_intent():
    msgs = build_synthesis_messages(
        "稽核链路怎么查",
        tool_summaries=["[search_docs] 命中 2 条"],
        intent="how_to",
        citations=[{"doc": "06-监管驾驶舱", "section": "6.10"}],
    )
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    assert "操作手册类" in system
    assert "06-监管驾驶舱" in user
    assert "参考来源" in user


def _noop_heuristic(text: str, entities=None):
    return "get_kpi_summary", {"scope": "today"}


def test_pick_initial_tool_routes_how_to():
    name, args = _pick_initial_tool("稽核链路怎么查", {}, _noop_heuristic)
    assert name == "search_docs"
    assert "稽核" in args["query"]


def test_pick_initial_tool_routes_report_with_yesterday():
    def apply_days(text, gen_args):
        gen_args = dict(gen_args)
        gen_args["start_date"] = "2026-05-28"
        gen_args["end_date"] = "2026-05-28"
        return gen_args

    name, args = _pick_initial_tool(
        "给我整一份昨天的监管日报",
        {},
        _noop_heuristic,
        apply_report_day_range=apply_days,
    )
    assert name == "generate_report"
    assert args["report_type"] == "daily"
    assert args["start_date"] == "2026-05-28"


def test_pick_initial_tool_mixed_analytics_not_pure_how_to():
    name, _ = _pick_initial_tool("稽核链路怎么查，顺便看今天开放告警几条", {}, _noop_heuristic)
    assert name == "get_kpi_summary"


def test_pick_initial_tool_mixed_prepends_docs_chain():
    """混合问法在 rule 链中应先手册后查数（由 run_rule_chain 预置 search_docs）。"""
    from services.ai_chat.rule_chain import _mixed_how_to_and_analytics, _analytics_companion_tool

    text = "演示账号是啥，顺便看今天GMV"
    assert _mixed_how_to_and_analytics(text)
    name, _ = _analytics_companion_tool(text, _noop_heuristic, {})
    assert name == "get_kpi_summary"


def test_pick_initial_tool_date_continuation_with_subject():
    name, args = _pick_initial_tool(
        "换成昨天呢",
        {"session_subject_name": "中农食迅"},
        _noop_heuristic,
        today=date(2026, 5, 29),
    )
    assert name == "generate_report"
    assert args["subject_name"] == "中农食迅"
    assert args["start_date"] == "2026-05-28"
    assert args["end_date"] == "2026-05-28"


def test_count_mixed_sub_intents():
    from services.ai_chat.synthesis import count_mixed_sub_intents, expects_explicit_count, needs_completeness_retry

    assert count_mixed_sub_intents("稽核怎么查，顺便看今天告警几条") >= 2
    assert expects_explicit_count("今天开放告警有几条")
    assert needs_completeness_retry(
        "稽核怎么查，顺便看今天告警几条",
        "请从侧栏进入稽核模块。",
        [{"name": "search_docs", "arguments": {}}],
    )


def test_build_synthesis_includes_date_anchor():
    from services.ai_chat.synthesis import build_synthesis_messages

    msgs = build_synthesis_messages(
        "换成昨天呢",
        tool_summaries=["[generate_report] ok"],
        tool_calls_debug=[{"name": "generate_report", "arguments": {"start_date": "2026-05-28", "end_date": "2026-05-28"}}],
    )
    assert "2026-05-28" in msgs[1]["content"]
