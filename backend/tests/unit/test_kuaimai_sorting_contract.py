from datetime import date
import sys
from types import SimpleNamespace

import pytest

if sys.version_info < (3, 10):
    pytest.skip("backend runtime is Python 3.11; local python is too old for service imports", allow_module_level=True)

from routers.delivery_sort import _parse_allocation_id, _summary
from services.kuaimai_print import build_label_fields, build_render_data_array
from services.order_detail_aggregator import (
    amount_weighted_contract_float_rate,
    calc_order_float_rate,
)


def test_kuaimai_render_data_uses_foodlink_fields():
    row = build_label_fields(
        order=SimpleNamespace(
            order_no="OD130041274",
            expected_delivery_date=date(2026, 5, 20),
            expected_delivery_slot="05:00-06:00",
        ),
        alloc=SimpleNamespace(id=12847, line_no=1),
        product=SimpleNamespace(name="大白菜", spec="一级", unit="斤"),
        canteen_name="教师食堂",
        supplier_user=SimpleNamespace(company_name="某食品厂", username="supplier001"),
        print_time="2026-05-20 09:00:00",
    )

    assert row["product_name"] == "大白菜"
    assert row["spec_unit"] == "一级/斤"
    assert row["allocation_id"] == "12847"
    assert row["allocation_label"] == "OD130041274-A12847"
    assert row["expected_delivery_date"] == "2026-05-20"
    assert row["expected_delivery_slot"] == "05:00-06:00"
    assert row["canteen_name"] == "教师食堂"
    assert row["supplier_name"] == "某食品厂"

    render_data = build_render_data_array([row], bind_table="FoodLink", print_time="2026-05-20 09:01:00")
    assert list(render_data[0].keys()) == ["FoodLink"]
    assert render_data[0]["FoodLink"][0]["allocation_id"] == "12847"
    assert render_data[0]["FoodLink"][0]["print_time"] == "2026-05-20 09:01:00"


def test_delivery_sort_parse_allocation_id_accepts_label_variants():
    assert _parse_allocation_id("12847") == 12847
    assert _parse_allocation_id("DZALLOC:12847") == 12847
    assert _parse_allocation_id("ALLOC-12847") == 12847
    assert _parse_allocation_id("OD13004127487611-A12847") == 12847
    assert _parse_allocation_id("A12847") == 12847
    assert _parse_allocation_id("not-a-label") is None


def test_delivery_sort_summary_separates_pending_and_not_ready():
    summary = _summary(
        [
            {"sort_status": "已分检"},
            {"sort_status": "待分检"},
            {"sort_status": "未出库"},
            {"sort_status": "异常"},
        ]
    )

    assert summary["total"] == 4
    assert summary["sorted"] == 1
    assert summary["pending"] == 1
    assert summary["not_ready"] == 2
    assert summary["abnormal"] == 2


def test_order_float_rate_matches_realized_rate_when_using_reference_weights():
    order = SimpleNamespace(
        items_json=[
            {"product_id": 1, "quantity": 10, "unit_price": 12.2},
            {"product_id": 2, "quantity": 5, "unit_price": 26.0},
        ],
        items_snapshot_json=[
            {"product_id": 1, "category1_id": 10, "category_float_rate": 0.22},
            {"product_id": 2, "category1_id": 20, "category_float_rate": 0.30},
        ],
    )
    rate_map = {10: 0.22, 20: 0.30}

    weighted = amount_weighted_contract_float_rate(order, rate_map, 0)
    realized = calc_order_float_rate(order)

    assert weighted == realized
