import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("backend runtime is Python 3.11", allow_module_level=True)

from services.ai_chat.intent import classify_intent, has_analytics_side_request


def test_mixed_how_to_and_metrics_goes_analytics():
    text = "稽核链路怎么查，顺便看今天开放告警几条"
    assert has_analytics_side_request(text)
    assert classify_intent(text) == "analytics"


def test_pure_how_to():
    assert classify_intent("稽核链路怎么查") == "how_to"


def test_date_continuation_is_report():
    assert classify_intent("换成昨天呢") == "report"
    assert classify_intent("改今天呢") == "report"


def test_pie_is_analytics():
    assert classify_intent("今天一级分类饼图") == "analytics"


def test_colloquial_business_is_analytics():
    assert classify_intent("昨天生意咋样") == "analytics"


def test_potato_tomorrow_is_national_price():
    assert classify_intent("土豆明天多少钱") == "national_price"


def test_gmv_is_analytics_not_national_price():
    assert classify_intent("今天GMV多少") == "analytics"


def test_xinfadi_cabbage_is_national_price():
    assert classify_intent("新发地白菜明天多少钱") == "national_price"
