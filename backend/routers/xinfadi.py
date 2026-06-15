from __future__ import annotations

import asyncio
import json
import math
import os
import random
import re
from datetime import date, datetime, timedelta
from statistics import mean, median, pstdev
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db, SessionLocal
from dependencies import require_role


router = APIRouter(prefix="/xinfadi", tags=["xinfadi"])

PER_PAGE = 200
MAX_PAGES = 80
ALLOWED_CAT_IDS = {1186, 1187, 1188, 1189, 1190, 1203, 1204}

_LAST_JOB: dict[str, Any] = {
    "job_id": "",
    "status": "idle",
    "progress": 0,
    "message": "等待采集任务",
    "updated_at": None,
}
_BACKFILL_STATUS: dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "message": "未启动补抓",
    "running": False,
    "finished": False,
    "total": 0,
    "processed": 0,
    "success": 0,
    "current": None,
    "progress_pct": 0,
    "logs": [],
    "updated_at": None,
}
_BATCH_RETRAIN_STATUS: dict[str, Any] = {
    "status": "idle",
    "running": False,
    "finished": False,
    "total": 0,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "current": None,
    "progress_pct": 0,
    "logs": [],
    "updated_at": None,
}
_POLITE_CRAWL = bool(settings.xinfadi_polite_crawl)
# 502/503/504 视为瞬时；403/429 视为反爬识别，单独走更长冷静期
_RETRYABLE_STATUS = {502, 503, 504}
_BANNED_STATUS = {403, 429}

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def _build_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(_UA_POOL),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "http://www.xinfadi.com.cn",
        "Referer": "http://www.xinfadi.com.cn/priceDetail.html",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


async def _warm_up_session(client: httpx.AsyncClient) -> None:
    """模拟浏览器在请求 API 前先访问行情详情页，拿到 cookie，降低被反爬概率。"""
    try:
        await client.get("http://www.xinfadi.com.cn/priceDetail.html", timeout=httpx.Timeout(8.0, connect=5.0))
    except Exception:
        return


async def _post_xinfadi_price_page(
    client: httpx.AsyncClient,
    current: int,
    date_slash: str,
    slow: bool = False,
) -> httpx.Response:
    """POST 新发地分页接口；区分瞬时错误与反爬识别（403/429），后者更长退避。"""
    max_tries = max(1, min(12, int(settings.xinfadi_http_max_retries)))
    base = float(settings.xinfadi_http_retry_base_seconds)
    banned_seen = False
    for attempt in range(max_tries):
        if attempt > 0:
            if banned_seen:
                # 反爬识别后的长冷静期，每次拉长，慢速模式更夸张
                cool = (45.0 if slow else 25.0) * (1.6 ** (attempt - 1)) + random.uniform(5.0, 18.0)
                wait = min(cool, 240.0)
            else:
                wait = base * (2 ** (attempt - 1)) + random.uniform(0, 1.5)
                wait = min(wait, 45.0)
            await asyncio.sleep(wait)
        try:
            response = await client.post(
                settings.xinfadi_price_api,
                data={
                    "current": current,
                    "limit": PER_PAGE,
                    "pubDateStartTime": date_slash,
                    "pubDateEndTime": date_slash,
                },
                headers=_build_headers(),
            )
            code = response.status_code
            if 200 <= code < 300:
                return response
            if code in _BANNED_STATUS and attempt < max_tries - 1:
                banned_seen = True
                try:
                    await response.aread()
                except Exception:
                    pass
                # 被反爬识别后清掉旧 cookie，重新热身
                client.cookies.clear()
                await _warm_up_session(client)
                continue
            if code in _RETRYABLE_STATUS and attempt < max_tries - 1:
                try:
                    await response.aread()
                except Exception:
                    pass
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            c = e.response.status_code if e.response is not None else 0
            if c in _BANNED_STATUS and attempt < max_tries - 1:
                banned_seen = True
                client.cookies.clear()
                await _warm_up_session(client)
                continue
            if c not in _RETRYABLE_STATUS or attempt >= max_tries - 1:
                raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError):
            if attempt >= max_tries - 1:
                raise
    raise httpx.HTTPError("新发地行情请求重试耗尽")


class BackfillBody(BaseModel):
    start_date: Optional[str] = Field(default=None)
    end_date: Optional[str] = Field(default=None)
    slow: bool = Field(default=False, description="慢速补抓：仅加大分页抓取间隔；日期间隔仍用配置的 3～5 秒")


def _monitor_guard(_=Depends(require_role("monitor"))) -> None:
    return None


def _tbl() -> str:
    return settings.xinfadi_price_table or "xinfadi_price_crawl"


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _default_date() -> date:
    return _today() - timedelta(days=1)


def _daterange_days(start_day: date, end_day: date) -> list[date]:
    out: list[date] = []
    cur = start_day
    while cur <= end_day:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _parse_day(value: Any, fallback: Optional[date] = None) -> Optional[date]:
    if value is None or value == "":
        return fallback
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text_value = str(value).strip().replace("/", "-").split()[0]
    try:
        return date.fromisoformat(text_value)
    except ValueError:
        return fallback


def _fmt_day(value: Any) -> str:
    day = _parse_day(value)
    return day.isoformat() if day else ""


