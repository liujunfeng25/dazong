import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.periodic_quality_reports import (
    assert_provider_can_upload,
    period_days,
    periods_overlap,
    validate_period,
)
from services.quality_report_attachments import _object_key_from_public_url


class _ScalarSession:
    def __init__(self, values):
        self.values = list(values)

    async def scalar(self, _stmt):
        return self.values.pop(0)


def _product(*, designated=False, factory_id=None):
    return SimpleNamespace(
        id=10,
        is_designated_factory=designated,
        designated_factory_id=factory_id,
    )


def _user(*, user_id=2, role="supplier", status="active"):
    return SimpleNamespace(id=user_id, role=role, status=status)


def test_period_validation_accepts_366_days():
    start = date(2026, 1, 1)
    end = date(2027, 1, 1)
    assert period_days(start, end) == 366
    validate_period(start, end)


def test_period_validation_rejects_more_than_366_days():
    with pytest.raises(HTTPException) as err:
        validate_period(date(2026, 1, 1), date(2027, 1, 2))
    assert err.value.status_code == 400
    assert "366" in err.value.detail


def test_period_validation_rejects_reversed_dates():
    with pytest.raises(HTTPException) as err:
        validate_period(date(2026, 2, 1), date(2026, 1, 31))
    assert "结束日期" in err.value.detail


def test_period_overlap_allows_adjacent_ranges():
    assert periods_overlap(
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2026, 2, 1),
        date(2026, 2, 28),
    ) is False
    assert periods_overlap(
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2026, 1, 31),
        date(2026, 2, 28),
    ) is True


def test_supplier_requires_own_quote():
    db = _ScalarSession([_product(), None])
    with pytest.raises(HTTPException) as err:
        asyncio.run(assert_provider_can_upload(db, _user(), 10))
    assert err.value.status_code == 403
    assert "已报价" in err.value.detail


def test_supplier_with_quote_is_allowed():
    db = _ScalarSession([_product(), 99])
    result = asyncio.run(assert_provider_can_upload(db, _user(), 10))
    assert result.id == 10


def test_factory_must_match_designated_factory():
    db = _ScalarSession([_product(designated=True, factory_id=8)])
    with pytest.raises(HTTPException) as err:
        asyncio.run(
            assert_provider_can_upload(
                db,
                _user(user_id=9, role="factory"),
                10,
            )
        )
    assert err.value.status_code == 403


def test_minio_proxy_url_can_be_deleted():
    assert (
        _object_key_from_public_url(
            "/api/system/files/minio/quality/example%20report.pdf"
        )
        == "quality/example report.pdf"
    )
