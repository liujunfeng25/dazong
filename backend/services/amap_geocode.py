from __future__ import annotations

from typing import Optional

import httpx

from config import settings

_GEO_URL = "https://restapi.amap.com/v3/geocode/geo"
_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
_TIPS_URL = "https://restapi.amap.com/v3/assistant/inputtips"
_TIMEOUT = 5.0


async def geocode_address(address: str, city: Optional[str] = None) -> Optional[tuple[float, float]]:
    """
    使用高德地理编码解析地址，返回 (lng, lat)；失败返回 None。
    """
    addr = (address or "").strip()
    if not addr:
        return None
    key = (settings.amap_web_key or "").strip()
    if not key:
        return None

    params = {"key": key, "address": addr}
    if city and city.strip():
        params["city"] = city.strip()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_GEO_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
        if str(data.get("status")) != "1":
            return None
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return None
        location = str(geocodes[0].get("location") or "")
        parts = location.split(",")
        if len(parts) != 2:
            return None
        return float(parts[0]), float(parts[1])
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None


async def regeocode_lnglat(lng: float, lat: float) -> Optional[str]:
    """
    高德逆地理编码：经纬度 -> 结构化地址（formatted_address）；无 Key 或失败返回 None。
    """
    key = (settings.amap_web_key or "").strip()
    if not key:
        return None
    try:
        lng_f = float(lng)
        lat_f = float(lat)
    except (TypeError, ValueError):
        return None
    location = f"{lng_f},{lat_f}"
    params = {"key": key, "location": location}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_REGEO_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
        if str(data.get("status")) != "1":
            return None
        regeocode = data.get("regeocode") or {}
        formatted = str(regeocode.get("formatted_address") or "").strip()
        return formatted or None
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None


async def search_address_tips(
    keywords: str, city: Optional[str] = None, limit: int = 10
) -> list[dict]:
    """
    使用高德输入提示接口联想地址，返回标准化建议列表。
    """
    key = (settings.amap_web_key or "").strip()
    if not key:
        return []
    q = (keywords or "").strip()
    if not q:
        return []

    params = {"key": key, "keywords": q, "datatype": "all"}
    if city and city.strip():
        params["city"] = city.strip()
        params["citylimit"] = "true"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_TIPS_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
        if str(data.get("status")) != "1":
            return []
        tips = data.get("tips") or []
        results: list[dict] = []
        for tip in tips:
            location = str(tip.get("location") or "")
            lng = None
            lat = None
            if "," in location:
                pieces = location.split(",")
                if len(pieces) == 2:
                    try:
                        lng = float(pieces[0])
                        lat = float(pieces[1])
                    except (TypeError, ValueError):
                        lng = None
                        lat = None
            name = str(tip.get("name") or "").strip()
            address = str(tip.get("address") or "").strip()
            district = str(tip.get("district") or "").strip()
            display = " ".join([v for v in [name, district, address] if v])
            if not display:
                continue
            results.append(
                {
                    "name": name,
                    "district": district,
                    "address": address,
                    "display": display,
                    "location": location,
                    "lng": lng,
                    "lat": lat,
                }
            )
            if len(results) >= max(1, limit):
                break
        return results
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return []
