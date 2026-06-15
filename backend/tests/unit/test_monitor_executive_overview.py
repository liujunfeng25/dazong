from types import SimpleNamespace

from routers.monitor import (
    _canteen_ranking_rows,
    _executive_conclusion,
    _executive_period_days,
)


def test_executive_conclusion_is_stable_without_pending_risks():
    result = _executive_conclusion(
        pending_risks=0,
        high_risks=0,
        fulfillment_rate=98.5,
    )

    assert result["tone"] == "stable"
    assert result["status"] == "运行稳定"
    assert "未发现待处置风险" in result["text"]


def test_executive_conclusion_prioritizes_high_risk():
    result = _executive_conclusion(
        pending_risks=6,
        high_risks=1,
        fulfillment_rate=96.0,
        top_risk_label="配送超时",
    )

    assert result["tone"] == "risk"
    assert result["status"] == "重点关注"
    assert "6 项风险待处置" in result["text"]
    assert "配送超时" in result["text"]


def test_executive_conclusion_marks_low_fulfillment_as_risk():
    result = _executive_conclusion(
        pending_risks=0,
        high_risks=0,
        fulfillment_rate=72.0,
    )

    assert result["tone"] == "risk"


def test_executive_period_supports_only_seven_or_thirty_days():
    assert _executive_period_days(7) == 7
    assert _executive_period_days(14) == 7
    assert _executive_period_days(30) == 30


def test_canteen_ranking_keeps_unassigned_orders_and_sorts_by_gmv():
    stats = {
        12: {"orders": 2, "gmv": 240.0, "delivered": 2, "abnormal": 0},
        None: {"orders": 1, "gmv": 80.0, "delivered": 0, "abnormal": 1},
    }
    canteen_map = {
        12: SimpleNamespace(id=12, name="第一食堂", address="北京市朝阳区示例路 1 号")
    }

    rows = _canteen_ranking_rows(stats, canteen_map)

    assert rows[0] == {
        "canteen_id": 12,
        "name": "第一食堂",
        "address": "北京市朝阳区示例路 1 号",
        "orders": 2,
        "gmv": 240.0,
        "fulfillment_rate": 100.0,
        "abnormal_rate": 0.0,
        "risks": 0,
    }
    assert rows[1]["canteen_id"] is None
    assert rows[1]["name"] == "未指定食堂"
    assert rows[1]["orders"] == 1
    assert rows[1]["risks"] == 1
