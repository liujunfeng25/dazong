from services.zg_data_quality import format_forecast_sample_hint


def test_dirty_sku_with_raw_days_hint():
    hint = format_forecast_sample_hint(
        eligible_days=0,
        raw_days=12,
        scope_label="福建口径",
        flag_status="open",
        flag_severity="high",
    )
    assert "疑似脏数据" in hint
    assert "热力地图" in hint
    assert "0 天" in hint


def test_no_hint_when_eligible_days_positive():
    assert format_forecast_sample_hint(eligible_days=5, raw_days=5) == ""


def test_sparse_province_without_flag():
    hint = format_forecast_sample_hint(eligible_days=0, raw_days=0, scope_label="福建口径")
    assert "暂无" in hint
    assert "全国" in hint
