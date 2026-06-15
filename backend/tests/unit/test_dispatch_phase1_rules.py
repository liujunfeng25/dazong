from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[2]))

from routers.delivery_dispatch import (
    _build_route_numbers,
    _collect_commit_order_ids,
    _register_commit_vehicle,
    _validate_order_planning_date,
    _validate_trip_action_status,
)
from services.dispatch_trip_edit import validate_stop_removal


@pytest.mark.parametrize("status", ["已完成", "已取消"])
@pytest.mark.parametrize("action", ["发车", "异常发车", "取消"])
def test_terminal_trip_rejects_further_actions(status, action):
    with pytest.raises(HTTPException) as err:
        _validate_trip_action_status(status, action)
    assert err.value.status_code == 400
    assert f"不能{action}" in err.value.detail


@pytest.mark.parametrize("status", ["待发车", "有阻塞"])
def test_editable_trip_allows_pre_departure_actions(status):
    _validate_trip_action_status(status, "发车")


def test_commit_rejects_duplicate_order_across_routes():
    routes = [
        {"stops": [{"order_id": 101}]},
        {"stops": [{"order_id": 101}]},
    ]
    with pytest.raises(HTTPException) as err:
        _collect_commit_order_ids(routes)
    assert err.value.status_code == 400
    assert "重复出现" in err.value.detail


def test_commit_rejects_duplicate_vehicle():
    used = set()
    _register_commit_vehicle(used, 7, "京A10001")
    with pytest.raises(HTTPException) as err:
        _register_commit_vehicle(used, 7, "京A10001")
    assert err.value.status_code == 400
    assert "重复使用" in err.value.detail


def test_commit_rejects_order_from_another_planning_date():
    order = SimpleNamespace(order_no="ORD-1", expected_delivery_date=date(2026, 6, 11))
    with pytest.raises(HTTPException) as err:
        _validate_order_planning_date(order, date(2026, 6, 10))
    assert err.value.status_code == 400
    assert "与计划日 2026-06-10 不一致" in err.value.detail


def test_route_number_uses_highest_existing_sequence():
    result = _build_route_numbers(
        ["TR20260610-01", "TR20260610-03", "TR20260610-03-D99", "OTHER"],
        date(2026, 6, 10),
        2,
    )
    assert result == ["TR20260610-04", "TR20260610-05"]


def test_cannot_remove_last_trip_stop():
    with pytest.raises(ValueError, match="至少一个站点"):
        validate_stop_removal([101], [101])


def test_can_remove_some_trip_stops():
    assert validate_stop_removal([101, 102], [102]) == {102}
