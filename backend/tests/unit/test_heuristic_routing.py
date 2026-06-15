"""口语化/多轮启发式路由（无 DB）。"""

import os
import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("backend runtime is Python 3.11", allow_module_level=True)

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from routers.chat import (  # noqa: E402
    _apply_day_range_to_report_args,
    _extract_subject_name,
    _heuristic_tool,
)


def test_yesterday_business_routes_kpi():
    tool, args = _heuristic_tool("昨天生意咋样", {})
    assert tool == "get_kpi_summary"
    assert args["scope"] == "range"
    assert args["start_date"] == args["end_date"]


def test_report_subject_not_whole_verb():
    assert _extract_subject_name("给我整一份昨天的监管日报") is None
    tool, args = _heuristic_tool("给我整一份昨天的监管日报", {})
    assert tool == "generate_report"
    assert "subject_name" not in args or args.get("subject_name") not in ("整", "整份")
    args = _apply_day_range_to_report_args("给我整一份昨天的监管日报", {"report_type": "daily"})
    assert args.get("start_date") == args.get("end_date")


def test_vague_orders_default_today():
    tool, args = _heuristic_tool("查一下订单", {})
    assert tool in ("search_orders", "get_today_orders")
    if tool == "search_orders":
        assert args.get("start_date") == args.get("end_date")


def test_session_subject_pronoun_lookup():
    tool, args = _heuristic_tool(
        "那边配送商最近咋样",
        {"session_subject_name": "中农食迅", "session_subject_type": "delivery"},
    )
    assert tool == "lookup_entity_by_name"
    assert args["name"] == "中农食迅"


def test_audit_link_search_docs():
    tool, args = _heuristic_tool("链路在哪查", {})
    assert tool == "search_docs"
    assert "链路" in args["query"]