def _num(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _repair_text(value: Any) -> str:
    text_value = str(value or "")
    if not text_value:
        return ""
    if not re.search(r"[åèéçæä]", text_value):
        return text_value
    try:
        return text_value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text_value


def _safe_rate(part: float, total: float) -> float:
    return round(part / total * 100, 2) if total else 0.0


def _row_from_api(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "category1": item.get("prodCat") or "",
        "category2": item.get("prodPcat") or "",
        "product_name": item.get("prodName") or "",
        "min_price": str(item.get("lowPrice") or ""),
        "avg_price": str(item.get("avgPrice") or ""),
        "max_price": str(item.get("highPrice") or ""),
        "spec": item.get("specInfo") or "",
        "origin": item.get("place") or "",
        "unit": item.get("unitInfo") or "",
        "publish_date": _fmt_day(item.get("pubDate")),
    }


def _db_row(row: Any) -> dict[str, Any]:
    m = row._mapping if hasattr(row, "_mapping") else row
    return {
        "id": int(m.get("id") or 0),
        "date": _fmt_day(m.get("crawl_date")),
        "crawl_date": _fmt_day(m.get("crawl_date")),
        "category1": _repair_text(m.get("category1")),
        "category2": _repair_text(m.get("category2")),
        "product_name": _repair_text(m.get("product_name")),
        "min_price": _num(m.get("min_price")),
        "avg_price": _num(m.get("avg_price")),
        "max_price": _num(m.get("max_price")),
        "spec": _repair_text(m.get("spec")),
        "origin": _repair_text(m.get("origin")),
        "unit": _repair_text(m.get("unit")),
        "publish_date": _fmt_day(m.get("publish_date")),
    }


def _forecast_from_series(points: list[dict[str, Any]], days: int = 14) -> list[dict[str, Any]]:
    values = [_num(p.get("avg_price")) for p in points if _num(p.get("avg_price")) > 0]
    if not values:
        values = [1.0]
    baseline = mean(values[-14:])
    volatility = 0.04
    if len(values) > 2 and baseline:
        volatility = min(0.22, max(0.015, (max(values[-30:]) - min(values[-30:])) / baseline))
    trend = 0.0
    if len(values) >= 7 and values[-7]:
        trend = max(-0.08, min(0.1, (values[-1] - values[-7]) / values[-7]))
    last_day = _parse_day(points[-1].get("crawl_date") if points else None, _default_date()) or _default_date()
    out: list[dict[str, Any]] = []
    for i in range(1, days + 1):
        seasonal = math.sin(i / 7 * math.pi * 2) * volatility * 0.22
        yhat = max(0.01, baseline * (1 + trend * i / max(days, 1) + seasonal))
        out.append(
            {
                "date": (last_day + timedelta(days=i)).isoformat(),
                "yhat": round(yhat, 2),
                "lower": round(max(0.01, yhat * (1 - volatility)), 2),
                "upper": round(yhat * (1 + volatility), 2),
                "confidence": round(max(0.5, 0.9 - volatility), 2),
                "trend": "up" if trend > 0.02 else "down" if trend < -0.02 else "stable",
            }
        )
    return out


def _normalize_forecast_row(row: dict[str, Any]) -> dict[str, Any]:
    yhat = _num(row.get("yhat"))
    lower = _num(row.get("yhat_lower", row.get("lower")))
    upper = _num(row.get("yhat_upper", row.get("upper")))
    return {
        "date": _fmt_day(row.get("date")),
        "yhat": round(yhat, 4),
        "yhat_lower": round(lower, 4),
        "yhat_upper": round(upper, 4),
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "confidence": round(_num(row.get("confidence")), 4),
        "trend": row.get("trend") or "flat",
    }


async def _latest_forecast_snapshot(db: AsyncSession, product_name: str) -> Optional[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT metrics_json, factors_json, decomposition_json, latest_forecast_json, updated_at
            FROM xinfadi_forecast_metrics
            WHERE product_name = :product_name
            LIMIT 1
            """
        ),
        {"product_name": product_name},
    )
    row = result.fetchone()
    if not row:
        return None
    m = row._mapping
    latest = _json_loads(m.get("latest_forecast_json"), {})
    if not isinstance(latest, dict):
        latest = {}
    ensemble = [_normalize_forecast_row(x) for x in (latest.get("ensemble") or []) if isinstance(x, dict)]
    latest["ensemble"] = [x for x in ensemble if x.get("date")]
    return {
        "product_name": product_name,
        "latest_forecast": latest,
        "metrics": _json_loads(m.get("metrics_json"), {}),
        "factors": _json_loads(m.get("factors_json"), []),
        "decomposition": _json_loads(m.get("decomposition_json"), {}),
        "updated_at": m.get("updated_at"),
    }


def _slice_forecast_window(ensemble: list[dict[str, Any]], days: int, *, start_day: Optional[date] = None) -> list[dict[str, Any]]:
    target = start_day or (_today() + timedelta(days=1))
    future = []
    for row in ensemble:
        row_day = _parse_day(row.get("date"))
        if row_day and row_day >= target:
            future.append(row)
    if not future:
        future = ensemble
    return future[: max(1, min(60, int(days)))]


def _daily_price_series(points: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    bucket: dict[str, list[float]] = {}
    exact_name = ""
    for row in points:
        day = _fmt_day(row.get("crawl_date"))
        price = _num(row.get("avg_price"))
        if not day or price <= 0:
            continue
        exact_name = exact_name or _repair_text(row.get("product_name"))
        bucket.setdefault(day, []).append(price)
    series = [
        {"date": day, "avg_price": round(mean(values), 4)}
        for day, values in sorted(bucket.items())
        if values
    ]
    return exact_name, series


def _anchored_forecast(series: list[dict[str, Any]], days: int) -> dict[str, Any]:
    """实时锚定预测（Opus 重建，替代旧的陈旧快照线性外推）。

    设计：以最新实际均价为锚点，在对数空间做 AR(1) 向近月中枢回归 + 阻尼趋势；
    单步涨跌幅按历史波动率封顶，并裁剪到近 180 日极值外扩的绝对边界。
    保证「明日 ≈ 实价」、缓慢均值回归、绝不出现翻倍式跳变；附随步长展开的置信带。
    输出集成线 + 3 条可解释子线（均值回归 / 持稳 / 阻尼趋势）。
    """
    vals = [_num(r["avg_price"]) for r in series if _num(r.get("avg_price")) > 0]
    dates = [r["date"] for r in series if _num(r.get("avg_price")) > 0]
    n = len(vals)
    if n < 5:
        return {}
    p0 = vals[-1]
    last_day = _parse_day(dates[-1]) or _today()
    recent = vals[-60:]
    level = median(vals[-30:])                       # 均值回归中枢
    win180 = vals[-180:]
    lo = max(0.01, min(win180) * 0.8)
    hi = max(win180) * 1.2

    rets = [
        math.log(b / a)
        for a, b in zip(recent[:-1], recent[1:])
        if a > 0 and b > 0
    ]
    if rets:
        srt = sorted(rets)
        k = int(len(srt) * 0.05)
        clipped = srt[k: len(srt) - k] or srt          # winsorize 去极值
        sigma = pstdev(clipped) if len(clipped) > 1 else abs(clipped[0])
    else:
        sigma = 0.0
    sigma = min(0.15, max(0.01, sigma))
    last7 = rets[-7:]
    g = median(last7) if last7 else 0.0
    g = max(-2 * sigma, min(2 * sigma, g))             # 阻尼趋势初始漂移

    kappa, phi, z = 0.15, 0.80, 1.28
    ln_level = math.log(max(0.01, level))

    def _path(use_revert: bool, use_trend: bool) -> list[float]:
        out: list[float] = []
        logf = math.log(max(0.01, p0))
        for h in range(1, days + 1):
            step = 0.0
            if use_revert:
                step += kappa * (ln_level - logf)
            if use_trend:
                step += g * (phi ** h)
            step = max(-1.5 * sigma, min(1.5 * sigma, step))   # 单步涨跌封顶
            logf += step
            out.append(min(hi, max(lo, math.exp(logf))))
        return out

    revert_path = _path(use_revert=True, use_trend=False)
    trend_path = _path(use_revert=False, use_trend=True)
    stable_path = [min(hi, max(lo, p0))] * days
    ensemble_vals = [
        0.5 * rv + 0.3 * st + 0.2 * tr
        for rv, st, tr in zip(revert_path, stable_path, trend_path)
    ]

    ensemble: list[dict[str, Any]] = []
    for h in range(1, days + 1):
        yhat = ensemble_vals[h - 1]
        spread = math.exp(z * sigma * math.sqrt(h))
        conf = max(0.4, min(0.95, 0.9 - 0.5 * sigma - 0.02 * h))
        ensemble.append({
            "date": (last_day + timedelta(days=h)).isoformat(),
            "yhat": round(yhat, 3),
            "yhat_lower": round(max(lo, yhat / spread), 3),
            "yhat_upper": round(min(hi * 1.5, yhat * spread), 3),
            "lower": round(max(lo, yhat / spread), 3),
            "upper": round(min(hi * 1.5, yhat * spread), 3),
            "confidence": round(conf, 3),
            "trend": "up" if yhat > p0 * 1.01 else "down" if yhat < p0 * 0.99 else "flat",
        })

    def _component(name: str, path_vals: list[float]) -> dict[str, Any]:
        return {
            "name": name,
            "points": [
                {"date": (last_day + timedelta(days=h + 1)).isoformat(), "yhat": round(v, 3)}
                for h, v in enumerate(path_vals)
            ],
        }

    return {
        "anchor_price": round(p0, 3),
        "anchor_date": last_day.isoformat(),
        "level": round(level, 3),
        "sigma": round(sigma, 4),
        "bounds": [round(lo, 3), round(hi, 3)],
        "ensemble": ensemble,
        "components": [
            _component("均值回归", revert_path),
            _component("持稳基线", stable_path),
            _component("阻尼趋势", trend_path),
        ],
    }


def _backtest_mape(series: list[dict[str, Any]], h: int = 14) -> dict[str, Any]:
    """走动式 1 步回测最近 h 天：用此前数据预测次日、对比实际，给 MAPE/MAE/方向命中率。"""
    vals = [_num(r["avg_price"]) for r in series if _num(r.get("avg_price")) > 0]
    n = len(vals)
    if n < 8:
        return {}
    errs: list[float] = []
    aerr: list[float] = []
    hits = 0
    total = 0
    start = max(5, n - h)
    for t in range(start, n):
        fc = _anchored_forecast(series[:t], 1)
        if not fc or not fc.get("ensemble"):
            continue
        pred = fc["ensemble"][0]["yhat"]
        actual = vals[t]
        prev = vals[t - 1]
        if actual > 0:
            errs.append(abs(pred - actual) / actual)
            aerr.append(abs(pred - actual))
            if (pred - prev >= 0) == (actual - prev >= 0):
                hits += 1
            total += 1
    if not errs:
        return {}
    return {
        "mape": round(mean(errs) * 100, 1),
        "mae": round(mean(aerr), 3),
        "hit_rate": round(hits / total * 100, 1) if total else 0.0,
        "backtest_days": len(errs),
    }


def _reliability_grade(sample_count: int, mape: Optional[float], hit_rate: Optional[float]) -> tuple[str, str, str]:
    """诚实评级：综合样本充足度 + 回测 MAPE + 方向命中率，返回 (grade, label, reason)。

    样本不足或方向命中低于随机的，绝不评高可靠——避免「龙眼 42 天、命中 28.6%」却显示高可靠。
    """
    n = int(sample_count or 0)
    if n < 30:
        return "low", "谨慎参考", f"有效样本仅 {n} 天（<30），数据不足，仅供参考"
    if hit_rate is None or mape is None:
        return "low", "谨慎参考", "回测样本不足，方向可靠性未知"
    if hit_rate < 45:
        return "low", "谨慎参考", f"方向命中率 {hit_rate}%（低于随机），趋势判断不可靠"
    if n >= 120 and mape <= 12 and hit_rate >= 55:
        return "high", "高可靠", f"样本 {n} 天充足，回测误差 {mape}%、方向命中 {hit_rate}%"
    if mape <= 25 and n >= 60:
        return "mid", "中等可靠", f"样本 {n} 天、回测误差 {mape}%、方向命中 {hit_rate}%，建议结合当日行情复核"
    return "low", "谨慎参考", f"样本 {n} 天、回测误差 {mape}%、方向命中 {hit_rate}%，可靠性不足"


def _trend_component(series: list[dict[str, Any]], horizon: int) -> list[float]:
    import numpy as np

    values = np.array([_num(row["avg_price"]) for row in series], dtype=float)
    x = np.arange(len(values), dtype=float)
    slope, intercept = np.polyfit(x, values, 1)
    weekly = []
    for weekday in range(7):
        vals = values[np.arange(len(values)) % 7 == weekday]
        weekly.append(float(np.mean(vals - np.mean(values))) if len(vals) else 0.0)
    out = []
    for step in range(1, horizon + 1):
        idx = len(values) + step - 1
        out.append(max(0.01, float(intercept + slope * idx + weekly[idx % 7])))
    return out


def _sequence_component(series: list[dict[str, Any]], horizon: int) -> list[float]:
    values = [_num(row["avg_price"]) for row in series]
    if not values:
        return [0.01] * horizon
    out: list[float] = []
    window = values[-30:]
    for _ in range(horizon):
        short = mean(window[-7:]) if len(window) >= 7 else mean(window)
        mid = mean(window[-14:]) if len(window) >= 14 else short
        long = mean(window[-30:]) if len(window) >= 30 else mid
        momentum = (window[-1] - window[-7]) / window[-7] if len(window) >= 7 and window[-7] else 0.0
        yhat = max(0.01, short * 0.5 + mid * 0.3 + long * 0.2)
        yhat *= 1 + max(-0.08, min(0.08, momentum)) * 0.35
        out.append(yhat)
        window.append(yhat)
    return out


def _features(values: list[float], idx: int) -> list[float]:
    tail7 = values[max(0, idx - 7) : idx]
    tail14 = values[max(0, idx - 14) : idx]
    tail30 = values[max(0, idx - 30) : idx]
    last = values[idx - 1]
    lag7 = values[idx - 7] if idx >= 7 else last
    lag14 = values[idx - 14] if idx >= 14 else lag7
    lag30 = values[idx - 30] if idx >= 30 else lag14
    weekday = idx % 7
    return [
        last,
        lag7,
        lag14,
        lag30,
        mean(tail7) if tail7 else last,
        mean(tail14) if tail14 else last,
        mean(tail30) if tail30 else last,
        (max(tail14) - min(tail14)) if len(tail14) > 1 else 0.0,
        math.sin(2 * math.pi * weekday / 7),
        math.cos(2 * math.pi * weekday / 7),
    ]


def _xgboost_component(series: list[dict[str, Any]], horizon: int, model_dir: str, version: str) -> tuple[list[float], str, list[dict[str, Any]]]:
    import joblib
    import numpy as np
    from xgboost import XGBRegressor

    values = [_num(row["avg_price"]) for row in series]
    if len(values) < 90:
        raise RuntimeError("历史有效样本不足 90 天，无法训练 XGBoost 预测器")
    x_train = []
    y_train = []
    for idx in range(30, len(values)):
        x_train.append(_features(values, idx))
        y_train.append(values[idx])
    model = XGBRegressor(
        n_estimators=160,
        max_depth=3,
        learning_rate=0.055,
        subsample=0.92,
        colsample_bytree=0.92,
        objective="reg:squarederror",
        random_state=42,
    )
    model.fit(np.array(x_train, dtype=float), np.array(y_train, dtype=float))
    forecast_values = values[:]
    out = []
    for _ in range(horizon):
        pred = float(model.predict(np.array([_features(forecast_values, len(forecast_values))], dtype=float))[0])
        pred = max(0.01, pred)
        out.append(pred)
        forecast_values.append(pred)
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, f"xgboost_{version}.joblib")
    joblib.dump(model, model_path)
    labels = ["最新价", "7日滞后", "14日滞后", "30日滞后", "7日均值", "14日均值", "30日均值", "14日波动", "周内周期sin", "周内周期cos"]
    importances = getattr(model, "feature_importances_", [])
    factors = [
        {"name": labels[idx], "value": round(float(score), 4), "weight": round(float(score), 4)}
        for idx, score in enumerate(importances)
    ]
    factors.sort(key=lambda item: item["weight"], reverse=True)
    return out, model_path, factors[:8]


def _mape(actual: list[float], predicted: list[float]) -> float:
    pairs = [(a, p) for a, p in zip(actual, predicted) if a > 0]
    if not pairs:
        return 0.0
    return round(mean([abs(a - p) / a for a, p in pairs]) * 100, 2)


def _model_series(last_day: date, values: list[float], confidence: float) -> list[dict[str, Any]]:
    rows = []
    for idx, yhat in enumerate(values, 1):
        band = max(0.04, 0.11 - confidence * 0.04)
        rows.append(
            {
                "date": (last_day + timedelta(days=idx)).isoformat(),
                "yhat": round(max(0.01, yhat), 4),
                "yhat_lower": round(max(0.01, yhat * (1 - band)), 4),
                "yhat_upper": round(max(0.01, yhat * (1 + band)), 4),
                "confidence": round(confidence, 4),
                "trend": "up" if idx > 1 and yhat > values[idx - 2] * 1.01 else "down" if idx > 1 and yhat < values[idx - 2] * 0.99 else "flat",
            }
        )
    return rows


def _safe_model_dir(product_name: str) -> str:
    safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", product_name).strip("_") or "product"
    return os.path.join(settings.xinfadi_models_dir, safe_name)


async def _save_rows(db: AsyncSession, crawl_day: date, rows: list[dict[str, Any]]) -> None:
    await db.execute(text(f"DELETE FROM `{_tbl()}` WHERE crawl_date = :crawl_date"), {"crawl_date": crawl_day})
    if rows:
        await db.execute(
            text(
                f"""
                INSERT INTO `{_tbl()}` (
                    crawl_date, category1, category2, product_name, min_price,
                    avg_price, max_price, spec, origin, unit, publish_date
                ) VALUES (
                    :crawl_date, :category1, :category2, :product_name, :min_price,
                    :avg_price, :max_price, :spec, :origin, :unit, :publish_date
                )
                """
            ),
            [
                {
                    **row,
                    "crawl_date": crawl_day,
                    "publish_date": _parse_day(row.get("publish_date")),
                }
                for row in rows
            ],
        )
    await db.commit()
    _invalidate_dates_cache()


# 进程级缓存：crawl_date DISTINCT 在数据量大且补抓写入并发时较慢，
# 用 60 秒 TTL 避免 dashboard 首屏 dates/sentiment 重复全扫导致请求堆积超时
_DATES_CACHE: dict[str, Any] = {"data": None, "expires_at": 0.0}
_DATES_CACHE_TTL = 60.0


def _invalidate_dates_cache() -> None:
    _DATES_CACHE["data"] = None
    _DATES_CACHE["expires_at"] = 0.0


async def _list_dates(db: AsyncSession) -> list[str]:
    import time as _time
    now = _time.monotonic()
    cached = _DATES_CACHE.get("data")
    if cached is not None and now < float(_DATES_CACHE.get("expires_at") or 0.0):
        return list(cached)
    result = await db.execute(text(f"SELECT DISTINCT crawl_date FROM `{_tbl()}` ORDER BY crawl_date"))
    dates = [_fmt_day(row[0]) for row in result.fetchall() if _fmt_day(row[0])]
    _DATES_CACHE["data"] = dates
    _DATES_CACHE["expires_at"] = now + _DATES_CACHE_TTL
    return dates


async def _latest_day(db: AsyncSession) -> Optional[str]:
    result = await db.execute(text(f"SELECT MAX(crawl_date) FROM `{_tbl()}`"))
    return _fmt_day(result.scalar_one_or_none()) or None


async def _existing_crawl_dates_in_range(db: AsyncSession, start_day: date, end_day: date) -> set[date]:
    """区间内库中已有行情的日期（有任意行即视为已抓，不再请求新发地）。"""
    result = await db.execute(
        text(
            f"""
            SELECT DISTINCT crawl_date FROM `{_tbl()}`
            WHERE crawl_date >= :start_day AND crawl_date <= :end_day
            """
        ),
        {"start_day": start_day, "end_day": end_day},
    )
    out: set[date] = set()
    for row in result.fetchall():
        raw = row[0]
        if raw is None:
            continue
        if isinstance(raw, datetime):
            out.add(raw.date())
        elif isinstance(raw, date):
            out.add(raw)
    return out


async def _query_rows(
    db: AsyncSession,
    *,
    crawl_date: Optional[str] = None,
    product_name: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> list[dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {"limit": int(limit)}
    if crawl_date:
        clauses.append("crawl_date = :crawl_date")
        params["crawl_date"] = _parse_day(crawl_date)
    if start_date:
        clauses.append("crawl_date >= :start_date")
        params["start_date"] = _parse_day(start_date)
    if end_date:
        clauses.append("crawl_date <= :end_date")
        params["end_date"] = _parse_day(end_date)
    if product_name.strip():
        clauses.append("product_name LIKE :product_name")
        params["product_name"] = f"%{product_name.strip()}%"
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await db.execute(
        text(
            f"""
            SELECT id, crawl_date, category1, category2, product_name, min_price,
                   avg_price, max_price, spec, origin, unit, publish_date
            FROM `{_tbl()}`
            {where_sql}
            ORDER BY crawl_date DESC, product_name ASC
            LIMIT :limit
            """
        ),
        params,
    )
    return [_db_row(row) for row in result.fetchall()]


async def _query_exact_product_rows(
    db: AsyncSession,
    *,
    product_names: list[str],
    start_date: str = "",
    end_date: str = "",
    cat1: str = "",
    limit: int = 20000,
) -> list[dict[str, Any]]:
    names = [name.strip() for name in product_names if name and name.strip()]
    if not names:
        return []
    clauses = ["product_name IN :product_names"]
    params: dict[str, Any] = {"product_names": tuple(names), "limit": int(limit)}
    if start_date:
        clauses.append("crawl_date >= :start_date")
        params["start_date"] = _parse_day(start_date)
    if end_date:
        clauses.append("crawl_date <= :end_date")
        params["end_date"] = _parse_day(end_date)
    if cat1.strip():
        clauses.append("category1 = :cat1")
        params["cat1"] = cat1.strip()
    result = await db.execute(
        text(
            f"""
            SELECT id, crawl_date, category1, category2, product_name, min_price,
                   avg_price, max_price, spec, origin, unit, publish_date
            FROM `{_tbl()}`
            WHERE {' AND '.join(clauses)}
            ORDER BY crawl_date ASC, product_name ASC
            LIMIT :limit
            """
        ).bindparams(bindparam("product_names", expanding=True)),
        params,
    )
    return [_db_row(row) for row in result.fetchall()]


async def _crawl_for_day(crawl_day: date, job: dict[str, Any], slow: bool = False) -> list[dict[str, Any]]:
    date_slash = crawl_day.strftime("%Y/%m/%d")
    rows: list[dict[str, Any]] = []
    total_count: Optional[int] = None
    timeout = httpx.Timeout(35.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=True) as client:
        # 先访问详情页拿一次 cookie，模拟浏览器入口路径
        await _warm_up_session(client)
        for current in range(1, MAX_PAGES + 1):
            job.update(
                {
                    "status": "running",
                    "progress": min(95, int((current - 1) / MAX_PAGES * 100)),
                    "message": f"抓取 {crawl_day.isoformat()} 第 {current} 页",
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            response = await _post_xinfadi_price_page(client, current, date_slash, slow=slow)
            payload = response.json()
            if total_count is None:
                try:
                    total_count = int(payload.get("count") or 0)
                except (TypeError, ValueError):
                    total_count = 0
            page_rows = payload.get("list") or []
            if not page_rows:
                break
            for item in page_rows:
                raw_id = item.get("prodCatid")
                try:
                    cat_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if cat_id not in ALLOWED_CAT_IDS:
                    continue
                row = _row_from_api(item)
                if row["publish_date"] == crawl_day.isoformat():
                    rows.append(row)
            if total_count and current * PER_PAGE >= total_count:
                break
            if slow:
                # 慢速：分页之间冷却 3～7 秒，显著低于人工浏览速度，但相比之前 0.65~1.85 安全得多
                await asyncio.sleep(random.uniform(3.0, 7.0))
            elif _POLITE_CRAWL:
                await asyncio.sleep(random.uniform(0.5, 1.2))
            else:
                await asyncio.sleep(random.uniform(0.12, 0.38))
    dedup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["product_name"], row["category1"], row["category2"], row["origin"])
        dedup[key] = row
    return list(dedup.values())


async def _crawl_and_store(crawl_day: date, job: dict[str, Any], slow: bool = False) -> None:
    try:
        rows = await _crawl_for_day(crawl_day, job, slow=slow)
        async with SessionLocal() as db:
            await _save_rows(db, crawl_day, rows)
        job.update(
            {
                "status": "completed",
                "progress": 100,
                "message": f"已抓取并入库 {len(rows)} 条新发地报价",
                "row_count": len(rows),
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
    except Exception as exc:  # noqa: BLE001
        message = str(exc) or repr(exc) or exc.__class__.__name__
        job.update(
            {
                "status": "failed",
                "progress": 0,
                "message": f"抓取失败：{message[:220]}",
                "updated_at": datetime.utcnow().isoformat(),
            }
        )


async def _retrain_product(product_name: str) -> None:
    async with SessionLocal() as db:
        version = datetime.utcnow().strftime("xfd-%Y%m%d%H%M%S")
        await _upsert_job(db, product_name, status="training", progress=8, stage="加载历史行情", started_at=datetime.utcnow(), model_version=version)
        try:
            candidate = await db.execute(
                text(
                    f"""
                    SELECT product_name, COUNT(*) AS sample_count
                    FROM `{_tbl()}`
                    WHERE product_name = :exact OR product_name LIKE :keyword
                    GROUP BY product_name
                    ORDER BY (product_name = :exact) DESC, sample_count DESC, product_name ASC
                    LIMIT 1
                    """
                ),
                {"exact": product_name, "keyword": f"%{product_name}%"},
            )
            candidate_row = candidate.fetchone()
            target_name = _repair_text(candidate_row.product_name) if candidate_row else product_name
            points = await _query_rows(db, product_name=target_name, limit=5000)
            exact_name, series = _daily_price_series(sorted(points, key=lambda row: row["crawl_date"]))
            exact_name = exact_name or target_name
            if len(series) < 120:
                raise RuntimeError(f"历史有效样本仅 {len(series)} 天，低于 120 天训练门槛")

            horizon = 30
            values = [_num(row["avg_price"]) for row in series]
            last_day = _parse_day(series[-1]["date"], _default_date()) or _default_date()
            model_dir = _safe_model_dir(exact_name)

            await _upsert_job(db, exact_name, status="training", progress=25, stage="训练趋势/周期组件", model_version=version)
            # 同步 CPU/IO 训练 offload 到线程，避免阻塞事件循环（批量重训时整站 API 不卡顿）
            trend_values = await asyncio.to_thread(_trend_component, series, horizon)

            await _upsert_job(db, exact_name, status="training", progress=45, stage="训练序列组件", model_version=version)
            sequence_values = await asyncio.to_thread(_sequence_component, series, horizon)

            await _upsert_job(db, exact_name, status="training", progress=70, stage="训练 XGBoost 特征模型", model_version=version)
            xgb_values, xgb_path, factors = await asyncio.to_thread(_xgboost_component, series, horizon, model_dir, version)

            weights = {"prophet_trend": 0.35, "sequence_signal": 0.3, "xgboost": 0.35}
            ensemble_values = [
                trend_values[idx] * weights["prophet_trend"]
                + sequence_values[idx] * weights["sequence_signal"]
                + xgb_values[idx] * weights["xgboost"]
                for idx in range(horizon)
            ]
            holdout = min(21, max(7, len(values) // 8))
            actual_holdout = values[-holdout:]
            naive_holdout = values[-holdout - 1 : -1] if len(values) > holdout else actual_holdout
            mape = _mape(actual_holdout, naive_holdout)
            confidence = max(0.55, min(0.92, 0.9 - mape / 250))
            volatility = (max(values[-30:]) - min(values[-30:])) / mean(values[-30:]) if len(values) >= 30 and mean(values[-30:]) else 0.0

            trend_rows = _model_series(last_day, trend_values, max(0.52, confidence - 0.06))
            sequence_rows = _model_series(last_day, sequence_values, max(0.52, confidence - 0.04))
            xgb_rows = _model_series(last_day, xgb_values, confidence)
            ensemble_rows = _model_series(last_day, ensemble_values, confidence)

            latest_forecast = {
                "product": exact_name,
                "product_name": exact_name,
                "model_version": version,
                "model_trained_at": datetime.utcnow().isoformat(),
                "forecast_days": horizon,
                "sample_count": len(series),
                "train_start_date": series[0]["date"],
                "train_end_date": series[-1]["date"],
                "algorithmic": True,
                "fallback": False,
                "ensemble": ensemble_rows,
                "models": {
                    "prophet": trend_rows,
                    "lstm": sequence_rows,
                    "xgboost": xgb_rows,
                },
                "accuracy": {
                    "mape": mape,
                    "confidence": round(confidence, 4),
                    "holdout_days": holdout,
                    "volatility": round(volatility, 4),
                },
                "feature_importance": factors,
                "decomposition": {
                    "model_weights": weights,
                    "trend": "up" if ensemble_values[-1] > ensemble_values[0] * 1.03 else "down" if ensemble_values[-1] < ensemble_values[0] * 0.97 else "flat",
                    "component_notes": {
                        "prophet": "趋势/周内周期组件，用于兼容 ai-agent Prophet 预测快照结构。",
                        "lstm": "序列滚动信号组件，用于兼容 ai-agent LSTM 预测快照结构。",
                        "xgboost": "XGBoostRegressor 特征模型。",
                    },
                },
            }
            metrics = {
                "sample_count": len(series),
                "latest_price": round(values[-1], 4),
                "avg_price": round(mean(values), 4),
                "mape": mape,
                "confidence": round(confidence, 4),
                "fallback": False,
                "model_version": version,
            }
            decomposition = latest_forecast["decomposition"]

            await _upsert_job(db, exact_name, status="training", progress=90, stage="写入模型与预测快照", model_version=version)
            await db.execute(
                text(
                    """
                    INSERT INTO xinfadi_forecast_models
                    (product_name, model_kind, model_path, trained_at, sample_count, meta_json, model_version)
                    VALUES
                    (:product_name, 'prophet_trend', :trend_path, :trained_at, :sample_count, :trend_meta, :model_version),
                    (:product_name, 'lstm_sequence', :sequence_path, :trained_at, :sample_count, :sequence_meta, :model_version),
                    (:product_name, 'xgboost', :xgb_path, :trained_at, :sample_count, :xgb_meta, :model_version)
                    ON DUPLICATE KEY UPDATE
                        model_path=VALUES(model_path),
                        trained_at=VALUES(trained_at),
                        sample_count=VALUES(sample_count),
                        meta_json=VALUES(meta_json)
                    """
                ),
                {
                    "product_name": exact_name,
                    "trend_path": os.path.join(model_dir, f"prophet_trend_{version}.json"),
                    "sequence_path": os.path.join(model_dir, f"lstm_sequence_{version}.json"),
                    "xgb_path": xgb_path,
                    "trained_at": datetime.utcnow(),
                    "sample_count": len(series),
                    "trend_meta": json.dumps({"component": "trend_weekly", "fallback": False}, ensure_ascii=False),
                    "sequence_meta": json.dumps({"component": "rolling_sequence", "fallback": False}, ensure_ascii=False),
                    "xgb_meta": json.dumps({"component": "xgboost", "fallback": False}, ensure_ascii=False),
                    "model_version": version,
                },
            )
            os.makedirs(model_dir, exist_ok=True)
            with open(os.path.join(model_dir, f"prophet_trend_{version}.json"), "w", encoding="utf-8") as fp:
                json.dump({"version": version, "forecast": trend_rows}, fp, ensure_ascii=False, indent=2)
            with open(os.path.join(model_dir, f"lstm_sequence_{version}.json"), "w", encoding="utf-8") as fp:
                json.dump({"version": version, "forecast": sequence_rows}, fp, ensure_ascii=False, indent=2)
            await db.execute(
                text(
                    """
                    INSERT INTO xinfadi_forecast_metrics
                    (product_name, metrics_json, factors_json, decomposition_json, latest_forecast_json)
                    VALUES (:product_name, :metrics_json, :factors_json, :decomposition_json, :latest_forecast_json)
                    ON DUPLICATE KEY UPDATE
                        metrics_json=VALUES(metrics_json),
                        factors_json=VALUES(factors_json),
                        decomposition_json=VALUES(decomposition_json),
                        latest_forecast_json=VALUES(latest_forecast_json)
                    """
                ),
                {
                    "product_name": exact_name,
                    "metrics_json": json.dumps(metrics, ensure_ascii=False),
                    "factors_json": json.dumps(factors, ensure_ascii=False),
                    "decomposition_json": json.dumps(decomposition, ensure_ascii=False),
                    "latest_forecast_json": json.dumps(latest_forecast, ensure_ascii=False),
                },
            )
            await _upsert_job(db, exact_name, status="done", progress=100, stage="完成", finished_at=datetime.utcnow(), model_version=version)
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await _upsert_job(
                db,
                product_name,
                status="failed",
                progress=100,
                stage="训练失败",
                finished_at=datetime.utcnow(),
                error_msg=str(exc)[:500],
                model_version=version,
            )


async def _upsert_job(
    db: AsyncSession,
    product_name: str,
    *,
    status: str,
    progress: int,
    stage: str,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    error_msg: Optional[str] = None,
    model_version: Optional[str] = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO xinfadi_forecast_jobs
            (product_name, status, progress, stage, started_at, finished_at, error_msg, model_version)
            VALUES (:product_name, :status, :progress, :stage, :started_at, :finished_at, :error_msg, :model_version)
            ON DUPLICATE KEY UPDATE
                status=VALUES(status),
                progress=VALUES(progress),
                stage=VALUES(stage),
                started_at=COALESCE(VALUES(started_at), started_at),
                finished_at=VALUES(finished_at),
                error_msg=VALUES(error_msg),
                model_version=VALUES(model_version)
            """
        ),
        {
            "product_name": product_name,
            "status": status,
            "progress": int(max(0, min(100, progress))),
            "stage": stage,
            "started_at": started_at,
            "finished_at": finished_at,
            "error_msg": error_msg,
            "model_version": model_version,
        },
    )
    await db.commit()


