from datetime import date
from types import SimpleNamespace

from services.zg_data_quality import (
    detect_quality_flags,
    normalize_quality_policy,
    quality_weight,
    should_exclude_quality,
)


def _row(province: str, price: str):
    return SimpleNamespace(
        goods_name="测试菜",
        spec="一级",
        unit="斤",
        cate_id=1,
        cate_name="蔬菜",
        scate_name="叶菜",
        district_name=province,
        price=price,
    )


def test_flags_only_outlier_province_high():
    # 各省中位价的中位数 M=1.2；广东 6.1/1.2=5.08>5 → 只标广东 high，其余省不标
    flags = detect_quality_flags(
        [_row("北京", "1"), _row("河北", "1.2"), _row("广东", "6.1")],
        date(2026, 6, 7),
    )
    assert len(flags) == 1
    assert flags[0]["severity"] == "high"
    assert flags[0]["district_name"] == "广东"
    assert '"cross_median"' in flags[0]["evidence_json"]


def test_flags_medium_outlier_province_and_half_weight():
    # M=1；广东 3.2/1=3.2>3 → 该省 medium
    flags = detect_quality_flags(
        [_row("北京", "1"), _row("河北", "1"), _row("广东", "3.2")],
        date(2026, 6, 7),
    )
    assert len(flags) == 1
    assert flags[0]["severity"] == "medium"
    assert flags[0]["district_name"] == "广东"
    assert quality_weight({"quality_level": "medium"}) == 0.5


def test_extreme_low_among_many_flags_only_that_province():
    # 仿真实 05-24：9 省里湖北 4.75 离谱，中位数 78，只标湖北 high
    rows = [
        _row("湖北", "4.75"), _row("上海", "70"), _row("江苏", "70"), _row("安徽", "75"),
        _row("天津", "78.06"), _row("河南", "80"), _row("河北", "80.55"), _row("北京", "83"),
        _row("湖南", "95"),
    ]
    flags = detect_quality_flags(rows, date(2026, 5, 24))
    assert len(flags) == 1
    assert flags[0]["district_name"] == "湖北"
    assert flags[0]["severity"] == "high"


def test_two_province_moderate_no_flag():
    # 只有 2 省、3.5 倍中等差异 → 说不清谁错，不误判
    flags = detect_quality_flags([_row("北京", "1"), _row("河北", "3.5")], date(2026, 6, 7))
    assert flags == []


def test_two_province_extreme_flags_low_one():
    # 2 省极端（4.75 vs 70，M=37.4）→ 标低价省 high
    flags = detect_quality_flags([_row("湖北", "4.75"), _row("上海", "70")], date(2026, 6, 7))
    assert len(flags) == 1
    assert flags[0]["district_name"] == "湖北"
    assert flags[0]["severity"] == "high"


def test_single_province_no_flag():
    flags = detect_quality_flags([_row("北京", "5")], date(2026, 6, 7))
    assert flags == []


def test_quality_policy_and_human_review_precedence():
    high = {"quality_level": "high", "statuses": ["open"]}
    quarantined = {"quality_level": "high", "statuses": ["quarantined"]}
    confirmed = {"quality_level": "high", "statuses": ["confirmed_valid"]}
    assert should_exclude_quality(high, "strict")
    assert not should_exclude_quality(high, "warn")
    assert should_exclude_quality(quarantined, "warn")
    assert not should_exclude_quality(confirmed, "strict")
    assert normalize_quality_policy("invalid") == "strict"
