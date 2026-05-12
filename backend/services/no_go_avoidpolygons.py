"""禁行多边形 → 高德 v3 驾车 avoidpolygons 参数，及分配阶段穿越/落点检测。"""

from __future__ import annotations

from typing import Any, Iterable, Optional

# 高德 Web 服务驾车路径规划 v3 限制
_MAX_POLYGONS = 32
_MAX_VERTICES_PER_RING = 16


def _ring_unique_vertices(ring: list) -> list[tuple[float, float]]:
    """GeoJSON 外环 → 去重闭合点后的顶点序列（至少 3 点）。"""
    out: list[tuple[float, float]] = []
    for p in ring:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            continue
        try:
            lng, lat = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            continue
        if out and abs(out[-1][0] - lng) < 1e-9 and abs(out[-1][1] - lat) < 1e-9:
            continue
        out.append((lng, lat))
    if len(out) >= 2 and out[0] == out[-1]:
        out = out[:-1]
    return out


def _decimate_vertices(pts: list[tuple[float, float]], max_n: int) -> list[tuple[float, float]]:
    if len(pts) <= max_n:
        return pts
    if max_n < 3:
        return pts[:max_n]
    idxs = [int(round(i * (len(pts) - 1) / (max_n - 1))) for i in range(max_n)]
    seen: set[int] = set()
    dec: list[tuple[float, float]] = []
    for i in idxs:
        if i in seen:
            continue
        seen.add(i)
        dec.append(pts[i])
    return dec if len(dec) >= 3 else pts[:max_n]


def _ring_to_avoid_segment(pts: list[tuple[float, float]]) -> str:
    """单区域：lng,lat;lng,lat;...（高德要求）。"""
    parts = [f"{lng:.6f},{lat:.6f}" for lng, lat in pts]
    return ";".join(parts)


def rings_for_leg_avoid_strict(
    rings: list[list[tuple[float, float]]],
    dest_lng: float,
    dest_lat: float,
) -> list[list[tuple[float, float]]]:
    """
    严格禁行：本段终点落在某环内时，该环本段不参与高德 avoid（否则无法规划到收货点）；
    其余环仍参与避让。
    """
    out: list[list[tuple[float, float]]] = []
    for ring in rings:
        if point_in_ring(float(dest_lng), float(dest_lat), ring):
            continue
        out.append(ring)
    return out


def rings_from_no_go_geofences(geofences: Iterable[Any]) -> list[list[tuple[float, float]]]:
    """
    从 ORM 行或 dict 解析禁行 Polygon 外环（平面经纬度），用于几何惩罚。
    仅 fence_type=no_go 且 is_active；geometry_json 须为 Polygon。
    """
    rings: list[list[tuple[float, float]]] = []
    for g in geofences:
        ft = getattr(g, "fence_type", None) or (g.get("fence_type") if isinstance(g, dict) else None)
        if str(ft or "") != "no_go":
            continue
        active = getattr(g, "is_active", True)
        if isinstance(g, dict):
            active = bool(g.get("is_active", True))
        if not active:
            continue
        geom = getattr(g, "geometry_json", None) or (g.get("geometry_json") if isinstance(g, dict) else None)
        if not isinstance(geom, dict) or str(geom.get("type") or "") != "Polygon":
            continue
        coords = geom.get("coordinates")
        if not isinstance(coords, list) or not coords:
            continue
        ring0 = coords[0]
        if not isinstance(ring0, list) or len(ring0) < 4:
            continue
        uv = _ring_unique_vertices(ring0)
        if len(uv) < 3:
            continue
        rings.append(uv)
    return rings


def build_avoidpolygons_param(
    rings: list[list[tuple[float, float]]],
) -> tuple[Optional[str], list[str]]:
    """
    将多组外环转为高德 avoidpolygons；超过 32 区或每区超过 16 顶点则截断/抽稀。
    返回 (参数字符串或 None, 人类可读告警文案列表)。
    """
    alerts: list[str] = []
    if not rings:
        return None, alerts
    use = rings[:_MAX_POLYGONS]
    if len(rings) > _MAX_POLYGONS:
        alerts.append(f"禁行区共 {len(rings)} 个，高德 avoidpolygons 仅取前 {_MAX_POLYGONS} 个参与避让")
    segs: list[str] = []
    for ri, ring in enumerate(use):
        dec = _decimate_vertices(ring, _MAX_VERTICES_PER_RING)
        if len(ring) > _MAX_VERTICES_PER_RING:
            alerts.append(f"禁行区第 {ri + 1} 个多边形顶点已抽稀至 {_MAX_VERTICES_PER_RING} 个")
        if len(dec) < 3:
            continue
        segs.append(_ring_to_avoid_segment(dec))
    if not segs:
        return None, alerts
    return "|".join(segs), alerts


def _ccw(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect_open(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    """线段 ab 与 cd 相交（CCW 判定）。"""

    def neq(x: bool, y: bool) -> bool:
        return x != y

    return neq(_ccw(a, c, d), _ccw(b, c, d)) and neq(_ccw(a, b, c), _ccw(a, b, d))


def segment_hits_ring(
    lng1: float,
    lat1: float,
    lng2: float,
    lat2: float,
    ring: list[tuple[float, float]],
) -> bool:
    """线段与多边形边界相交，或端点在多边形内（由内点射线处理）。"""
    a = (lng1, lat1)
    b = (lng2, lat2)
    n = len(ring)
    if n < 3:
        return False
    for i in range(n):
        c = ring[i]
        d = ring[(i + 1) % n]
        if _segments_intersect_open(a, b, c, d):
            return True
    return False


def point_in_ring(lng: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """射线法，ring 为不重复闭合前的顶点环。"""
    n = len(ring)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def no_go_penalty_for_leg(
    lng1: float,
    lat1: float,
    lng2: float,
    lat2: float,
    rings: list[list[tuple[float, float]]],
    *,
    base_cross: float = 50.0,
    inside_extra: float = 80.0,
) -> float:
    """
    车辆当前点 → 订单点的直线若穿过禁行区边界，或订单点落在禁行区内，则增加惩罚（与 km 同量纲叠加到 base_geo）。
    """
    pen = 0.0
    for ring in rings:
        if segment_hits_ring(lng1, lat1, lng2, lat2, ring):
            pen += base_cross
        if point_in_ring(lng2, lat2, ring):
            pen += inside_extra
    return pen
