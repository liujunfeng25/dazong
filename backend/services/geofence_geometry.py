"""电子围栏几何：平面近似圆 → GeoJSON Polygon 外环。"""

from __future__ import annotations

import math
from typing import Any


def circle_polygon_geojson(center_lng: float, center_lat: float, radius_m: float, segments: int = 36) -> dict[str, Any]:
    ring = _circle_ring_coordinates(center_lng, center_lat, radius_m, segments)
    return {"type": "Polygon", "coordinates": [ring]}


def _circle_ring_coordinates(lng: float, lat: float, radius_m: float, segments: int) -> list[list[float]]:
    """闭合外环 [lng, lat]，首尾同点。"""
    r_earth = 6371000.0
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    d = radius_m / r_earth
    ring: list[list[float]] = []
    n = max(8, min(72, int(segments)))
    for i in range(n + 1):
        brng = 2 * math.pi * (i % n) / n
        lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brng))
        dlng = math.atan2(
            math.sin(brng) * math.sin(d) * math.cos(lat1),
            math.cos(d) - math.sin(lat1) * math.sin(lat2),
        )
        lng2 = lng1 + dlng
        ring.append([round(math.degrees(lng2), 6), round(math.degrees(lat2), 6)])
    return ring


def validate_polygon_geojson(geom: dict[str, Any] | None) -> tuple[bool, str]:
    if not geom or not isinstance(geom, dict):
        return False, "geometry_json 须为 GeoJSON 对象"
    if str(geom.get("type") or "") != "Polygon":
        return False, "禁行/分检区域须为 Polygon"
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return False, "Polygon.coordinates 无效"
    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < 4:
        return False, "多边形顶点至少 3 个（闭合环）"
    if ring[0] != ring[-1]:
        return False, "多边形须闭合（首尾坐标相同）"
    return True, ""
