import pytest

from services.zg_quality_verify import prices_changed, quality_action_status


@pytest.mark.parametrize(
    "before,after,expected",
    [
        ({"min_price": 3.5, "max_price": 37.3}, {"min_price": 3.5, "max_price": 37.3}, False),
        ({"min_price": 3.5, "max_price": 37.3}, {"min_price": 3.5, "max_price": 4.2}, True),
        ({"min_price": 10.0, "max_price": 20.0}, {"min_price": 10.05, "max_price": 20.0}, True),
        ({"min_price": 10.0, "max_price": 20.0}, {"min_price": 10.001, "max_price": 20.0}, False),
    ],
)
def test_prices_changed(before, after, expected):
    assert prices_changed(before, after) is expected


def test_quality_action_status_mapping():
    assert quality_action_status("isolate") == "quarantined"
    assert quality_action_status("restore") == "open"
    assert quality_action_status("correct") == "corrected"
    assert quality_action_status("confirm") is None
    assert quality_action_status("invalid") is None
