"""地理坐标校验：拒绝空值、占位 (0,0) 及越界坐标。"""
from __future__ import annotations

import math
from typing import Any, Optional

from services.amap_geocode import geocode_address

_GEO_EPS = 1e-5


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def is_usable_geo_coord(lng: Any, lat: Any) -> bool:
    lng_f = _to_float(lng)
    lat_f = _to_float(lat)
    if lng_f is None or lat_f is None:
        return False
    if lng_f < -180 or lng_f > 180 or lat_f < -90 or lat_f > 90:
        return False
    if abs(lng_f) < _GEO_EPS and abs(lat_f) < _GEO_EPS:
        return False
    return True


def ensure_usable_geo_coord(lng: Any, lat: Any, *, field_label: str = "位置") -> tuple[float, float]:
    if not is_usable_geo_coord(lng, lat):
        raise ValueError(f"{field_label}无效，请从地址联想中选择带坐标的条目，或点击地图扎针定位")
    return float(_to_float(lng)), float(_to_float(lat))


async def resolve_locatable_address_coord(
    *,
    address: str,
    lng: Any = None,
    lat: Any = None,
    role_label: str = "地址",
) -> tuple[float, float]:
    """配送方/采购方/生产方/供货商等需落点的地址：优先用前端扎针，否则 geocode。"""
    addr = (address or "").strip()
    if not addr:
        raise ValueError(f"{role_label}不能为空")
    if lng is not None and lat is not None:
        return ensure_usable_geo_coord(lng, lat, field_label=role_label)
    coord = await geocode_address(addr)
    if coord and is_usable_geo_coord(coord[0], coord[1]):
        return float(coord[0]), float(coord[1])
    raise ValueError(f"{role_label}无法解析为有效坐标，请从联想列表选择或点击地图扎针")
