"""高德驾车路径规划（REST v3），用于路段距离、时长与折线坐标。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from config import settings

_DRIVING_URL = "https://restapi.amap.com/v3/direction/driving"
_TIMEOUT = 8.0


@dataclass
class DrivingLegResult:
    distance_m: float
    duration_s: float
    points: list[tuple[float, float]]  # (lng, lat)


def _parse_polyline(poly: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    if not poly or not poly.strip():
        return out
    for pair in poly.strip().split(";"):
        parts = pair.split(",")
        if len(parts) != 2:
            continue
        try:
            lng, lat = float(parts[0]), float(parts[1])
        except (TypeError, ValueError):
            continue
        if out and abs(out[-1][0] - lng) < 1e-7 and abs(out[-1][1] - lat) < 1e-7:
            continue
        out.append((lng, lat))
    return out


async def _fetch_driving_leg_raw(
    origin_lng: float,
    origin_lat: float,
    dest_lng: float,
    dest_lat: float,
    *,
    avoidpolygons: Optional[str] = None,
) -> Optional[DrivingLegResult]:
    key = (settings.amap_web_key or "").strip()
    if not key:
        return None
    o_lng, o_lat, d_lng, d_lat = map(float, (origin_lng, origin_lat, dest_lng, dest_lat))
    params: dict[str, str] = {
        "key": key,
        "origin": f"{o_lng},{o_lat}",
        "destination": f"{d_lng},{d_lat}",
        "extensions": "all",
        "strategy": "0",  # 速度优先（默认）
    }
    if avoidpolygons and avoidpolygons.strip():
        params["avoidpolygons"] = avoidpolygons.strip()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_DRIVING_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return None

    if str(data.get("status")) != "1":
        return None
    route_obj = data.get("route") or {}
    paths = route_obj.get("paths") or []
    if not paths:
        return None
    path0 = paths[0] if isinstance(paths[0], dict) else {}
    try:
        distance_m = float(path0.get("distance") or 0)
        duration_s = float(path0.get("duration") or 0)
    except (TypeError, ValueError):
        return None
    if distance_m <= 0 or duration_s <= 0:
        return None

    points: list[tuple[float, float]] = []
    steps = path0.get("steps") or []
    for step in steps:
        if not isinstance(step, dict):
            continue
        poly = str(step.get("polyline") or "")
        seg = _parse_polyline(poly)
        if points and seg and points[-1] == seg[0]:
            seg = seg[1:]
        points.extend(seg)

    if len(points) < 2:
        points = [(o_lng, o_lat), (d_lng, d_lat)]

    return DrivingLegResult(distance_m=distance_m, duration_s=duration_s, points=points)


async def fetch_driving_leg(
    origin_lng: float,
    origin_lat: float,
    dest_lng: float,
    dest_lat: float,
    *,
    avoidpolygons: Optional[str] = None,
    retry_without_avoid: bool = True,
) -> tuple[Optional[DrivingLegResult], bool]:
    """
    请求 A→B 驾车路径。成功返回 (结果, used_avoid)；失败 (None, False)。
    若传入 avoidpolygons 且首请求失败，可选重试一次不带避让（retry_without_avoid=True）。
    """
    if avoidpolygons and avoidpolygons.strip():
        res = await _fetch_driving_leg_raw(
            origin_lng, origin_lat, dest_lng, dest_lat, avoidpolygons=avoidpolygons
        )
        if res is not None:
            return res, True
        if retry_without_avoid:
            res2 = await _fetch_driving_leg_raw(origin_lng, origin_lat, dest_lng, dest_lat, avoidpolygons=None)
            return res2, False
        return None, False
    res = await _fetch_driving_leg_raw(origin_lng, origin_lat, dest_lng, dest_lat, avoidpolygons=None)
    return res, False


def merge_leg_polylines(legs: list[DrivingLegResult]) -> list[list[float]]:
    """将多段 leg 的 points 合并为 [[lng,lat], ...]。"""
    merged: list[list[float]] = []
    for leg in legs:
        for lng, lat in leg.points:
            if merged and abs(merged[-1][0] - lng) < 1e-7 and abs(merged[-1][1] - lat) < 1e-7:
                continue
            merged.append([lng, lat])
    return merged
