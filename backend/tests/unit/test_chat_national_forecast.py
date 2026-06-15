import asyncio
import sys
from unittest.mock import AsyncMock, patch

import pytest

if sys.version_info < (3, 10):
    pytest.skip("backend runtime is Python 3.11", allow_module_level=True)

from routers import chat as chat_router
from services.ai_chat import national_price as np_svc


def test_tool_national_forecast_delegates_to_service():
    payload = {
        "ok": True,
        "status": "ok",
        "type": "forecast",
        "source": "zgncpjgw_snapshot",
        "product": "大白菜",
        "future": [{"date": "2026-05-29", "yhat": 0.423, "confidence": 0.85, "trend": "flat"}],
        "model_version": "xgboost",
    }
    with patch(
        "services.ai_chat.national_price.forecast_for_query",
        AsyncMock(return_value=payload),
    ) as mock_forecast:
        result = asyncio.run(
            chat_router._tool_national_ag_forecast(
                AsyncMock(),
                {"query_text": "大白菜明天多少钱", "mode": "tomorrow", "days": 7, "target_offset": 1},
            )
        )

    mock_forecast.assert_awaited_once()
    assert result["ok"] is True
    assert result["source"] == "zgncpjgw_snapshot"
    assert result["future"][0]["yhat"] == 0.423


def test_direct_price_reply_future_card_uses_price_not_rank():
    tool_result = {
        "ok": True,
        "product": "大白菜",
        "mode": "future",
        "source": "zgncpjgw_live",
        "model_version": "zgncpjgw_anchored_live",
        "future": [
            {"date": "2026-05-29", "yhat": 0.423, "confidence": 0.85, "trend": "down"},
            {"date": "2026-05-30", "yhat": 0.418, "confidence": 0.83, "trend": "down"},
        ],
    }
    _, card, _ = chat_router._direct_price_reply(tool_result)
    assert card["type"] == "trend"
    assert card["rows"][0]["price"] == 0.423
    assert card["rows"][1]["price"] == 0.418
    assert "rank" not in card["rows"][0]
    assert any(c["key"] == "price" for c in card["columns"])


def test_parse_price_query_strips_yesterday_and_grade():
    pq = np_svc.parse_price_query("昨天大白菜（平头型）二级多少钱")
    assert pq.target_date is not None
    assert "昨天" not in pq.product_query
    assert "多少钱" not in pq.product_query
    assert "大白菜" in pq.product_query
    assert pq.grade_hint == "二级"
    assert pq.goods_name_hint == "大白菜"


def test_fast_historical_price_from_text():
    tool = chat_router._fast_historical_price_from_text("昨天大白菜（平头型）二级多少钱")
    assert tool is not None
    name, args = tool
    assert name == "get_national_ag_price"
    assert "大白菜" in args.get("product_query", "")
    assert args.get("target_date")


def test_direct_history_reply_single_day_kpi():
    reply, card, _ = chat_router._direct_history_reply({
        "ok": True,
        "product": "大白菜（平头型） 二级",
        "target_date": "2026-06-03",
        "price": 0.42,
        "rows": [],
    })
    assert "2026-06-03" in reply
    assert "0.420" in reply
    assert card["type"] == "kpi"
