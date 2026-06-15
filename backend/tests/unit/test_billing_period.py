from datetime import date, datetime
from types import SimpleNamespace

import pytest

from services.billing_service import compute_billing_period, summarize_overdue


def _cycle(cycle_type="monthly", close_day=1, confirm_due_days=3, payment_due_days=7):
    return SimpleNamespace(
        cycle_type=cycle_type,
        close_day=close_day,
        confirm_due_days=confirm_due_days,
        payment_due_days=payment_due_days,
    )


@pytest.mark.parametrize(
    "created,close_day,expected_label,expected_start,expected_end,expected_close",
    [
        # close_day=1: 4 月内的账单归 "2026-04" 账期
        (date(2026, 4, 15), 1, "2026-04", "2026-04-01", "2026-04-30", "2026-05-01"),
        (date(2026, 4, 1), 1, "2026-04", "2026-04-01", "2026-04-30", "2026-05-01"),
        (date(2026, 4, 30), 1, "2026-04", "2026-04-01", "2026-04-30", "2026-05-01"),
        # close_day=15: 4/15~5/14 归 "2026-05"
        (date(2026, 4, 10), 15, "2026-04", "2026-03-15", "2026-04-14", "2026-04-15"),
        (date(2026, 4, 14), 15, "2026-04", "2026-03-15", "2026-04-14", "2026-04-15"),
        (date(2026, 4, 15), 15, "2026-05", "2026-04-15", "2026-05-14", "2026-05-15"),
        (date(2026, 4, 20), 15, "2026-05", "2026-04-15", "2026-05-14", "2026-05-15"),
        # 跨年：12 月底 close_day=1 → next 是次年 1/1
        (date(2026, 12, 20), 1, "2026-12", "2026-12-01", "2026-12-31", "2027-01-01"),
        (date(2026, 1, 5), 15, "2026-01", "2025-12-15", "2026-01-14", "2026-01-15"),
    ],
)
def test_compute_billing_period_monthly(
    created, close_day, expected_label, expected_start, expected_end, expected_close
):
    cycle = _cycle("monthly", close_day=close_day, confirm_due_days=3, payment_due_days=10)
    period = compute_billing_period(created, cycle)
    assert period["period_label"] == expected_label
    assert period["period_start"] == expected_start
    assert period["period_end"] == expected_end
    assert period["close_at"] == expected_close
    # 到期日 = close_at + N
    close_dt = date.fromisoformat(expected_close)
    assert (date.fromisoformat(period["confirm_due_date"]) - close_dt).days == 3
    assert (date.fromisoformat(period["payment_due_date"]) - close_dt).days == 10


def test_compute_billing_period_daily():
    cycle = _cycle("daily", close_day=1, confirm_due_days=1, payment_due_days=3)
    period = compute_billing_period(date(2026, 5, 18), cycle)
    assert period["period_label"] == "2026-05-18"
    assert period["period_start"] == "2026-05-18"
    assert period["period_end"] == "2026-05-18"
    assert period["close_at"] == "2026-05-18"
    assert period["confirm_due_date"] == "2026-05-19"
    assert period["payment_due_date"] == "2026-05-21"


def test_compute_billing_period_weekly():
    # 2026-05-18 是周一 (isoweekday=1)；close_day=5 表示周五关账
    cycle = _cycle("weekly", close_day=5, confirm_due_days=0, payment_due_days=7)
    period = compute_billing_period(date(2026, 5, 18), cycle)
    # 下次关账：2026-05-22（周五）
    assert period["close_at"] == "2026-05-22"
    assert period["period_end"] == "2026-05-21"
    assert period["period_start"] == "2026-05-15"
    assert period["confirm_due_date"] == "2026-05-22"
    assert period["payment_due_date"] == "2026-05-29"


def test_compute_billing_period_accepts_datetime():
    cycle = _cycle("monthly", close_day=1)
    period = compute_billing_period(datetime(2026, 4, 15, 10, 30, 0), cycle)
    assert period["period_label"] == "2026-04"
    assert period["close_at"] == "2026-05-01"


def test_compute_billing_period_close_day_clamped_to_28():
    """配置 close_day=31 时按 28 处理，避免 2 月歧义。"""
    cycle = _cycle("monthly", close_day=31)
    period = compute_billing_period(date(2026, 2, 10), cycle)
    assert period["close_at"] == "2026-02-28"
    assert period["period_end"] == "2026-02-27"


def _enriched(status, confirm_due, payment_due, **extra):
    return {
        "status": status,
        "confirm_due_date": confirm_due,
        "payment_due_date": payment_due,
        **extra,
    }


def test_summarize_overdue_buckets_into_two_lists():
    today = date(2026, 5, 18)
    items = [
        # 已过确认到期，状态待确认 → 进入 overdue_confirm
        _enriched("待确认", "2026-05-10", "2026-05-20", id=1),
        # 已过付款到期，状态已确认 → 进入 overdue_payment
        _enriched("已确认", "2026-05-01", "2026-05-10", id=2),
        # 已结清，跳过
        _enriched("已结清", "2026-04-01", "2026-04-10", id=3),
        # 未到期
        _enriched("待确认", "2026-05-20", "2026-05-30", id=4),
        # 部分结清且过期，进入 overdue_payment
        _enriched("部分结清", "2026-05-01", "2026-05-10", id=5),
    ]
    result = summarize_overdue(items, today)
    confirm_ids = sorted(it["id"] for it in result["overdue_confirm"])
    payment_ids = sorted(it["id"] for it in result["overdue_payment"])
    assert confirm_ids == [1]
    assert payment_ids == [2, 5]
    # overdue_days 计算正确
    assert result["overdue_confirm"][0]["overdue_days"] == 8
    assert result["overdue_payment"][0]["overdue_days"] == 8
