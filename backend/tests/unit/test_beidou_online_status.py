from datetime import datetime, timezone

from services.beidou_client import (
    beidou_device_activity_ms,
    beidou_latest_activity_ms,
    beidou_location_for_amap,
    beidou_online_status_from_raw,
    lng_lat_to_amap_gcj02,
)


def test_beidou_online_uses_device_heartbeat_not_server_time():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    stale = now_ms - 4 * 3600 * 1000
    fresh_server = now_ms - 60 * 1000
    raw = {"heart_time": stale, "server_time": fresh_server, "datetime": stale}
    assert beidou_device_activity_ms(raw) == stale
    assert beidou_latest_activity_ms(raw) == fresh_server
    assert beidou_online_status_from_raw(raw) == "offline"


def test_beidou_online_when_device_heartbeat_fresh():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    fresh = now_ms - 60 * 1000
    raw = {"heart_time": fresh, "server_time": now_ms - 4 * 3600 * 1000}
    assert beidou_online_status_from_raw(raw) == "online"


def test_beidou_offline_when_all_timestamps_stale():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    stale = now_ms - 4 * 3600 * 1000
    raw = {"heart_time": stale, "server_time": stale}
    assert beidou_online_status_from_raw(raw) == "offline"


def test_bd09_to_gcj02_shifts_coordinates():
    lng, lat = 116.28484225, 39.88638251
    glng, glat = lng_lat_to_amap_gcj02(lng, lat, "BAIDU")
    assert abs(glng - lng) > 0.001 or abs(glat - lat) > 0.001


def test_beidou_location_marks_stale_when_gps_old():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    stale = now_ms - 5 * 3600 * 1000
    raw = {
        "jingdu": 116.27844512,
        "weidu": 39.88002922,
        "heart_time": stale,
        "server_time": now_ms - 60 * 1000,
        "_gps18_map_type": "GAODE",
    }
    lng, lat, is_stale = beidou_location_for_amap(raw)
    assert lng is not None and lat is not None
    assert is_stale is True