@router.get("/default_date")
async def default_date(_=Depends(_monitor_guard)):
    return {"date": _default_date().isoformat()}


@router.get("/polite_crawl")
async def polite_crawl_get(_=Depends(_monitor_guard)):
    return {"polite": _POLITE_CRAWL}


@router.post("/polite_crawl")
async def polite_crawl_post(payload: Optional[dict[str, Any]] = None, _=Depends(_monitor_guard)):
    global _POLITE_CRAWL
    _POLITE_CRAWL = bool((payload or {}).get("polite"))
    return {"polite": _POLITE_CRAWL}


@router.get("/analytics/dates")
async def analytics_dates(_=Depends(_monitor_guard), db: AsyncSession = Depends(get_db)):
    dates = await _list_dates(db)
    return {
        "dates": dates,
        "data_dates": dates,
        "min_date": dates[0] if dates else None,
        "max_date": dates[-1] if dates else None,
        "available_dates": dates[-30:],
    }


@router.get("/analytics/products")
async def analytics_products(
    q: str = "",
    limit: int = Query(120, ge=1, le=3000),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    clauses = []
    params: dict[str, Any] = {"limit": limit}
    if q.strip():
        clauses.append("product_name LIKE :q")
        params["q"] = f"%{q.strip()}%"
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await db.execute(
        text(
            f"""
            SELECT product_name, category1, COUNT(*) AS sample_count, AVG(CAST(avg_price AS DECIMAL(12,2))) AS avg_price
            FROM `{_tbl()}`
            {where_sql}
            GROUP BY product_name, category1
            ORDER BY sample_count DESC, product_name ASC
            LIMIT :limit
            """
        ),
        params,
    )
    rows = [
        {
            "name": _repair_text(row.product_name),
            "product_name": _repair_text(row.product_name),
            "category_name": _repair_text(row.category1) or "未分类",
            "sample_count": int(row.sample_count or 0),
            "avg_price": _num(row.avg_price),
        }
        for row in result.fetchall()
    ]
    return {"names": [row["product_name"] for row in rows], "rows": rows}


@router.get("/analytics/timeseries")
async def analytics_timeseries(
    product_name: str = "",
    prod_names: str = "",
    cat1: str = "",
    start_date: str = "",
    end_date: str = "",
    days: int = Query(30, ge=1, le=365),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    names = [x.strip() for x in (prod_names or "").split(",") if x.strip()]
    if product_name.strip() and not names:
        names = [product_name.strip()]
    if not start_date and not end_date:
        end = _parse_day(await _latest_day(db), _default_date()) or _default_date()
        start = end - timedelta(days=days - 1)
        start_date = start.isoformat()
        end_date = end.isoformat()
    if not names:
        hints = (await analytics_products(limit=4, _=None, db=db)).get("names", [])
        names = hints[:4]
    start = _parse_day(start_date, _default_date()) or _default_date()
    end = _parse_day(end_date, start) or start
    if start > end:
        start, end = end, start
    calendar_dates: list[str] = []
    cur = start
    while cur <= end:
        calendar_dates.append(cur.isoformat())
        cur += timedelta(days=1)
    rows = await _query_exact_product_rows(
        db,
        product_names=names,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        cat1=cat1,
        limit=max(20000, len(names) * len(calendar_dates) * 8),
    )
    by_product_day: dict[str, dict[str, list[dict[str, Any]]]] = {}
    detail_rows = []
    for row in rows:
        product = row["product_name"]
        day = row["crawl_date"]
        by_product_day.setdefault(product, {}).setdefault(day, []).append(row)
        detail_rows.append(
            {
                "发布日期": day,
                "品名": product,
                "一级分类": row.get("category1") or "",
                "平均价": row.get("avg_price"),
                "最低价": row.get("min_price"),
                "最高价": row.get("max_price"),
                "产地": row.get("origin") or "",
                "单位": row.get("unit") or "",
            }
        )
    series = []
    flat_rows = []
    points_with_value = 0
    for product in names:
        product_bucket = by_product_day.get(product, {})
        avg_values: list[Optional[float]] = []
        low_values: list[Optional[float]] = []
        high_values: list[Optional[float]] = []
        n_values: list[int] = []
        for day in calendar_dates:
            vals = product_bucket.get(day, [])
            avgs = [_num(v["avg_price"]) for v in vals if _num(v["avg_price"]) > 0]
            lows = [_num(v["min_price"]) for v in vals if _num(v["min_price"]) > 0]
            highs = [_num(v["max_price"]) for v in vals if _num(v["max_price"]) > 0]
            if avgs:
                points_with_value += 1
                avg_price = round(mean(avgs), 4)
                low_price = round(min(lows) if lows else min(avgs), 4)
                high_price = round(max(highs) if highs else max(avgs), 4)
                avg_values.append(avg_price)
                low_values.append(low_price)
                high_values.append(high_price)
                n_values.append(len(vals))
                flat_rows.append({"date": day, "product_name": product, "avg_price": avg_price, "low_price": low_price, "high_price": high_price, "sample_count": len(vals)})
            else:
                avg_values.append(None)
                low_values.append(None)
                high_values.append(None)
                n_values.append(0)
        series.append({"name": product, "avg": avg_values, "low": low_values, "high": high_values, "n": n_values})
    return {
        "product_name": names[0] if names else "",
        "product_names": names,
        "calendar_dates": calendar_dates,
        "series": series,
        "rows": flat_rows,
        "detail_rows": detail_rows,
        "meta": {
            "points_with_value": points_with_value,
            "prod_count": len([item for item in series if any(v is not None for v in item["avg"])]),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    }


@router.get("/analytics/sentiment")
async def analytics_sentiment(
    product_name: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    dates = await _list_dates(db)
    if len(dates) < 2:
        return {
            "has_data": False,
            "change_pct": None,
            "direction": "flat",
            "message": "新发地历史行情不足两天，暂无法计算整体价格景气度。",
            "product_name": product_name,
            "sentiment": "neutral",
            "signals": [],
        }
    prev_day, latest_day = dates[-2], dates[-1]
    clauses = ["crawl_date IN :days"]
    params: dict[str, Any] = {"days": (prev_day, latest_day)}
    if product_name.strip():
        clauses.append("product_name LIKE :product_name")
        params["product_name"] = f"%{product_name.strip()}%"
    result = await db.execute(
        text(
            f"""
            SELECT crawl_date, category1, AVG(CAST(avg_price AS DECIMAL(12,4))) AS avg_price, COUNT(*) AS row_count
            FROM `{_tbl()}`
            WHERE {' AND '.join(clauses)}
              AND avg_price IS NOT NULL AND avg_price <> ''
            GROUP BY crawl_date, category1
            """
        ).bindparams(bindparam("days", expanding=True)),
        params,
    )
    day_category: dict[str, dict[str, float]] = {}
    row_count = 0
    for row in result.fetchall():
        day = _fmt_day(row.crawl_date)
        category = _repair_text(row.category1) or "未分类"
        day_category.setdefault(day, {})[category] = _num(row.avg_price)
        row_count += int(row.row_count or 0)
    prev_map = day_category.get(prev_day, {})
    latest_map = day_category.get(latest_day, {})
    common = [cat for cat in latest_map if cat in prev_map and prev_map[cat] > 0 and latest_map[cat] > 0]
    if not common:
        return {
            "has_data": False,
            "change_pct": None,
            "direction": "flat",
            "message": f"最近两个有数据日（{prev_day}→{latest_day}）没有可比分类。",
            "product_name": product_name,
            "sentiment": "neutral",
            "signals": [{"name": "行情样本", "value": row_count, "unit": "条"}],
        }
    prev_avg = mean([prev_map[cat] for cat in common])
    latest_avg = mean([latest_map[cat] for cat in common])
    change_pct = round((latest_avg - prev_avg) / prev_avg * 100, 2) if prev_avg else 0
    direction = "up" if change_pct > 0.1 else "down" if change_pct < -0.1 else "flat"
    arrow = "↑" if direction == "up" else "↓" if direction == "down" else "→"
    return {
        "has_data": True,
        "change_pct": change_pct,
        "direction": direction,
        "message": f"相对前一有数据日（{prev_day}→{latest_day}），仅统计两天均出现的 {len(common)} 个一级分类内全部报价行的均价，变动{arrow}{abs(change_pct):.2f}%。",
        "product_name": product_name,
        "sentiment": "risk" if abs(change_pct) > 5 else "neutral",
        "signals": [
            {"name": "可比分类", "value": len(common), "unit": "个"},
            {"name": "价格变化", "value": change_pct, "unit": "%"},
            {"name": "行情样本", "value": row_count, "unit": "条"},
        ],
    }


@router.get("/data")
async def xinfadi_data(
    date: str = "",
    product_name: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    target = date or await _latest_day(db) or _default_date().isoformat()
    rows = await _query_rows(db, crawl_date=target, product_name=product_name, limit=10000)
    start = (page - 1) * page_size
    sliced = rows[start : start + page_size]
    return {"page": page, "page_size": page_size, "total": len(rows), "date": target, "rows": sliced}


@router.post("/crawl")
async def crawl(
    background_tasks: BackgroundTasks,
    payload: Optional[dict[str, Any]] = None,
    date: str = "",
    _=Depends(_monitor_guard),
):
    crawl_day = _parse_day(date or (payload or {}).get("date"), _default_date()) or _default_date()
    _LAST_JOB.update(
        {
            "job_id": f"xfd-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "status": "queued",
            "progress": 0,
            "message": f"已加入抓取队列：{crawl_day.isoformat()}",
            "date": crawl_day.isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
    )
    background_tasks.add_task(_crawl_and_store, crawl_day, _LAST_JOB)
    return _LAST_JOB


@router.get("/progress")
async def crawl_progress(_=Depends(_monitor_guard)):
    return _LAST_JOB


async def _backfill_worker(start_day: date, end_day: date, slow: bool = False) -> None:
    calendar = _daterange_days(start_day, end_day)
    async with SessionLocal() as db:
        existing = await _existing_crawl_dates_in_range(db, start_day, end_day)
    days = [d for d in calendar if d not in existing]
    skipped = len(calendar) - len(days)
    start_logs = [
        f"扫描 {start_day.isoformat()} ~ {end_day.isoformat()}：日历共 {len(calendar)} 日；库内已有 {skipped} 日，仅对缺失的 {len(days)} 日发起补抓。",
    ]
    if slow:
        slow_lo = float(settings.xinfadi_backfill_slow_day_pause_min)
        slow_hi = float(settings.xinfadi_backfill_slow_day_pause_max)
        start_logs.append(
            f"慢速模式：分页冷却 3～7 秒；日与日期冷却约 {slow_lo:g}～{slow_hi:g} 秒；遇 403/429 反爬识别自动长退避并清空会话重试，目标是不触发限流而非追求速度。"
        )
    if not days:
        start_logs.append("无缺失日期，无需请求新发地。")
        _BACKFILL_STATUS.update(
            {
                "status": "completed",
                "running": False,
                "finished": True,
                "progress": 100,
                "progress_pct": 100,
                "message": "无需补抓：区间内行情日期已齐全",
                "total": 0,
                "processed": 0,
                "success": 0,
                "current": None,
                "logs": start_logs,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        return

    _BACKFILL_STATUS.update(
        {
            "status": "running",
            "running": True,
            "finished": False,
            "progress": 0,
            "progress_pct": 0,
            "message": "补抓启动",
            "total": len(days),
            "processed": 0,
            "success": 0,
            "current": None,
            "logs": start_logs,
            "updated_at": datetime.utcnow().isoformat(),
        }
    )
    consecutive_failures = 0
    for idx, day in enumerate(days, 1):
        if idx > 1:
            if slow:
                lo = float(settings.xinfadi_backfill_slow_day_pause_min)
                hi = float(settings.xinfadi_backfill_slow_day_pause_max)
            else:
                lo = float(settings.xinfadi_backfill_day_pause_min)
                hi = float(settings.xinfadi_backfill_day_pause_max)
            if hi < lo:
                lo, hi = hi, lo
            pause = random.uniform(lo, hi) if hi > lo else lo
            # 连续失败时再追加冷却（避免一直撞被限流的窗口）
            if consecutive_failures >= 2:
                pause += random.uniform(30.0, 90.0) * min(consecutive_failures, 5)
            await asyncio.sleep(pause)
        local_job = {"status": "running", "progress": 0, "message": ""}
        await _crawl_and_store(day, local_job, slow=slow)
        ok = local_job.get("status") == "completed"
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
        logs = list(_BACKFILL_STATUS.get("logs") or [])
        logs.append(f"{'OK' if ok else 'WARN'} {day.isoformat()}：{local_job.get('message') or '无返回'}")
        _BACKFILL_STATUS.update(
            {
                "status": "running",
                "progress": int(idx / len(days) * 100),
                "progress_pct": int(idx / len(days) * 100),
                "message": f"已补抓 {day.isoformat()}：{local_job.get('message')}",
                "running": True,
                "finished": False,
                "total": len(days),
                "processed": idx,
                "success": int(_BACKFILL_STATUS.get("success") or 0) + (1 if ok else 0),
                "current": day.isoformat(),
                "logs": logs[-200:],
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
    logs = list(_BACKFILL_STATUS.get("logs") or [])
    logs.append(f"补抓结束：成功 {_BACKFILL_STATUS.get('success') or 0}/{len(days)} 日。")
    _BACKFILL_STATUS.update(
        {
            "status": "completed",
            "running": False,
            "finished": True,
            "progress": 100,
            "progress_pct": 100,
            "message": "补抓完成",
            "current": None,
            "logs": logs[-200:],
            "updated_at": datetime.utcnow().isoformat(),
        }
    )


@router.post("/backfill")
async def backfill(
    background_tasks: BackgroundTasks,
    body: Optional[BackfillBody] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    end_day = _parse_day(body.end_date if body else None, _default_date()) or _default_date()
    start_day = _parse_day(body.start_date if body else None, end_day - timedelta(days=6)) or (end_day - timedelta(days=6))
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    slow = bool(getattr(body, "slow", False)) if body else False
    calendar = _daterange_days(start_day, end_day)
    existing = await _existing_crawl_dates_in_range(db, start_day, end_day)
    missing = [d for d in calendar if d not in existing]
    if not missing:
        msg = f"{start_day.isoformat()} ~ {end_day.isoformat()} 区间内 MySQL 已有全部 {len(calendar)} 日行情，无需补抓。"
        _BACKFILL_STATUS.update(
            {
                "status": "completed",
                "running": False,
                "finished": True,
                "progress": 100,
                "progress_pct": 100,
                "message": msg,
                "total": 0,
                "processed": 0,
                "success": 0,
                "current": None,
                "logs": [msg],
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
        return {**_BACKFILL_STATUS, "started": False}

    background_tasks.add_task(_backfill_worker, start_day, end_day, slow)
    slow_tag = "（慢速）" if slow else ""
    skipped = len(calendar) - len(missing)
    if slow:
        pause_lo = float(settings.xinfadi_backfill_slow_day_pause_min)
        pause_hi = float(settings.xinfadi_backfill_slow_day_pause_max)
        pause_hint = f"慢速模式：分页冷却 3～7 秒，日间隔约 {pause_lo:g}～{pause_hi:g} 秒；遇 403/429 自动长退避并清空会话重试。"
    else:
        pause_lo = float(settings.xinfadi_backfill_day_pause_min)
        pause_hi = float(settings.xinfadi_backfill_day_pause_max)
        pause_hint = f"日与日期间隔约 {pause_lo:g}～{pause_hi:g} 秒。"
    _BACKFILL_STATUS.update(
        {
            "status": "queued",
            "running": False,
            "finished": False,
            "progress": 0,
            "progress_pct": 0,
            "message": f"已加入补抓队列{slow_tag}：{start_day.isoformat()}~{end_day.isoformat()}",
            "total": len(missing),
            "processed": 0,
            "success": 0,
            "current": None,
            "logs": [
                f"已加入补抓队列{slow_tag}：待抓 {len(missing)} 日（日历 {len(calendar)} 日中已跳过库内已有 {skipped} 日）。",
                pause_hint,
            ],
            "updated_at": datetime.utcnow().isoformat(),
        }
    )
    return {**_BACKFILL_STATUS, "started": True}


@router.get("/backfill/status")
async def backfill_status(_=Depends(_monitor_guard)):
    return _BACKFILL_STATUS


@router.post("/backfill/dismiss")
async def backfill_dismiss(_=Depends(_monitor_guard)):
    _BACKFILL_STATUS.update({"status": "dismissed", "running": False, "message": "已忽略本次补抓提醒", "updated_at": datetime.utcnow().isoformat()})
    return _BACKFILL_STATUS


async def live_product_forecast(
    db: AsyncSession,
    *,
    keyword: str,
    days: int = 14,
    min_series_days: int = 14,
) -> dict[str, Any]:
    """按最新新发地日序列做锚定实时预测（与 GET /predict、AI 助手共用）。"""
    kw = (keyword or "").strip()
    if not kw:
        return {"status": "empty", "product_name": "", "ensemble": [], "message": "缺少品名"}
    rows = await _query_rows(db, product_name=kw, limit=1000)
    if not rows:
        return {
            "status": "empty",
            "product_name": kw,
            "source": "xinfadi_live",
            "ensemble": [],
            "message": "未找到匹配的新发地行情商品",
        }

    exact_name, series = _daily_price_series(rows)
    exact_name = exact_name or rows[0]["product_name"]
    if len(series) < int(min_series_days):
        return {
            "status": "insufficient",
            "product_name": exact_name,
            "source": "xinfadi_live",
            "ensemble": [],
            "message": f"有效历史不足 {int(min_series_days)} 天，暂不出具预测。",
            "sample_count": len(series),
        }
    fc = _anchored_forecast(series, int(days))
    if not fc or not fc.get("ensemble"):
        return {
            "status": "failed",
            "product_name": exact_name,
            "source": "xinfadi_live",
            "ensemble": [],
            "message": "预测计算失败。",
            "sample_count": len(series),
        }
    accuracy = _backtest_mape(series, h=14)
    grade, grade_label, grade_reason = _reliability_grade(
        len(series), accuracy.get("mape"), accuracy.get("hit_rate")
    )
    ensemble = [_normalize_forecast_row(x) for x in fc["ensemble"]]
    p0 = fc["anchor_price"]
    lo, hi = fc["bounds"]
    drivers = [
        {"name": "锚定实价", "value": f"{p0} 元", "description": f"以 {fc['anchor_date']} 最新实际均价为预测起点"},
        {"name": "近月中枢", "value": f"{fc['level']} 元", "description": "预测向近 30 日中位价缓慢回归"},
        {"name": "日波动率", "value": f"{round(fc['sigma'] * 100, 1)}%", "description": "由近 60 日对数收益估计，约束单日涨跌幅"},
        {"name": "合理区间", "value": f"{lo}~{hi} 元", "description": "近 180 日极值外扩 20% 的硬边界"},
    ]
    return {
        "status": "ok",
        "product_name": exact_name,
        "product": exact_name,
        "source": "xinfadi_live",
        "fallback": False,
        "algorithmic": True,
        "method": "锚定均值回归 + 阻尼趋势（实时计算）",
        "anchor_price": p0,
        "anchor_date": fc["anchor_date"],
        "level": fc["level"],
        "sigma": fc["sigma"],
        "bounds": fc["bounds"],
        "model_version": f"live-{_today().isoformat()}",
        "model_trained_at": None,
        "forecast_updated_at": _today().isoformat(),
        "forecast_days": len(ensemble),
        "sample_count": len(series),
        "reliability": grade,
        "reliability_label": grade_label,
        "reliability_reason": grade_reason,
        "ensemble": ensemble,
        "components": fc["components"],
        "models": {comp["name"]: comp["points"] for comp in fc["components"]},
        "accuracy": accuracy,
        "feature_importance": [],
        "decomposition": {},
        "drivers": drivers,
    }


@router.get("/predict")
async def predict_product(
    product_name: str = "",
    product: str = "",
    days: int = Query(14, ge=1, le=60),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    keyword = (product_name or product or "").strip()
    if not keyword:
        product_rows = (await analytics_products(limit=1, _=None, db=db)).get("rows", [])
        keyword = product_rows[0]["product_name"] if product_rows else ""
    return await live_product_forecast(db, keyword=keyword, days=days)


@router.get("/predict/overview")
async def predict_overview(
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=0, le=5000),
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    only_trainable: bool = False,
    only_usable: bool = False,
    limit: int = Query(0, ge=0, le=5000),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    items = await _overview_items(db, q=q, only_trainable=only_trainable, only_usable=only_usable, sort_by=sort_by, sort_order=sort_order)
    if limit and not page_size:
        page_size = limit
    total = len(items)
    if page_size <= 0:
        paged = items
        page = 1
        page_size = total
    else:
        start = (page - 1) * page_size
        paged = items[start : start + page_size]

    # 仅对当前页用实时锚定算法重算「次日预测价/置信度/可靠灯」，
    # 避免展示陈旧训练快照值（如大白菜 0.830）；训练元数据(model_version/freshness/train_*)保留。
    for item in paged:
        try:
            rows = await _query_rows(db, product_name=item["product"], limit=1000)
            _, series = _daily_price_series(rows) if rows else ("", [])
            if len(series) >= 5:
                fc = _anchored_forecast(series, 1)
                first = (fc.get("ensemble") or [{}])[0] if fc else {}
                if first:
                    item["next_price"] = round(_num(first.get("yhat")), 4)
                    item["confidence"] = round(_num(first.get("confidence")), 4)
                    item["anchor_price"] = fc.get("anchor_price")
                    item["live"] = True
                    acc = _backtest_mape(series, h=14)
                    grade, grade_label, grade_reason = _reliability_grade(
                        len(series), acc.get("mape"), acc.get("hit_rate")
                    )
                    rank = {"high": 3, "mid": 2, "low": 1}[grade]
                    item["reliability"], item["reliability_rank"] = grade, rank
                    item["reliability_label"] = grade_label
                    item["reliability_reason"] = grade_reason
                    item["backtest_mape"] = acc.get("mape")
                    item["hit_rate"] = acc.get("hit_rate")
            else:
                item["next_price"] = None
                item["live"] = False
        except Exception:
            item["live"] = False

    return {"items": paged, "rows": paged, "total": total, "page": page, "page_size": page_size}


async def _overview_items(
    db: AsyncSession,
    q: str = "",
    only_trainable: bool = False,
    only_usable: bool = False,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> list[dict[str, Any]]:
    """枚举品种概览项（取 SQL + 计算 can_train/reliability + q/only_* 过滤 + 排序），
    不含分页后的昂贵实时重算，供 overview 分页与批量重训共用。"""
    kw = (q or "").strip()
    result = await db.execute(
        text(
            f"""
            SELECT
                p.product_name,
                p.total_day_count,
                COALESCE(v.effective_day_count, 0) AS effective_day_count,
                p.last_data_day,
                m.latest_forecast_json,
                m.metrics_json,
                m.updated_at AS forecast_updated_at,
                j.status AS train_status,
                j.progress AS train_progress,
                j.stage AS train_stage,
                j.error_msg,
                j.model_version AS job_model_version
            FROM (
                SELECT product_name, COUNT(DISTINCT crawl_date) AS total_day_count, MAX(crawl_date) AS last_data_day
                FROM `{_tbl()}`
                WHERE (:kw = '' OR product_name LIKE :like_kw)
                GROUP BY product_name
            ) p
            LEFT JOIN (
                SELECT t.product_name, COUNT(DISTINCT t.crawl_date) AS effective_day_count
                FROM `{_tbl()}` t
                JOIN (
                    SELECT product_name, MAX(crawl_date) AS last_data_day
                    FROM `{_tbl()}`
                    GROUP BY product_name
                ) z ON z.product_name = t.product_name
                WHERE t.avg_price IS NOT NULL
                  AND t.avg_price <> ''
                  AND t.crawl_date >= DATE_SUB(z.last_data_day, INTERVAL 364 DAY)
                GROUP BY t.product_name
            ) v ON v.product_name = p.product_name
            LEFT JOIN xinfadi_forecast_metrics m ON m.product_name = p.product_name
            LEFT JOIN xinfadi_forecast_jobs j ON j.product_name = p.product_name
            """
        ),
        {"kw": kw, "like_kw": f"%{kw}%"},
    )
    now = datetime.utcnow()
    items = []
    for row in result.fetchall():
        m = row._mapping
        product = _repair_text(m.get("product_name"))
        latest = _json_loads(m.get("latest_forecast_json"), {})
        metrics = _json_loads(m.get("metrics_json"), {})
        ensemble = [_normalize_forecast_row(x) for x in (latest.get("ensemble") or []) if isinstance(x, dict)]
        future = _slice_forecast_window(ensemble, 1)
        first = future[0] if future else (ensemble[0] if ensemble else {})
        confidence = _num(first.get("confidence")) if first else 0
        mape7 = _num((latest.get("accuracy") or metrics or {}).get("mape_7d", (latest.get("accuracy") or metrics or {}).get("mape", 0)))
        if confidence >= 0.85 and (not mape7 or mape7 <= 15):
            reliability, reliability_rank = "high", 3
        elif confidence >= 0.75 and (not mape7 or mape7 <= 25):
            reliability, reliability_rank = "mid", 2
        else:
            reliability, reliability_rank = "low", 1
        updated_at = m.get("forecast_updated_at")
        freshness_days = None
        if updated_at:
            freshness_days = max(0.0, (now - updated_at).total_seconds() / 86400.0)
        if freshness_days is None:
            freshness_text = "未训练"
        elif freshness_days < 1:
            freshness_text = f"{int(max(1, round(freshness_days * 24)))}小时内"
        else:
            freshness_text = f"{int(freshness_days)}天"
        sample_days = int(m.get("effective_day_count") or 0)
        can_train = sample_days >= 120
        item = {
            "product": product,
            "product_name": product,
            "sample_days": sample_days,
            "sample_days_total": int(m.get("total_day_count") or 0),
            "can_train": can_train,
            "blocked_reason": None if can_train else f"近365天有效样本不足 120 天（当前 {sample_days} 天）",
            "next_price": round(_num(first.get("yhat")), 4) if first else None,
            "confidence": round(confidence, 4) if confidence else None,
            "reliability": reliability,
            "reliability_rank": reliability_rank,
            "freshness_days": round(freshness_days, 2) if freshness_days is not None else None,
            "freshness_text": freshness_text,
            "updated_at": updated_at.isoformat() if updated_at else None,
            "model_version": latest.get("model_version") or m.get("job_model_version"),
            "train_status": m.get("train_status") or "idle",
            "train_progress": int(m.get("train_progress") or 0),
            "train_stage": m.get("train_stage") or "",
            "train_error": m.get("error_msg"),
            "latest_forecast_days": len(ensemble),
            "status": "ok" if ensemble else (m.get("train_status") or "idle"),
        }
        if only_trainable and not item["can_train"]:
            continue
        if only_usable and item["reliability"] not in ("high", "mid"):
            continue
        items.append(item)
    reverse = (sort_order or "desc").lower() != "asc"
    sorters = {
        "product": lambda x: str(x.get("product") or ""),
        "confidence": lambda x: float(x.get("confidence") or -1),
        "price": lambda x: float(x.get("next_price") or -1),
        "updated_at": lambda x: str(x.get("updated_at") or ""),
        "freshness": lambda x: float(x.get("freshness_days") if x.get("freshness_days") is not None else 1e9),
        "reliability": lambda x: int(x.get("reliability_rank") or 0),
        "sample_days": lambda x: int(x.get("sample_days") or 0),
    }
    items.sort(key=sorters.get((sort_by or "").lower(), sorters["updated_at"]), reverse=reverse)
    return items


@router.get("/predict/train-status")
async def train_status(
    product_name: str = "",
    product: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    keyword = product_name or product
    if not keyword:
        result = await db.execute(text("SELECT * FROM xinfadi_forecast_jobs ORDER BY updated_at DESC LIMIT 1"))
    else:
        result = await db.execute(text("SELECT * FROM xinfadi_forecast_jobs WHERE product_name LIKE :p ORDER BY updated_at DESC LIMIT 1"), {"p": f"%{keyword}%"})
    row = result.fetchone()
    if not row:
        return {"status": "idle", "progress": 0, "stage": "未开始", "model": "xinfadi-ensemble", "message": "尚未训练"}
    m = row._mapping
    return {
        "product_name": m.get("product_name"),
        "status": m.get("status"),
        "progress": int(m.get("progress") or 0),
        "stage": m.get("stage") or "",
        "started_at": m.get("started_at").isoformat() if m.get("started_at") else None,
        "updated_at": m.get("updated_at").isoformat() if m.get("updated_at") else None,
        "finished_at": m.get("finished_at").isoformat() if m.get("finished_at") else None,
        "error": m.get("error_msg"),
        "model_version": m.get("model_version"),
    }


@router.post("/predict/retrain")
async def retrain(
    background_tasks: BackgroundTasks,
    payload: Optional[dict[str, Any]] = None,
    product_name: str = "",
    product: str = "",
    _=Depends(_monitor_guard),
):
    name = (product_name or product or (payload or {}).get("product_name") or (payload or {}).get("product") or "").strip()
    if not name:
        name = "白菜"
    background_tasks.add_task(_retrain_product, name)
    return {"status": "queued", "product_name": name, "message": "训练任务已启动"}


async def _batch_retrain_worker(names: list[str]) -> None:
    """串行重训给定品名清单：一次只训一个（天然限速），逐个更新进度，
    try/finally 保证终态，不阻塞事件循环（_retrain_product 内部已 offload 同步训练到线程）。"""
    total = len(names)
    _BATCH_RETRAIN_STATUS.update(
        {
            "status": "running",
            "running": True,
            "finished": False,
            "total": total,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "current": None,
            "progress_pct": 0,
            "logs": [f"批量重训启动：共 {total} 个品种，串行训练（一次一个，避免拖慢整站 API）。"],
            "updated_at": datetime.utcnow().isoformat(),
        }
    )
    success = 0
    failed = 0
    try:
        for idx, name in enumerate(names, 1):
            _BATCH_RETRAIN_STATUS.update({"current": name, "updated_at": datetime.utcnow().isoformat()})
            ok = True
            err = ""
            try:
                await _retrain_product(name)
            except Exception as exc:  # noqa: BLE001
                ok = False
                err = str(exc)[:160]
            if ok:
                success += 1
            else:
                failed += 1
            logs = list(_BATCH_RETRAIN_STATUS.get("logs") or [])
            logs.append(f"{'OK' if ok else 'FAIL'} {name}{'' if ok else '：' + err}")
            _BATCH_RETRAIN_STATUS.update(
                {
                    "processed": idx,
                    "success": success,
                    "failed": failed,
                    "progress_pct": int(idx / total * 100) if total else 100,
                    "logs": logs[-200:],
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            # 让出事件循环，确保训练间隙 API 完全可响应
            await asyncio.sleep(0)
    finally:
        logs = list(_BATCH_RETRAIN_STATUS.get("logs") or [])
        logs.append(f"批量重训结束：成功 {success}，失败 {failed}，共 {total}。")
        _BATCH_RETRAIN_STATUS.update(
            {
                "status": "completed",
                "running": False,
                "finished": True,
                "current": None,
                "progress_pct": 100,
                "logs": logs[-200:],
                "updated_at": datetime.utcnow().isoformat(),
            }
        )


@router.post("/predict/retrain-all")
async def retrain_all(
    background_tasks: BackgroundTasks,
    q: str = "",
    only_trainable: bool = True,
    only_usable: bool = False,
    payload: Optional[dict[str, Any]] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """批量重训：枚举命中（带 q/筛选时为筛选命中全部，否则全部可训练）的品种，后台串行重训。"""
    body = payload or {}
    q = (body.get("q") if body.get("q") is not None else q) or ""
    if "only_trainable" in body:
        only_trainable = bool(body.get("only_trainable"))
    if "only_usable" in body:
        only_usable = bool(body.get("only_usable"))
    if _BATCH_RETRAIN_STATUS.get("running"):
        return {**_BATCH_RETRAIN_STATUS, "started": False, "message": "已有批量重训在进行中"}
    items = await _overview_items(db, q=q, only_trainable=True, only_usable=only_usable)
    # only_trainable 形参保留兼容，但批量重训只对 can_train 的品种发起（不可训练无意义）
    names = [it["product"] for it in items if it.get("can_train") and it.get("product")]
    if not names:
        return {"status": "idle", "started": False, "total": 0, "message": "没有可训练的品种"}
    background_tasks.add_task(_batch_retrain_worker, names)
    return {"status": "queued", "started": True, "total": len(names), "message": f"已提交 {len(names)} 个品种批量重训"}


@router.get("/predict/retrain-all/status")
async def retrain_all_status(_=Depends(_monitor_guard)):
    return dict(_BATCH_RETRAIN_STATUS)


@router.get("/predict/analysis")
async def predict_analysis(
    product_name: str = "",
    product: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    prediction = await predict_product(product_name=product_name or product, days=7, _=None, db=db)
    snapshot = await _latest_forecast_snapshot(db, prediction.get("product_name") or product_name or product)
    return {
        "product_name": prediction.get("product_name", product_name),
        "status": prediction.get("status"),
        "summary": "基于已训练的新发地 Prophet + LSTM + XGBoost 预测快照返回；无快照时不使用历史行情冒充未来预测。",
        "prediction": prediction,
        "decomposition": (snapshot or {}).get("decomposition") or prediction.get("decomposition") or {},
        "model_version": prediction.get("model_version"),
    }


@router.get("/predict/factors")
async def predict_factors(
    product_name: str = "",
    product: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    prediction = await predict_product(product_name=product_name or product, days=7, _=None, db=db)
    snapshot = await _latest_forecast_snapshot(db, prediction.get("product_name") or product_name or product)
    factors = (snapshot or {}).get("factors") or prediction.get("feature_importance") or []
    return {
        "product_name": prediction.get("product_name", product_name or product),
        "status": prediction.get("status"),
        "feature_importance": factors,
        "factors": factors,
        "model_version": prediction.get("model_version"),
    }


@router.get("/predict/accuracy")
async def predict_accuracy(
    product_name: str = "",
    product: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    if product_name or product:
        prediction = await predict_product(product_name=product_name or product, days=7, _=None, db=db)
        snapshot = await _latest_forecast_snapshot(db, prediction.get("product_name") or product_name or product)
        return {
            "product_name": prediction.get("product_name", product_name or product),
            "status": prediction.get("status"),
            "model": "xinfadi-ensemble-prophet-lstm-xgboost",
            "accuracy": (snapshot or {}).get("metrics") or prediction.get("accuracy") or {},
            "model_version": prediction.get("model_version"),
        }
    result = await db.execute(text("SELECT COUNT(*) FROM xinfadi_forecast_metrics"))
    trained = int(result.scalar_one() or 0)
    return {
        "model": "xinfadi-ensemble-prophet-lstm-xgboost",
        "trained_products": trained,
        "mae": 0,
        "mape": 0,
        "sample_count": trained,
        "fallback_supported": False,
    }
