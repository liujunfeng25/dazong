from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from config import settings


def _to_tail_digit(val: Any) -> int | None:
    text = str(val or "").strip().upper()
    if not text:
        return None
    if text.isdigit():
        return int(text) % 10
    if len(text) == 1 and "A" <= text <= "Z":
        return 0
    return None


def _parse_digits(raw_items: list[Any]) -> list[int]:
    out: list[int] = []
    for item in raw_items:
        if isinstance(item, (list, tuple)):
            for x in item:
                d = _to_tail_digit(x)
                if d is not None and d not in out:
                    out.append(d)
        else:
            d = _to_tail_digit(item)
            if d is not None and d not in out:
                out.append(d)
    return out


def _extract_restriction_for_date(
    first: dict[str, Any],
    want: date,
    today_sh: date,
) -> tuple[list[int], str, str, str] | None:
    """
    从心知 driving_restriction 单条 result 中解析指定自然日 want 的尾号限行。
    返回 (digits, date_text, summary, limit_time)；无法匹配该日时返回 None。
    """
    want_iso = want.isoformat()
    restriction_obj = first.get("restriction") if isinstance(first.get("restriction"), dict) else {}
    limits = restriction_obj.get("limits") if isinstance(restriction_obj.get("limits"), list) else []
    for it in limits:
        if not isinstance(it, dict):
            continue
        if str(it.get("date") or "").strip() != want_iso:
            continue
        digits = _parse_digits([it.get("plates"), it.get("numbers"), it.get("tail_number")])
        summary = str(it.get("memo") or "").strip()
        limit_t = str(restriction_obj.get("time") or "").strip()
        date_text = str(it.get("date") or want_iso).strip() or want_iso
        return digits, date_text, summary, limit_t

    restrictions = first.get("driving_restriction")
    if isinstance(restrictions, list) and restrictions:
        for item in restrictions:
            if not isinstance(item, dict):
                continue
            d = str(item.get("date") or "").strip()
            if d and d != want_iso:
                continue
            if not d and want != today_sh:
                continue
            digits = _parse_digits(
                [
                    item.get("numbers"),
                    item.get("tail_number"),
                    item.get("limit_numbers"),
                    item.get("number"),
                ]
            )
            summary = str(item.get("brief") or item.get("description") or item.get("content") or "").strip()
            limit_t = str(item.get("restriction") or item.get("status") or "").strip()
            date_text = d or want_iso
            return digits, date_text, summary, limit_t
    return None


async def fetch_beijing_driving_restriction(*, target_date: date | None = None) -> dict[str, Any]:
    sh_tz = ZoneInfo("Asia/Shanghai")
    today_sh = datetime.now(sh_tz).date()
    want = target_date if target_date is not None else today_sh

    key = (settings.seniverse_api_key or "").strip()
    if not key:
        return {
            "source": "seniverse",
            "available": False,
            "message": "未配置实时限号 API Key（SENIVERSE_API_KEY）",
            "city": "北京",
            "date": want.isoformat(),
            "digits": [],
            "raw_text": "",
        }

    if want < today_sh:
        return {
            "source": "seniverse",
            "available": False,
            "message": f"限行预报接口不支持早于今日（{today_sh.isoformat()}）的历史日期：{want.isoformat()}",
            "city": "北京",
            "date": want.isoformat(),
            "digits": [],
            "raw_text": "",
        }

    offset = (want - today_sh).days
    days_req = min(15, max(1, offset + 1))

    url = "https://api.seniverse.com/v3/life/driving_restriction.json"
    params = {
        "key": key,
        "location": "beijing",
        "language": "zh-Hans",
        "start": 0,
        "days": days_req,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json() if resp.content else {}

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        raise ValueError("实时限号接口返回为空")

    first = results[0] if isinstance(results[0], dict) else {}
    location = first.get("location") if isinstance(first.get("location"), dict) else {}

    picked = _extract_restriction_for_date(first, want, today_sh)
    if picked is None:
        return {
            "source": "seniverse",
            "available": False,
            "message": (
                f"接口返回中未找到 {want.isoformat()} 的尾号限行条目（已请求连续 {days_req} 天预报，"
                "可能超出可预报范围或接口结构变更）"
            ),
            "city": str(location.get("name") or "北京"),
            "date": want.isoformat(),
            "digits": [],
            "raw_text": "",
        }

    digits, date_text, summary, limit_t = picked
    return {
        "source": "seniverse",
        "available": True,
        "message": "",
        "city": str(location.get("name") or "北京"),
        "date": date_text,
        "digits": digits,
        "raw_text": "；".join([x for x in [summary, limit_t] if x]),
    }


async def fetch_beijing_weather_now() -> dict[str, Any]:
    key = (settings.seniverse_api_key or "").strip()
    if not key:
        return {
            "source": "seniverse",
            "available": False,
            "message": "未配置实时天气 API Key（SENIVERSE_API_KEY）",
            "city": "北京",
            "text": "",
            "temperature": "",
            "last_update": "",
        }

    url = "https://api.seniverse.com/v3/weather/now.json"
    params = {
        "key": key,
        "location": "beijing",
        "language": "zh-Hans",
        "unit": "c",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json() if resp.content else {}

    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        raise ValueError("实时天气接口返回为空")

    first = results[0] if isinstance(results[0], dict) else {}
    location = first.get("location") if isinstance(first.get("location"), dict) else {}
    now = first.get("now") if isinstance(first.get("now"), dict) else {}
    return {
        "source": "seniverse",
        "available": True,
        "message": "",
        "city": str(location.get("name") or "北京"),
        "text": str(now.get("text") or "").strip(),
        "temperature": str(now.get("temperature") or "").strip(),
        "last_update": str(first.get("last_update") or ""),
    }
