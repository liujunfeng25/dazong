from __future__ import annotations

import asyncio
import json
import math
import random
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean as _stat_mean
from statistics import median as _stat_median
from statistics import pstdev as _stat_pstdev
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import SessionLocal, get_db
from dependencies import require_role
from services.zg_materialize import refresh_derived, make_sku_key, split_sku_key
from services.zg_change_analytics import compute_change_ranking, compute_change_ratio
from services.zg_data_quality import (
    HIGH_RATIO,
    build_forecast_sample_hint,
    detect_quality_flags,
    ensure_quality_table,
    normalize_quality_policy,
    now_naive,
    parse_evidence,
    quality_map_for_days,
    should_exclude_quality,
    sync_quality_flags_for_day,
)
from services.zg_quality_verify import quality_action_status, verify_flag_by_recrawl
from models import User
from services import zgncpjgw_credentials as zg_cred


router = APIRouter(prefix="/zgncpjgw", tags=["zgncpjgw"])


def _bare_route_param(value: Any, fallback: Any = None) -> Any:
    """剥离 FastAPI Query/Depends 默认值（服务层直接调用路由函数时不会走依赖注入）。"""
    if value is None or isinstance(value, (int, float, str, bool, date, datetime)):
        return value if value is not None else fallback
    if type(value).__name__ in ("Query", "Body", "Form", "File", "Header", "Cookie", "Depends"):
        default = getattr(value, "default", fallback)
        if default is Ellipsis or default is ...:
            return fallback
        return default
    return value


MAX_PAGES = 120
_DB_WRITE_LOCK = asyncio.Lock()
_UPSERT_DEADLOCK_RETRIES = 5

_LAST_JOB: dict[str, Any] = {
    "job_id": "",
    "status": "idle",
    "progress": 0,
    "message": "等待采集任务",
    "date": None,
    "district_id": None,
    "cate_id": None,
    "row_count": 0,
    "updated_at": None,
}
_BACKFILL_STATUS: dict[str, Any] = {
    "status": "idle",
    "running": False,
    "finished": False,
    "progress": 0,
    "progress_pct": 0,
    "message": "未启动补抓",
    "total": 0,
    "processed": 0,
    "success": 0,
    "sub_total": 0,
    "sub_processed": 0,
    "current": None,
    "logs": [],
    "updated_at": None,
}


class BackfillBody(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    district_id: Optional[int] = None
    cate_id: Optional[int] = None
    slow: bool = False
    forecast_sku_keys: list[str] = Field(default_factory=list, description="补抓完成后优先训练的当前页面 SKU")


class ZgCredentialsBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=32, description="中农价格网手机号")
    password: str = Field(..., min_length=1, max_length=128, description="登录密码")


class DailyReportBody(BaseModel):
    report_date: Optional[str] = None
    district_id: Optional[int] = None
    cate_id: Optional[int] = None
    scate: str = ""
    appendix_sku_key: str = ""
    appendix_start_date: str = ""
    appendix_end_date: str = ""
    format: str = Field(default="pdf", description="json 预览 / pdf 下载")


class QualityActionBody(BaseModel):
    action: str = Field(description="correct / isolate / restore")
    corrected_price: Optional[float] = Field(default=None, gt=0)
    note: str = Field(default="", max_length=1000)


def _monitor_guard(_=Depends(require_role("monitor"))) -> None:
    return None


def _tbl() -> str:
    return settings.zgncpjgw_price_table or "zgncpjgw_price_crawl"


AGG_TBL = "zgncpjgw_daily_agg"
IDX_TBL = "zgncpjgw_price_index"
FORECAST_TBL = "zgncpjgw_forecast_snapshots"
HOT_SKU_TBL = "zgncpjgw_hot_skus"

_FORECAST_STATUS: dict[str, Any] = {
    "running": False,
    "finished": False,
    "status": "idle",
    "phase": "idle",
    "phase_label": "等待训练",
    "training_scope": "",
    "scope_mode": "",
    "started_at": None,
    "finished_at": None,
    "stage_progress_pct": 0,
    "display_progress_pct": 0,
    "task_index": 0,
    "task_total": 0,
    "estimated_total_seconds": None,
    "elapsed_seconds": 0,
    "remaining_seconds": None,
    "avg_seconds_per_task": None,
    "speed_text": "",
    "eta_text": "",
    "progress_pct": 0,
    "total": 0,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "current": None,
    "sample_count": None,
    "winner_model": "",
    "metric_text": "",
    "detail_lines": [],
    "message": "未启动预测训练",
    "logs": [],
    "updated_at": None,
}

_FORECAST_TIMING: dict[str, Any] = {
    "avg_seconds_per_task": 8.0,
}


class HotSkuItem(BaseModel):
    sku_key: str
    label: str = ""
    enabled: bool = True


class HotSkuSaveBody(BaseModel):
    items: list[HotSkuItem] = Field(default_factory=list)


def _forecast_status_push(
    phase: str,
    phase_label: str,
    line: str,
    **extra: Any,
) -> None:
    lines = list(_FORECAST_STATUS.get("detail_lines") or [])
    if line:
        lines.append(line)
    payload = {
        "phase": phase,
        "phase_label": phase_label,
        "message": phase_label,
        "detail_lines": lines[-8:],
        "updated_at": _now_cn_iso(),
    }
    payload.update(extra)
    _FORECAST_STATUS.update(payload)
    _refresh_forecast_eta()


def _fmt_seconds(seconds: Optional[float]) -> str:
    if seconds is None:
        return "预计时间计算中"
    sec = max(0, int(round(seconds)))
    if sec < 60:
        return f"{sec}秒"
    minutes, s = divmod(sec, 60)
    if minutes < 60:
        return f"{minutes}分{s:02d}秒"
    hours, m = divmod(minutes, 60)
    return f"{hours}小时{m:02d}分"


def _refresh_forecast_eta() -> None:
    started = _FORECAST_STATUS.get("started_at")
    now = _now_cn()
    elapsed = 0.0
    if started:
        try:
            elapsed = max(0.0, (now - _parse_status_dt(started)).total_seconds())
        except Exception:
            elapsed = 0.0
    total = int(_FORECAST_STATUS.get("total") or 0)
    processed = int(_FORECAST_STATUS.get("processed") or 0)
    progress = float(_FORECAST_STATUS.get("display_progress_pct") or _FORECAST_STATUS.get("progress_pct") or 0)
    avg = _FORECAST_STATUS.get("avg_seconds_per_task")
    if processed > 0 and elapsed > 0:
        avg = elapsed / processed
        _FORECAST_STATUS["avg_seconds_per_task"] = round(avg, 2)
    elif avg is None:
        avg = float(_FORECAST_TIMING.get("avg_seconds_per_task") or 8.0)
        _FORECAST_STATUS["avg_seconds_per_task"] = round(avg, 2)
    estimated_total = _FORECAST_STATUS.get("estimated_total_seconds")
    if total and avg:
        estimated_total = max(float(estimated_total or 0), float(avg) * total)
    remaining = None
    if total and avg:
        remaining = max(0.0, (total - processed) * float(avg))
        if progress > 0 and elapsed > 0:
            remaining = min(remaining, max(0.0, elapsed * (100.0 - progress) / progress))
    speed = 60.0 / float(avg) if avg else 0.0
    _FORECAST_STATUS.update({
        "elapsed_seconds": int(round(elapsed)),
        "estimated_total_seconds": int(round(estimated_total)) if estimated_total is not None else None,
        "remaining_seconds": int(round(remaining)) if remaining is not None else None,
        "speed_text": f"{speed:.1f} 任务/分钟" if speed else "",
        "eta_text": f"预计剩余 {_fmt_seconds(remaining)}" if remaining is not None else "预计时间计算中",
    })


def _forecast_stage_progress(fraction: float, label: Optional[str] = None) -> None:
    total = int(_FORECAST_STATUS.get("total") or 0)
    processed = int(_FORECAST_STATUS.get("processed") or 0)
    frac = max(0.0, min(1.0, float(fraction)))
    pct = int(((processed + frac) / total) * 100) if total else int(frac * 100)
    pct = max(int(_FORECAST_STATUS.get("display_progress_pct") or 0), min(99, pct))
    _FORECAST_STATUS.update({
        "stage_progress_pct": round(frac * 100, 1),
        "display_progress_pct": pct,
        "progress_pct": pct,
        "phase_label": label or _FORECAST_STATUS.get("phase_label") or "",
        "updated_at": _now_cn_iso(),
    })
    _refresh_forecast_eta()


_CN_TZ = ZoneInfo("Asia/Shanghai")


def _now_cn() -> datetime:
    return datetime.now(_CN_TZ)


def _now_cn_iso() -> str:
    """状态/进度接口返回的中国（北京）时间，带 +08:00 偏移。"""
    return _now_cn().replace(microsecond=0).isoformat()


def _parse_status_dt(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return _now_cn()
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CN_TZ)


def _today() -> date:
    return _now_cn().date()


def _default_date() -> date:
    return _today() - timedelta(days=1)


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


_PRICE_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _price_to_float(value: Any) -> Optional[float]:
    """price 为字符串：纯数字直接取，区间(如 5.2-5.8)取均值，含单位/杂质则提取数字；无法解析返回 None。"""
    if value is None:
        return None
    nums = _PRICE_NUM_RE.findall(str(value).strip())
    if not nums:
        return None
    try:
        vals = [float(n) for n in nums]
    except ValueError:
        return None
    return sum(vals) / len(vals) if vals else None


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _daterange_days(start_day: date, end_day: date) -> list[date]:
    out: list[date] = []
    cur = start_day
    while cur <= end_day:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _ensure_credentials() -> None:
    if not zg_cred.credentials_configured():
        raise HTTPException(
            status_code=400,
            detail="中农价格网账号未配置：请在「全国农产品价格 → 配置」填写手机号与密码，或在 backend/.env 设置 ZGNCPJGW_USERNAME / ZGNCPJGW_PASSWORD",
        )


def _friendly_crawl_error(exc: BaseException) -> str:
    if isinstance(exc, zg_cred.ZgncpjgwAuthError):
        return str(exc)
    msg = str(exc) or exc.__class__.__name__
    if zg_cred.is_auth_failure_message(msg):
        return msg
    if msg.startswith("登录失败："):
        inner = msg.replace("登录失败：", "", 1)
        if zg_cred.is_auth_failure_message(inner):
            return zg_cred.format_login_failure({"status": 40003, "message": inner})
    return msg


def _is_waf_body(body: str) -> bool:
    text_value = (body or "").strip().lower()
    if not text_value:
        return False
    if text_value.startswith("<html") or "acw_sc__v2" in text_value:
        return True
    return False


def _row_signature(item: dict[str, Any]) -> str:
    return "|".join(
        [
            str(item.get("goods_sn") or ""),
            str(item.get("spec") or ""),
            str(item.get("place") or ""),
            str(item.get("update_date") or ""),
        ]
    )


def _pause_range(lo_attr: str, hi_attr: str, slow: bool = False) -> tuple[float, float]:
    lo = float(getattr(settings, lo_attr))
    hi = float(getattr(settings, hi_attr))
    if hi < lo:
        lo, hi = hi, lo
    if not settings.zgncpjgw_polite_crawl:
        return 0.05, 0.12
    if slow:
        lo *= 4.0
        hi *= 8.0
    return lo, hi


async def _sleep_pause(lo_attr: str, hi_attr: str, slow: bool = False) -> None:
    lo, hi = _pause_range(lo_attr, hi_attr, slow=slow)
    if hi <= 0:
        return
    await asyncio.sleep(random.uniform(lo, hi) if hi > lo else lo)


class ZgncpjgwClient:
    """Playwright 引导 WAF cookie + httpx 调 API；会话失效时自动重新引导。"""

    def __init__(
        self,
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._bootstrap_lock = asyncio.Lock()
        self._username_override = (username or "").strip() or None
        self._password_override = password if password is not None else None

    def _login_username(self) -> str:
        return self._username_override or zg_cred.get_username()

    def _login_password(self) -> str:
        if self._password_override is not None:
            return self._password_override
        return zg_cred.get_password()

    async def close(self) -> None:
        async with self._bootstrap_lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def _reset(self) -> None:
        await self.close()

    async def _bootstrap(self) -> None:
        _ensure_credentials()
        base = (settings.zgncpjgw_base_url or "https://www.zgncpjgw.com").rstrip("/")
        try:
            cookies = await asyncio.wait_for(
                asyncio.to_thread(zg_cred.fetch_waf_cookies_sync),
                timeout=70.0,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError("过 WAF 超时（70 秒），请检查网络或稍后重试") from exc
        except ImportError as exc:
            raise RuntimeError(
                "未安装 playwright，请执行: pip install playwright && python -m playwright install chromium"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"过 WAF 失败：{exc}") from exc

        jar = httpx.Cookies()
        for item in cookies:
            jar.set(
                item.get("name", ""),
                item.get("value", ""),
                domain=item.get("domain") or "",
                path=item.get("path") or "/",
            )

        timeout = httpx.Timeout(45.0, connect=15.0)
        self._client = httpx.AsyncClient(
            timeout=timeout,
            cookies=jar,
            follow_redirects=True,
            trust_env=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Origin": base,
                "Referer": f"{base}/",
            },
        )
        login = await self._post_once(
            "user.login",
            {"username": self._login_username(), "password": self._login_password()},
        )
        login_err = zg_cred.format_login_failure(login)
        if login_err:
            await self._reset()
            if int(login.get("status") or 0) == 40003 or "密码" in login_err:
                raise zg_cred.ZgncpjgwAuthError(login_err)
            raise RuntimeError(login_err)

    async def ensure_ready(self) -> None:
        if self._client is not None:
            return
        async with self._bootstrap_lock:
            if self._client is None:
                await self._bootstrap()

    async def _post_once(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP 客户端未初始化")
        base = (settings.zgncpjgw_base_url or "https://www.zgncpjgw.com").rstrip("/")
        url = f"{base}/home/rest.php?method={method}"
        files = {key: (None, str(value if value is not None else "")) for key, value in params.items()}
        response = await self._client.post(url, files=files)
        body = response.text
        if _is_waf_body(body):
            raise RuntimeError("WAF_CHALLENGE")
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"非 JSON 响应：{body[:200]}") from exc
        if int(payload.get("status") or 0) == -1 and "登录" in str(payload.get("message") or ""):
            raise RuntimeError("SESSION_EXPIRED")
        return payload

    async def call(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        params = params or {}
        max_tries = max(1, int(settings.zgncpjgw_http_max_retries))
        base_wait = float(settings.zgncpjgw_http_retry_base_seconds)
        last_error: Optional[Exception] = None
        for attempt in range(max_tries):
            try:
                await self.ensure_ready()
                return await self._post_once(method, params)
            except RuntimeError as exc:
                last_error = exc
                msg = str(exc)
                if msg in {"WAF_CHALLENGE", "SESSION_EXPIRED"} or "非 JSON" in msg:
                    async with self._bootstrap_lock:
                        if self._client is not None:
                            await self._client.aclose()
                            self._client = None
                if attempt + 1 < max_tries:
                    await asyncio.sleep(base_wait * (1.6**attempt) + random.uniform(0.1, 0.4))
                    continue
                raise
        raise RuntimeError(str(last_error) if last_error else "请求失败")


def _normalize_api_row(
    item: dict[str, Any],
    *,
    crawl_day: date,
    district_id: int,
    district_name: str,
    cate_id: int,
    cate_name: str,
) -> dict[str, Any]:
    update_day = _parse_day(item.get("update_date"))
    return {
        "crawl_date": crawl_day,
        "district_id": district_id,
        "district_name": district_name or "",
        "cate_id": cate_id,
        "cate_name": cate_name or str(item.get("cate_name") or ""),
        "scate_name": str(item.get("scate_name") or ""),
        "goods_sn": str(item.get("goods_sn") or ""),
        "goods_name": str(item.get("goods_name") or ""),
        "spec": str(item.get("spec") or ""),
        "unit": str(item.get("unit") or ""),
        "place": str(item.get("place") or ""),
        "price": str(item.get("price") or ""),
        "update_date": update_day,
        "raw_json": json.dumps(item, ensure_ascii=False),
    }


def _is_deadlock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "1213" in msg or "deadlock" in msg


async def _upsert_rows(db: AsyncSession, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = text(
        f"""
        INSERT INTO `{_tbl()}` (
            crawl_date, district_id, district_name, cate_id, cate_name, scate_name,
            goods_sn, goods_name, spec, unit, place, price, update_date, raw_json
        ) VALUES (
            :crawl_date, :district_id, :district_name, :cate_id, :cate_name, :scate_name,
            :goods_sn, :goods_name, :spec, :unit, :place, :price, :update_date, :raw_json
        )
        ON DUPLICATE KEY UPDATE
            district_name = VALUES(district_name),
            cate_name = VALUES(cate_name),
            scate_name = VALUES(scate_name),
            goods_name = VALUES(goods_name),
            unit = VALUES(unit),
            price = VALUES(price),
            raw_json = VALUES(raw_json),
            updated_at = CURRENT_TIMESTAMP
        """
    )
    async with _DB_WRITE_LOCK:
        for attempt in range(_UPSERT_DEADLOCK_RETRIES):
            try:
                await db.execute(sql, rows)
                await db.commit()
                return len(rows)
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                if _is_deadlock_error(exc) and attempt + 1 < _UPSERT_DEADLOCK_RETRIES:
                    await asyncio.sleep(0.15 * (2**attempt) + random.uniform(0, 0.2))
                    continue
                raise
    return 0


async def _crawl_list_pages(
    client: ZgncpjgwClient,
    *,
    crawl_day: date,
    district_id: int,
    district_name: str,
    cate_id: int,
    cate_name: str,
    job: dict[str, Any],
    slow: bool = False,
) -> list[dict[str, Any]]:
    day_str = crawl_day.isoformat()
    collected: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    prev_page_signatures: Optional[frozenset[str]] = None

    for page in range(1, MAX_PAGES + 1):
        job.update(
            {
                "message": (
                    f"抓取 {day_str} {district_name or district_id} / "
                    f"{cate_name or cate_id} 第 {page} 页"
                ),
                "updated_at": _now_cn_iso(),
            }
        )
        payload = await client.call(
            "price.getList",
            {
                "district_id": district_id,
                "cate_id": cate_id,
                "page": page,
                "start_date": day_str,
                "end_date": day_str,
                "city": "",
            },
        )
        if int(payload.get("status") or 0) != 200:
            raise RuntimeError(f"price.getList 失败：{payload.get('message') or payload}")
        raw_rows = payload.get("data") or []
        if not isinstance(raw_rows, list) or not raw_rows:
            break

        page_signatures = frozenset(_row_signature(item) for item in raw_rows if isinstance(item, dict))
        if prev_page_signatures is not None and page_signatures == prev_page_signatures:
            break
        prev_page_signatures = page_signatures

        page_rows: list[dict[str, Any]] = []
        for item in raw_rows:
            if not isinstance(item, dict):
                continue
            sig = _row_signature(item)
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)
            page_rows.append(
                _normalize_api_row(
                    item,
                    crawl_day=crawl_day,
                    district_id=district_id,
                    district_name=district_name,
                    cate_id=cate_id,
                    cate_name=cate_name,
                )
            )
        if page_rows:
            async with SessionLocal() as db:
                await _upsert_rows(db, page_rows)
            collected.extend(page_rows)

        if page < MAX_PAGES:
            await _sleep_pause("zgncpjgw_page_pause_min", "zgncpjgw_page_pause_max", slow=slow)

    return collected


async def _fetch_districts(client: ZgncpjgwClient, district_id: Optional[int]) -> list[dict[str, Any]]:
    payload = await client.call("price.getDistrict", {})
    if int(payload.get("status") or 0) != 200:
        raise RuntimeError(f"price.getDistrict 失败：{payload.get('message') or payload}")
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        return []
    if district_id is not None:
        rows = [row for row in rows if str(row.get("id")) == str(district_id)]
    return [row for row in rows if isinstance(row, dict)]


async def _fetch_categories(
    client: ZgncpjgwClient,
    district_id: int,
    cate_id: Optional[int],
) -> list[dict[str, Any]]:
    payload = await client.call("price.getCategory", {"district_id": district_id})
    if int(payload.get("status") or 0) != 200:
        raise RuntimeError(f"price.getCategory 失败：{payload.get('message') or payload}")
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        return []
    if cate_id is not None:
        rows = [row for row in rows if str(row.get("id")) == str(cate_id)]
    return [row for row in rows if isinstance(row, dict)]


async def _crawl_district(
    client: ZgncpjgwClient,
    district: dict[str, Any],
    *,
    crawl_day: date,
    cate_id: Optional[int],
    slow: bool,
    job: dict[str, Any],
    progress: dict[str, int],
) -> list[dict[str, Any]]:
    did = int(district.get("id") or 0)
    dname = str(district.get("name") or "")
    categories = await _fetch_categories(client, did, cate_id)
    rows: list[dict[str, Any]] = []
    for idx, category in enumerate(categories):
        cid = int(category.get("id") or 0)
        cname = str(category.get("name") or "")
        rows.extend(
            await _crawl_list_pages(
                client,
                crawl_day=crawl_day,
                district_id=did,
                district_name=dname,
                cate_id=cid,
                cate_name=cname,
                job=job,
                slow=slow,
            )
        )
        progress["done"] += 1
        total = progress.get("total") or 0
        if total:
            job["progress"] = min(99, int(progress["done"] / total * 100))
        if idx + 1 < len(categories):
            await _sleep_pause("zgncpjgw_category_pause_min", "zgncpjgw_category_pause_max", slow=slow)
    return rows


async def _crawl_day(
    crawl_day: date,
    job: dict[str, Any],
    *,
    district_id: Optional[int] = None,
    cate_id: Optional[int] = None,
    only_district_ids: Optional[set[int]] = None,
    client: Optional[ZgncpjgwClient] = None,
    slow: bool = False,
    on_district_done: Optional[Any] = None,
) -> list[dict[str, Any]]:
    own_client = client is None
    client = client or ZgncpjgwClient()
    all_rows: list[dict[str, Any]] = []
    try:
        districts = await _fetch_districts(client, district_id)
        if only_district_ids is not None:
            districts = [d for d in districts if int(d.get("id") or 0) in only_district_ids]
        if not districts:
            raise RuntimeError("未获取到任何省级区域")
        district_categories: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        total_tasks = 0
        for district in districts:
            did = int(district.get("id") or 0)
            categories = await _fetch_categories(client, did, cate_id)
            district_categories.append((district, categories))
            total_tasks += len(categories)
        progress = {"done": 0, "total": total_tasks}
        concurrency = max(1, int(settings.zgncpjgw_crawl_concurrency))
        sem = asyncio.Semaphore(concurrency)

        async def _run_district(district: dict[str, Any]) -> list[dict[str, Any]]:
            async with sem:
                chunk = await _crawl_district(
                    client,
                    district,
                    crawl_day=crawl_day,
                    cate_id=cate_id,
                    slow=slow,
                    job=job,
                    progress=progress,
                )
                if on_district_done is not None:
                    dname = str(district.get("name") or district.get("id") or "")
                    maybe = on_district_done(dname, len(chunk))
                    if asyncio.iscoroutine(maybe):
                        await maybe
                return chunk

        chunks = await asyncio.gather(*[_run_district(district) for district, _ in district_categories])
        for chunk in chunks:
            all_rows.extend(chunk)
    finally:
        if own_client:
            await client.close()
    return all_rows


async def _existing_scope_dates_in_range(
    db: AsyncSession,
    start_day: date,
    end_day: date,
    district_id: Optional[int],
    cate_id: Optional[int],
) -> set[date]:
    clauses = ["crawl_date >= :start_day", "crawl_date <= :end_day"]
    params: dict[str, Any] = {"start_day": start_day, "end_day": end_day}
    if district_id is not None:
        clauses.append("district_id = :district_id")
        params["district_id"] = district_id
    if cate_id is not None:
        clauses.append("cate_id = :cate_id")
        params["cate_id"] = cate_id
    result = await db.execute(
        text(
            f"""
            SELECT DISTINCT crawl_date FROM `{_tbl()}`
            WHERE {' AND '.join(clauses)}
            """
        ),
        params,
    )
    out: set[date] = set()
    for row in result.fetchall():
        raw = row[0]
        if isinstance(raw, datetime):
            out.add(raw.date())
        elif isinstance(raw, date):
            out.add(raw)
    return out


def _expected_district_count() -> int:
    return max(1, int(settings.zgncpjgw_expected_districts))


def _expected_category_count() -> int:
    return max(1, int(settings.zgncpjgw_expected_categories))


def _backfill_province_units(missing_ids: set[int]) -> int:
    """单日待补「省」数量；空集合表示该日需抓全省。"""
    if missing_ids:
        return len(missing_ids)
    return _expected_district_count()


def _backfill_plan_province_total(day_plans: list[tuple[date, set[int], str]]) -> int:
    return sum(_backfill_province_units(missing_ids) for _day, missing_ids, _label in day_plans)


async def _complete_days_in_range(db: AsyncSession, start_day: date, end_day: date) -> set[date]:
    """全省 × 全类均已入库的日期视为完成，可整日跳过。"""
    need_d = _expected_district_count()
    need_c = _expected_category_count()
    result = await db.execute(
        text(
            f"""
            SELECT crawl_date FROM `{_tbl()}`
            WHERE crawl_date >= :start_day AND crawl_date <= :end_day
            GROUP BY crawl_date
            HAVING COUNT(DISTINCT district_id) >= :need_d
               AND COUNT(DISTINCT cate_id) >= :need_c
            """
        ),
        {"start_day": start_day, "end_day": end_day, "need_d": need_d, "need_c": need_c},
    )
    out: set[date] = set()
    for row in result.fetchall():
        raw = row[0]
        if isinstance(raw, datetime):
            out.add(raw.date())
        elif isinstance(raw, date):
            out.add(raw)
    return out


async def _complete_district_ids_by_day(
    db: AsyncSession, start_day: date, end_day: date
) -> dict[date, set[int]]:
    """按日返回已齐全（分类数达标）的 province id 集合。"""
    need_c = _expected_category_count()
    result = await db.execute(
        text(
            f"""
            SELECT crawl_date, district_id FROM `{_tbl()}`
            WHERE crawl_date >= :start_day AND crawl_date <= :end_day
            GROUP BY crawl_date, district_id
            HAVING COUNT(DISTINCT cate_id) >= :need_c
            """
        ),
        {"start_day": start_day, "end_day": end_day, "need_c": need_c},
    )
    out: dict[date, set[int]] = {}
    for row in result.fetchall():
        raw_day, raw_did = row[0], row[1]
        if isinstance(raw_day, datetime):
            day = raw_day.date()
        elif isinstance(raw_day, date):
            day = raw_day
        else:
            continue
        out.setdefault(day, set()).add(int(raw_did))
    return out


async def _ensure_forecast_table(db: AsyncSession) -> None:
    await db.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS `{FORECAST_TBL}` (
                `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                `sku_key` VARCHAR(512) NOT NULL,
                `district_id` INT NOT NULL DEFAULT 0,
                `district_name` VARCHAR(128) NOT NULL DEFAULT '',
                `scope` VARCHAR(24) NOT NULL DEFAULT 'national',
                `winner_model` VARCHAR(64) NOT NULL DEFAULT '',
                `forecast_json` LONGTEXT NOT NULL,
                `metrics_json` LONGTEXT NOT NULL,
                `sample_count` INT NOT NULL DEFAULT 0,
                `data_latest_date` DATE NULL,
                `trained_at` DATETIME NOT NULL,
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY `uq_zg_forecast_scope` (`sku_key`(255), `scope`, `district_id`),
                KEY `idx_zg_forecast_latest` (`data_latest_date`),
                KEY `idx_zg_forecast_district` (`district_id`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
    )
    await db.commit()


async def _ensure_hot_sku_table(db: AsyncSession) -> None:
    await db.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS `{HOT_SKU_TBL}` (
                `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                `sku_key` VARCHAR(512) NOT NULL,
                `label` VARCHAR(255) NOT NULL DEFAULT '',
                `sort_order` INT NOT NULL DEFAULT 0,
                `enabled` TINYINT(1) NOT NULL DEFAULT 1,
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY `uq_zg_hot_sku` (`sku_key`(255)),
                KEY `idx_zg_hot_sku_enabled` (`enabled`, `sort_order`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
    )
    await db.commit()


def _forecast_feature(values: list[float], idx: int, day: date) -> list[float]:
    last = values[idx - 1]
    lag7 = values[idx - 7] if idx >= 7 else last
    lag14 = values[idx - 14] if idx >= 14 else lag7
    lag30 = values[idx - 30] if idx >= 30 else lag14
    tail7 = values[max(0, idx - 7):idx]
    tail14 = values[max(0, idx - 14):idx]
    tail30 = values[max(0, idx - 30):idx]
    return [
        last,
        lag7,
        lag14,
        lag30,
        _stat_mean(tail7) if tail7 else last,
        _stat_mean(tail14) if tail14 else last,
        _stat_mean(tail30) if tail30 else last,
        max(tail14) - min(tail14) if len(tail14) > 1 else 0.0,
        math.sin(2 * math.pi * day.weekday() / 7),
        math.cos(2 * math.pi * day.weekday() / 7),
        math.sin(2 * math.pi * day.month / 12),
        math.cos(2 * math.pi * day.month / 12),
    ]


def _series_values(series: list[dict[str, Any]]) -> tuple[list[date], list[float]]:
    days: list[date] = []
    vals: list[float] = []
    for row in series:
        d = _parse_day(row.get("date"))
        v = _price_to_float(row.get("avg_price"))
        if d and v is not None and v > 0:
            days.append(d)
            vals.append(float(v))
    return days, vals


def _forecast_rows_from_values(last_day: date, values: list[float], horizon: int, *, confidence: float = 0.78) -> list[dict[str, Any]]:
    clean = [v for v in values if v > 0]
    baseline = _stat_mean(clean[-30:]) if clean else 1.0
    sigma = 0.04
    if len(clean) > 3 and baseline:
        rets = [abs(b - a) / a for a, b in zip(clean[:-1], clean[1:]) if a > 0]
        if rets:
            sigma = min(0.22, max(0.025, _stat_mean(rets[-30:])))
    rows: list[dict[str, Any]] = []
    prev = clean[-1] if clean else baseline
    for idx, yhat in enumerate(values[-horizon:], 1):
        band = min(0.35, max(0.04, sigma * math.sqrt(idx) * 1.28))
        rows.append(
            {
                "date": (last_day + timedelta(days=idx)).isoformat(),
                "yhat": round(max(0.01, yhat), 3),
                "yhat_lower": round(max(0.01, yhat * (1 - band)), 3),
                "yhat_upper": round(max(0.01, yhat * (1 + band)), 3),
                "lower": round(max(0.01, yhat * (1 - band)), 3),
                "upper": round(max(0.01, yhat * (1 + band)), 3),
                "confidence": round(max(0.42, min(0.94, confidence - 0.012 * idx)), 3),
                "trend": "up" if yhat > prev * 1.01 else "down" if yhat < prev * 0.99 else "flat",
            }
        )
        prev = yhat
    return rows


def _moving_forecast(series: list[dict[str, Any]], horizon: int) -> list[dict[str, Any]]:
    days, values = _series_values(series)
    if not days or not values:
        return []
    window = values[:]
    out: list[float] = []
    for _ in range(horizon):
        tail7 = window[-7:] if len(window) >= 7 else window
        tail30 = window[-30:] if len(window) >= 30 else window
        momentum = (window[-1] - window[-7]) / window[-7] if len(window) >= 7 and window[-7] else 0.0
        pred = _stat_mean(tail7) * 0.55 + _stat_mean(tail30) * 0.45
        pred *= 1 + max(-0.06, min(0.06, momentum)) * 0.25
        pred = max(0.01, pred)
        out.append(pred)
        window.append(pred)
    return _forecast_rows_from_values(days[-1], values + out, horizon, confidence=0.7)


def _xgboost_forecast(series: list[dict[str, Any]], horizon: int) -> list[dict[str, Any]]:
    import numpy as np
    from xgboost import XGBRegressor

    days, values = _series_values(series)
    if len(values) < 45:
        return []
    x_train = []
    y_train = []
    for idx in range(30, len(values)):
        x_train.append(_forecast_feature(values, idx, days[idx]))
        y_train.append(values[idx])
    if len(x_train) < 12:
        return []
    model = XGBRegressor(
        n_estimators=120,
        max_depth=3,
        learning_rate=0.06,
        subsample=0.92,
        colsample_bytree=0.92,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=1,
    )
    model.fit(np.array(x_train, dtype=float), np.array(y_train, dtype=float))
    rolling = values[:]
    out: list[float] = []
    for step in range(1, horizon + 1):
        next_day = days[-1] + timedelta(days=step)
        pred = float(model.predict(np.array([_forecast_feature(rolling, len(rolling), next_day)], dtype=float))[0])
        recent = rolling[-60:] if len(rolling) >= 60 else rolling
        lo = max(0.01, min(recent) * 0.75)
        hi = max(recent) * 1.35
        pred = min(hi, max(lo, pred))
        out.append(pred)
        rolling.append(pred)
    return _forecast_rows_from_values(days[-1], values + out, horizon, confidence=0.82)


def _anchored_rows(series: list[dict[str, Any]], horizon: int) -> list[dict[str, Any]]:
    from routers.xinfadi import _anchored_forecast, _normalize_forecast_row

    fc = _anchored_forecast(series, horizon)
    return [_normalize_forecast_row(row) for row in (fc.get("ensemble") or [])] if fc else []


def _one_step_prediction(model_name: str, train_series: list[dict[str, Any]]) -> Optional[float]:
    if model_name == "moving_baseline":
        rows = _moving_forecast(train_series, 1)
    elif model_name == "anchored_revert":
        rows = _anchored_rows(train_series, 1)
    elif model_name == "xgboost":
        rows = _xgboost_forecast(train_series, 1)
    else:
        rows = []
    return _price_to_float(rows[0].get("yhat")) if rows else None


def _backtest_model(series: list[dict[str, Any]], model_name: str, window: int = 30) -> dict[str, Any]:
    _days, values = _series_values(series)
    n = len(values)
    if model_name == "xgboost":
        holdout = min(max(7, window), max(1, n - 45))
        if n - holdout < 45:
            return {"model": model_name, "mape": None, "mae": None, "hit_rate": None, "backtest_days": 0}
        rows = _xgboost_forecast(series[: n - holdout], holdout)
        preds = [_price_to_float(row.get("yhat")) for row in rows]
        actuals = values[n - holdout:]
        prevs = values[n - holdout - 1: n - 1]
        pairs = [(p, a, prev) for p, a, prev in zip(preds, actuals, prevs) if p is not None and a > 0]
        if not pairs:
            return {"model": model_name, "mape": None, "mae": None, "hit_rate": None, "backtest_days": 0}
        errs = [abs(float(p) - a) / a for p, a, _prev in pairs]
        abs_errs = [abs(float(p) - a) for p, a, _prev in pairs]
        hits = sum(1 for p, a, prev in pairs if (float(p) - prev >= 0) == (a - prev >= 0))
        return {
            "model": model_name,
            "mape": round(_stat_mean(errs) * 100, 2),
            "mae": round(_stat_mean(abs_errs), 3),
            "hit_rate": round(hits / len(pairs) * 100, 1),
            "backtest_days": len(pairs),
        }
    start = max(30 if model_name == "xgboost" else 8, n - window)
    errs: list[float] = []
    abs_errs: list[float] = []
    hits = 0
    total = 0
    for idx in range(start, n):
        pred = _one_step_prediction(model_name, series[:idx])
        actual = values[idx]
        prev = values[idx - 1] if idx > 0 else actual
        if pred is None or actual <= 0:
            continue
        errs.append(abs(pred - actual) / actual)
        abs_errs.append(abs(pred - actual))
        if (pred - prev >= 0) == (actual - prev >= 0):
            hits += 1
        total += 1
    if not errs:
        return {"model": model_name, "mape": None, "mae": None, "hit_rate": None, "backtest_days": 0}
    return {
        "model": model_name,
        "mape": round(_stat_mean(errs) * 100, 2),
        "mae": round(_stat_mean(abs_errs), 3),
        "hit_rate": round(hits / total * 100, 1) if total else 0,
        "backtest_days": total,
    }


def _reliability_from_metrics(sample_count: int, mape: Optional[float], hit_rate: Optional[float]) -> tuple[str, str, str]:
    if sample_count < 30:
        return "low", "谨慎参考", f"有效样本仅 {sample_count} 天（<30），数据不足"
    if mape is None or hit_rate is None:
        return "low", "谨慎参考", "回测样本不足，可靠性未知"
    if hit_rate < 45:
        return "low", "谨慎参考", f"方向命中率 {hit_rate}% 低于随机水平"
    if sample_count >= 120 and mape <= 12 and hit_rate >= 55:
        return "high", "高可靠", f"样本 {sample_count} 天，回测误差 {mape}%，方向命中 {hit_rate}%"
    if sample_count >= 60 and mape <= 25:
        return "mid", "中等可靠", f"样本 {sample_count} 天，回测误差 {mape}%，方向命中 {hit_rate}%"
    return "low", "谨慎参考", f"样本 {sample_count} 天，回测误差 {mape}%，方向命中 {hit_rate}%"


async def _forecast_series_for_scope(
    db: AsyncSession,
    sku_key: str,
    district_id: Optional[int] = None,
) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (口径名, 标签, 清洗后序列, 原始序列)。
    原始序列=未过质量规则的逐日中位价；省份口径才有逐行原始，全国口径(日聚合已清洗)原始=清洗后。"""
    name, spec, unit, cate_id, scate = split_sku_key(sku_key)
    if not name:
        return "", "", [], []
    if district_id is None:
        result = await db.execute(
            text(
                f"""
                SELECT crawl_date, median_price
                FROM `{AGG_TBL}`
                WHERE sku_key = :sk AND median_price > 0
                ORDER BY crawl_date
                """
            ),
            {"sk": sku_key},
        )
        rows = [{"date": _fmt_day(r.crawl_date), "avg_price": float(r.median_price)} for r in result.fetchall()]
        # 全国口径数据源是已清洗的日聚合，无逐行原始可还原，原始=清洗后
        return "全国", _sku_label(name, spec, unit) + (f" · {scate}" if scate else ""), rows, list(rows)
    result = await db.execute(
        text(
            f"""
            SELECT crawl_date, district_name, price
            FROM `{_tbl()}`
            WHERE goods_name = :g AND spec = :s AND unit = :u
              AND cate_id = :c AND scate_name = :sc AND district_id = :did
            ORDER BY crawl_date
            """
        ),
        {"g": name, "s": spec, "u": unit, "c": cate_id, "sc": scate, "did": district_id},
    )
    raw_rows = list(result.fetchall())
    raw_days = [row.crawl_date for row in raw_rows if row.crawl_date]
    quality_map = await quality_map_for_days(db, raw_days, sync_missing=False)
    buckets: dict[str, list[float]] = defaultdict(list)
    raw_buckets: dict[str, list[float]] = defaultdict(list)
    district_name = ""
    for r in raw_rows:
        d = _fmt_day(r.crawl_date)
        v0 = _price_to_float(r.price)
        if d and v0 is not None:
            raw_buckets[d].append(v0)  # 原始：不剔脏、不校正
            district_name = district_name or (r.district_name or "")
        quality_meta = quality_map.get((r.crawl_date, sku_key, r.district_name or ""))
        if should_exclude_quality(quality_meta, "strict"):
            continue
        v = v0
        if quality_meta and quality_meta.get("corrected_price") is not None:
            v = float(quality_meta["corrected_price"])
        if v is None or not d:
            continue
        buckets[d].append(v)
    rows = [{"date": d, "avg_price": round(_stat_median(vals), 4)} for d, vals in sorted(buckets.items()) if vals]
    raw_series = [{"date": d, "avg_price": round(_stat_median(vals), 4)} for d, vals in sorted(raw_buckets.items()) if vals]
    label = _sku_label(name, spec, unit) + (f" · {scate}" if scate else "")
    return district_name or str(district_id), label, rows, raw_series


async def _raw_forecast_series_day_count(
    db: AsyncSession,
    sku_key: str,
    district_id: Optional[int] = None,
) -> int:
    """统计未过质量规则前的原始可用天数，用于向用户解释 0 样本原因。"""
    name, spec, unit, cate_id, scate = split_sku_key(sku_key)
    if not name:
        return 0
    if district_id is None:
        res = await db.execute(
            text(
                f"""
                SELECT COUNT(DISTINCT crawl_date) AS n
                FROM `{AGG_TBL}`
                WHERE sku_key = :sk AND median_price > 0
                """
            ),
            {"sk": sku_key},
        )
        return int(res.scalar() or 0)
    res = await db.execute(
        text(
            f"""
            SELECT COUNT(DISTINCT crawl_date) AS n
            FROM `{_tbl()}`
            WHERE goods_name = :g AND spec = :s AND unit = :u
              AND cate_id = :c AND scate_name = :sc AND district_id = :did
            """
        ),
        {"g": name, "s": spec, "u": unit, "c": cate_id, "sc": scate, "did": district_id},
    )
    return int(res.scalar() or 0)


async def _recommended_hot_skus(db: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    latest = await _latest_agg_date(db)
    if latest is None:
        return []
    res = await db.execute(
        text(
            f"""
            SELECT goods_name, spec, unit, cate_id, cate_name, scate_name, province_count
            FROM `{AGG_TBL}`
            WHERE crawl_date = :d AND median_price > 0
            ORDER BY province_count DESC, sample_count DESC, goods_name
            LIMIT :lim
            """
        ),
        {"d": latest, "lim": limit},
    )
    return _attach_sku_labels([
        {"goods_name": r.goods_name, "spec": r.spec, "unit": r.unit,
         "cate_id": r.cate_id, "cate_name": r.cate_name, "scate_name": r.scate_name}
        for r in res.fetchall() if r.goods_name
    ])


async def _configured_hot_skus(db: AsyncSession, only_enabled: bool = True) -> list[dict[str, Any]]:
    await _ensure_hot_sku_table(db)
    where = "WHERE enabled = 1" if only_enabled else ""
    res = await db.execute(
        text(
            f"""
            SELECT sku_key, label, enabled, sort_order
            FROM `{HOT_SKU_TBL}` {where}
            ORDER BY sort_order ASC, id ASC
            """
        )
    )
    return [
        {
            "sku_key": str(r.sku_key or ""),
            "label": str(r.label or r.sku_key or ""),
            "enabled": bool(r.enabled),
            "sort_order": int(r.sort_order or 0),
        }
        for r in res.fetchall()
        if r.sku_key
    ]


async def _all_forecast_skus(db: AsyncSession, limit: int = 50000) -> list[str]:
    latest = await _latest_agg_date(db)
    if latest is None:
        return []
    res = await db.execute(
        text(
            f"""
            SELECT sku_key
            FROM `{AGG_TBL}`
            WHERE crawl_date = :d AND median_price > 0
            ORDER BY province_count DESC, sample_count DESC, goods_name
            LIMIT :lim
            """
        ),
        {"d": latest, "lim": limit},
    )
    return [str(r.sku_key or "") for r in res.fetchall() if r.sku_key]


async def _estimate_all_forecast_tasks(db: AsyncSession) -> dict[str, Any]:
    latest = await _latest_agg_date(db)
    if latest is None:
        return {
            "sku_count": 0,
            "task_count": 0,
            "avg_seconds_per_task": round(float(_FORECAST_TIMING.get("avg_seconds_per_task") or 8.0), 2),
            "estimated_total_seconds": 0,
            "estimated_total_text": "0秒",
        }
    res = await db.execute(
        text(
            f"""
            SELECT COUNT(*) AS sku_count, COALESCE(SUM(province_count), 0) AS province_tasks
            FROM `{AGG_TBL}`
            WHERE crawl_date = :d AND median_price > 0
            """
        ),
        {"d": latest},
    )
    row = res.fetchone()
    sku_count = int(row.sku_count or 0) if row else 0
    task_count = sku_count + (int(row.province_tasks or 0) if row else 0)
    avg = float(_FORECAST_TIMING.get("avg_seconds_per_task") or 8.0)
    estimated = int(round(task_count * avg))
    return {
        "sku_count": sku_count,
        "task_count": task_count,
        "avg_seconds_per_task": round(avg, 2),
        "estimated_total_seconds": estimated,
        "estimated_total_text": _fmt_seconds(estimated),
    }


async def _estimate_forecast_tasks(db: AsyncSession, sku_keys: list[str], district_limit: int = 40) -> dict[str, Any]:
    scopes_by_sku: list[dict[str, Any]] = []
    total_tasks = 0
    for sku_key in sku_keys:
        districts = await _district_ids_for_sku(db, sku_key, limit=district_limit)
        task_count = 1 + len(districts)
        total_tasks += task_count
        scopes_by_sku.append({"sku_key": sku_key, "district_count": len(districts), "task_count": task_count})
    avg = float(_FORECAST_TIMING.get("avg_seconds_per_task") or 8.0)
    estimated = int(round(total_tasks * avg))
    return {
        "sku_count": len(sku_keys),
        "task_count": total_tasks,
        "avg_seconds_per_task": round(avg, 2),
        "estimated_total_seconds": estimated,
        "estimated_total_text": _fmt_seconds(estimated),
        "scopes_by_sku": scopes_by_sku,
    }


async def _train_one_forecast_snapshot(
    db: AsyncSession,
    sku_key: str,
    *,
    district_id: Optional[int],
    horizon: int = 14,
) -> dict[str, Any]:
    await _ensure_forecast_table(db)
    scope_label = "全国" if district_id is None else f"省份 {district_id}"
    _forecast_stage_progress(0.05, "读取历史价格序列")
    _forecast_status_push(
        "read_data",
        "读取历史价格序列",
        f"读取历史序列：{scope_label} · 正在汇总每日中位价",
        current=f"{sku_key} / {scope_label}",
    )
    district_name, label, series, _raw_series = await _forecast_series_for_scope(db, sku_key, district_id)
    scope = "province" if district_id is not None else "national"
    display_scope = district_name if scope == "province" else "全国"
    data_latest = _parse_day(series[-1]["date"]) if series else None
    sample_count = len(series)
    _forecast_stage_progress(0.20, "构造预测特征")
    _forecast_status_push(
        "features",
        "构造预测特征",
        f"读取完成：{display_scope} · 有效样本 {sample_count} 天 · 最新数据 {data_latest.isoformat() if data_latest else '—'}",
        current=f"{label} / {display_scope}",
        sample_count=sample_count,
    )
    if sample_count < 30:
        grade, grade_label, reason = _reliability_from_metrics(sample_count, None, None)
        raw_days = await _raw_forecast_series_day_count(db, sku_key, district_id)
        quality_hint = await build_forecast_sample_hint(
            db,
            sku_key,
            eligible_days=sample_count,
            raw_days=raw_days,
            scope_label=f"{display_scope}口径",
        )
        user_reason = quality_hint or reason
        _forecast_stage_progress(0.84, "样本不足，写入谨慎参考快照")
        _forecast_status_push(
            "insufficient",
            "样本不足，写入谨慎参考快照",
            f"样本校验：有效样本 {sample_count} 天（<30），不生成正式预测曲线",
            sample_count=sample_count,
            winner_model="insufficient",
            metric_text=user_reason,
        )
        payload = {
            "status": "insufficient",
            "product": label,
            "sku_key": sku_key,
            "scope": scope,
            "district_id": district_id or 0,
            "district_name": district_name if scope == "province" else "",
            "history": [{"date": r["date"], "price": round(float(r["avg_price"]), 3)} for r in series[-60:]],
            "ensemble": [],
            "message": user_reason,
            "quality_hint": quality_hint,
            "raw_sample_count": raw_days,
        }
        metrics = {
            "reliability": grade,
            "reliability_label": grade_label,
            "reliability_reason": user_reason,
            "sample_count": sample_count,
            "models": [],
        }
        winner_model = "insufficient"
    else:
        _forecast_stage_progress(0.35, "评估基线模型")
        _forecast_status_push(
            "train_baseline",
            "评估基线模型",
            f"模型评估：移动均值基线 / 锚定均值回归 · 样本 {sample_count} 天",
            sample_count=sample_count,
        )
        candidates: dict[str, list[dict[str, Any]]] = {
            "moving_baseline": _moving_forecast(series, horizon),
            "anchored_revert": _anchored_rows(series, horizon),
        }
        if sample_count >= 45:
            try:
                _forecast_stage_progress(0.52, "训练 XGBoost 模型")
                _forecast_status_push(
                    "train_xgboost",
                    "训练 XGBoost 模型",
                    f"XGBoost：构造滞后/滚动窗口特征 · 样本 {sample_count} 天",
                    sample_count=sample_count,
                )
                candidates["xgboost"] = await asyncio.to_thread(_xgboost_forecast, series, horizon)
            except Exception as exc:  # noqa: BLE001
                candidates["xgboost"] = []
                _forecast_stage_progress(0.68, "XGBoost 训练跳过")
                _forecast_status_push(
                    "train_xgboost",
                    "XGBoost 训练跳过",
                    f"XGBoost：训练失败已跳过（{str(exc)[:80]}）",
                    sample_count=sample_count,
                )
        else:
            _forecast_stage_progress(0.68, "XGBoost 样本校验")
            _forecast_status_push(
                "train_xgboost",
                "XGBoost 样本校验",
                f"XGBoost：样本不足 45 天，已跳过 · 当前 {sample_count} 天",
                sample_count=sample_count,
            )
        _forecast_stage_progress(0.80, "滚动回测选择冠军模型")
        _forecast_status_push(
            "backtest",
            "滚动回测选择冠军模型",
            "回测：用最近窗口模拟历史预测，比较误差与方向命中率",
            sample_count=sample_count,
        )
        model_metrics = [
            _backtest_model(series, name, window=min(30, max(14, sample_count // 4)))
            for name, rows in candidates.items()
            if rows
        ]
        valid_metrics = [m for m in model_metrics if m.get("mape") is not None]
        if valid_metrics:
            winner = sorted(valid_metrics, key=lambda m: (float(m.get("mape") or 9999), -float(m.get("hit_rate") or 0)))[0]
            winner_model = str(winner["model"])
        else:
            winner_model = "anchored_revert" if candidates.get("anchored_revert") else "moving_baseline"
            winner = {"mape": None, "hit_rate": None, "mae": None, "backtest_days": 0}
        metric_text = (
            f"回测误差 {winner.get('mape')}% · 方向命中 {winner.get('hit_rate')}%"
            if winner.get("mape") is not None
            else "回测样本不足，使用稳健兜底模型"
        )
        _forecast_status_push(
            "select_winner",
            "冠军模型已选择",
            f"冠军模型：{winner_model} · {metric_text}",
            sample_count=sample_count,
            winner_model=winner_model,
            metric_text=metric_text,
        )
        ens = candidates.get(winner_model) or []
        grade, grade_label, reason = _reliability_from_metrics(sample_count, winner.get("mape"), winner.get("hit_rate"))
        payload = {
            "status": "ok",
            "product": label,
            "sku_key": sku_key,
            "scope": scope,
            "district_id": district_id or 0,
            "district_name": district_name if scope == "province" else "",
            "anchor_price": round(float(series[-1]["avg_price"]), 3),
            "anchor_date": series[-1]["date"],
            "history": [{"date": r["date"], "price": round(float(r["avg_price"]), 3)} for r in series[-60:]],
            "ensemble": ens,
            "models": candidates,
            "winner_model": winner_model,
            "method": "本地 AutoML：XGBoost + 锚定均值回归 + 移动均值基线，滚动回测自动选冠军模型",
        }
        metrics = {
            "reliability": grade,
            "reliability_label": grade_label,
            "reliability_reason": reason,
            "sample_count": sample_count,
            "winner_model": winner_model,
            "mape": winner.get("mape"),
            "mae": winner.get("mae"),
            "hit_rate": winner.get("hit_rate"),
            "backtest_days": winner.get("backtest_days"),
            "models": model_metrics,
        }

    now = _now_cn()
    _forecast_stage_progress(0.92, "写入预测快照")
    await db.execute(
        text(
            f"""
            INSERT INTO `{FORECAST_TBL}`
              (sku_key, district_id, district_name, scope, winner_model, forecast_json, metrics_json, sample_count, data_latest_date, trained_at)
            VALUES
              (:sku_key, :district_id, :district_name, :scope, :winner_model, :forecast_json, :metrics_json, :sample_count, :data_latest_date, :trained_at)
            ON DUPLICATE KEY UPDATE
              district_name=VALUES(district_name),
              winner_model=VALUES(winner_model),
              forecast_json=VALUES(forecast_json),
              metrics_json=VALUES(metrics_json),
              sample_count=VALUES(sample_count),
              data_latest_date=VALUES(data_latest_date),
              trained_at=VALUES(trained_at)
            """
        ),
        {
            "sku_key": sku_key,
            "district_id": int(district_id or 0),
            "district_name": district_name if scope == "province" else "",
            "scope": scope,
            "winner_model": winner_model,
            "forecast_json": json.dumps(payload, ensure_ascii=False),
            "metrics_json": json.dumps(metrics, ensure_ascii=False),
            "sample_count": sample_count,
            "data_latest_date": data_latest,
            "trained_at": now,
        },
    )
    await db.commit()
    _forecast_stage_progress(0.98, "写入预测快照")
    _forecast_status_push(
        "write_snapshot",
        "写入预测快照",
        f"写入预测快照：{display_scope} · {winner_model} · {now.isoformat(timespec='minutes')}",
        sample_count=sample_count,
        winner_model=winner_model,
        metric_text=_FORECAST_STATUS.get("metric_text") or "",
    )
    return {"sku_key": sku_key, "scope": scope, "district_id": district_id or 0, "status": payload["status"], "winner_model": winner_model}


async def _popular_forecast_skus(db: AsyncSession, explicit: Optional[list[str]] = None, limit: int = 20) -> list[str]:
    explicit_keys = [k for k in (explicit or []) if str(k or "").strip()]
    seen: set[str] = set()
    out: list[str] = []
    for key in explicit_keys:
        if key not in seen:
            out.append(key)
            seen.add(key)
    latest = await _latest_agg_date(db)
    if latest is None:
        return out[:limit]
    res = await db.execute(
        text(
            f"""
            SELECT sku_key FROM `{AGG_TBL}`
            WHERE crawl_date = :d AND median_price > 0
            ORDER BY province_count DESC, sample_count DESC, goods_name
            LIMIT :lim
            """
        ),
        {"d": latest, "lim": limit},
    )
    for row in res.fetchall():
        key = str(row.sku_key or "")
        if key and key not in seen:
            out.append(key)
            seen.add(key)
    return out[:limit]


async def _district_ids_for_sku(db: AsyncSession, sku_key: str, limit: int = 12) -> list[tuple[int, str]]:
    name, spec, unit, cate_id, scate = split_sku_key(sku_key)
    if not name:
        return []
    latest = await _latest_agg_date(db)
    if latest is None:
        return []
    res = await db.execute(
        text(
            f"""
            SELECT district_id, district_name, COUNT(*) AS c
            FROM `{_tbl()}`
            WHERE crawl_date = :d AND goods_name = :g AND spec = :s AND unit = :u AND cate_id = :c AND scate_name = :sc
            GROUP BY district_id, district_name
            ORDER BY district_id
            LIMIT :lim
            """
        ),
        {"d": latest, "g": name, "s": spec, "u": unit, "c": cate_id, "sc": scate, "lim": limit},
    )
    return [(int(r.district_id), str(r.district_name or r.district_id)) for r in res.fetchall() if r.district_id is not None]


async def _train_forecast_batch(
    explicit_sku_keys: Optional[list[str]] = None,
    *,
    limit: int = 20,
    include_popular: bool = True,
    district_limit: int = 12,
    scope_mode: str = "popular_batch",
    single_district_id: Optional[int] = None,
) -> None:
    explicit_clean = [str(k or "").strip() for k in (explicit_sku_keys or []) if str(k or "").strip()]
    if scope_mode == "single_current":
        training_scope = "当前SKU · 当前省份/全国口径"
    elif scope_mode == "all_batch":
        training_scope = "全量SKU · 全国及有数据省份"
    elif explicit_clean and not include_popular:
        training_scope = "当前SKU · 全国及有数据省份"
    else:
        training_scope = "客户配置热门SKU · 全国及有数据省份"
    _FORECAST_STATUS.update({
        "running": True,
        "finished": False,
        "status": "running",
        "phase": "prepare",
        "phase_label": "准备训练任务",
        "training_scope": training_scope,
        "scope_mode": scope_mode,
        "started_at": _now_cn_iso(),
        "finished_at": None,
        "stage_progress_pct": 0,
        "display_progress_pct": 0,
        "task_index": 0,
        "task_total": 0,
        "estimated_total_seconds": None,
        "elapsed_seconds": 0,
        "remaining_seconds": None,
        "avg_seconds_per_task": float(_FORECAST_TIMING.get("avg_seconds_per_task") or 8.0),
        "speed_text": "",
        "eta_text": "预计时间计算中",
        "progress_pct": 0,
        "total": 0,
        "processed": 0,
        "success": 0,
        "failed": 0,
        "current": None,
        "sample_count": None,
        "winner_model": "",
        "metric_text": "",
        "detail_lines": [f"训练范围：{training_scope}"],
        "message": "正在准备预测训练任务…",
        "logs": [],
        "updated_at": _now_cn_iso(),
    })
    async with SessionLocal() as db:
        await _ensure_forecast_table(db)
        if scope_mode == "single_current":
            sku_keys = explicit_clean[:1]
        elif scope_mode == "all_batch":
            sku_keys = await _all_forecast_skus(db, limit=50000)
        elif include_popular:
            configured = await _configured_hot_skus(db, only_enabled=True)
            if configured:
                sku_keys = [x["sku_key"] for x in configured[:limit]]
            else:
                sku_keys = await _popular_forecast_skus(db, explicit_clean, limit=limit)
        else:
            seen: set[str] = set()
            sku_keys = []
            for key in explicit_clean:
                if key and key not in seen:
                    sku_keys.append(key)
                    seen.add(key)
            sku_keys = sku_keys[:limit]
        tasks: list[tuple[str, Optional[int]]] = []
        for sku_key in sku_keys:
            if scope_mode == "single_current":
                tasks.append((sku_key, single_district_id))
            else:
                tasks.append((sku_key, None))
                for did, _dname in await _district_ids_for_sku(db, sku_key, limit=district_limit):
                    tasks.append((sku_key, did))
        avg = float(_FORECAST_TIMING.get("avg_seconds_per_task") or 8.0)
        _FORECAST_STATUS.update({
            "estimated_total_seconds": int(round(len(tasks) * avg)),
            "task_total": len(tasks),
            "total": len(tasks),
        })
        _forecast_status_push(
            "prepare",
            "训练任务已生成",
            f"任务清单：{len(sku_keys)} 个 SKU · {len(tasks)} 个全国/省份口径",
            total=len(tasks),
            task_total=len(tasks),
            training_scope=training_scope,
        )
        logs: list[str] = []
        for idx, (sku_key, district_id) in enumerate(tasks, 1):
            _FORECAST_STATUS.update({
                "current": f"{sku_key} / {'全国' if district_id is None else district_id}",
                "processed": idx - 1,
                "task_index": idx,
                "progress_pct": int((idx - 1) / len(tasks) * 100) if tasks else 100,
                "display_progress_pct": int((idx - 1) / len(tasks) * 100) if tasks else 100,
                "stage_progress_pct": 0,
                "phase": "read_data",
                "phase_label": "读取历史价格序列",
                "message": f"预测训练中：已完成 {idx - 1}/{len(tasks)}",
                "updated_at": _now_cn_iso(),
            })
            task_start = _now_cn()
            try:
                result = await _train_one_forecast_snapshot(db, sku_key, district_id=district_id)
                _FORECAST_STATUS["success"] = int(_FORECAST_STATUS.get("success") or 0) + 1
                logs.append(f"OK {result['scope']} {result['district_id']} {result['winner_model']}")
            except Exception as exc:  # noqa: BLE001
                _FORECAST_STATUS["failed"] = int(_FORECAST_STATUS.get("failed") or 0) + 1
                logs.append(f"WARN {sku_key} / {district_id or '全国'}：{str(exc)[:160]}")
            duration = max(0.1, (_now_cn() - task_start).total_seconds())
            prev_avg = float(_FORECAST_TIMING.get("avg_seconds_per_task") or duration)
            new_avg = prev_avg * 0.75 + duration * 0.25
            _FORECAST_TIMING["avg_seconds_per_task"] = round(new_avg, 2)
            _FORECAST_STATUS.update({
                "logs": logs[-100:],
                "processed": idx,
                "display_progress_pct": int(idx / len(tasks) * 100) if tasks else 100,
                "progress_pct": int(idx / len(tasks) * 100) if tasks else 100,
                "avg_seconds_per_task": round(new_avg, 2),
            })
            _refresh_forecast_eta()
        if not tasks:
            _forecast_status_push("completed", "没有可训练任务", "没有找到可训练的 SKU 或省份数据", progress_pct=100)
    final_line = f"训练完成：成功 {_FORECAST_STATUS.get('success') or 0} · 失败 {_FORECAST_STATUS.get('failed') or 0}"
    final_lines = list(_FORECAST_STATUS.get("detail_lines") or [])
    final_lines.append(final_line)
    _FORECAST_STATUS.update({
        "running": False,
        "finished": True,
        "status": "completed",
        "phase": "completed",
        "phase_label": "预测训练已完成",
        "progress_pct": 100,
        "display_progress_pct": 100,
        "stage_progress_pct": 100,
        "processed": int(_FORECAST_STATUS.get("total") or 0),
        "task_index": int(_FORECAST_STATUS.get("total") or 0),
        "current": None,
        "detail_lines": final_lines[-8:],
        "finished_at": _now_cn_iso(),
        "message": f"预测已更新：成功 {_FORECAST_STATUS.get('success') or 0}，失败 {_FORECAST_STATUS.get('failed') or 0}",
        "updated_at": _now_cn_iso(),
    })
    _refresh_forecast_eta()


async def _crawl_and_store(
    crawl_day: date,
    job: dict[str, Any],
    *,
    district_id: Optional[int] = None,
    cate_id: Optional[int] = None,
    only_district_ids: Optional[set[int]] = None,
    client: Optional[ZgncpjgwClient] = None,
    slow: bool = False,
    on_district_done: Optional[Any] = None,
) -> None:
    try:
        _ensure_credentials()
        rows = await _crawl_day(
            crawl_day,
            job,
            district_id=district_id,
            cate_id=cate_id,
            only_district_ids=only_district_ids,
            client=client,
            slow=slow,
            on_district_done=on_district_done,
        )
        job.update(
            {
                "status": "completed",
                "progress": 100,
                "message": f"已抓取并入库 {len(rows)} 条农产品价格网报价",
                "row_count": len(rows),
                "updated_at": _now_cn_iso(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        message = _friendly_crawl_error(exc)
        job.update(
            {
                "status": "failed",
                "message": message,
                "error_kind": "auth" if zg_cred.is_auth_failure_message(message) else "other",
                "updated_at": _now_cn_iso(),
            }
        )


async def _backfill_worker(
    start_day: date,
    end_day: date,
    *,
    district_id: Optional[int] = None,
    cate_id: Optional[int] = None,
    forecast_sku_keys: Optional[list[str]] = None,
    slow: bool = False,
) -> None:
    try:
        await _backfill_worker_core(
            start_day,
            end_day,
            district_id=district_id,
            cate_id=cate_id,
            forecast_sku_keys=forecast_sku_keys,
            slow=slow,
        )
    except Exception as exc:  # noqa: BLE001
        if not _BACKFILL_STATUS.get("running"):
            return
        logs = list(_BACKFILL_STATUS.get("logs") or [])
        message = _friendly_crawl_error(exc)
        logs.append(f"补抓异常中止：{message}")
        _BACKFILL_STATUS.update(
            {
                "status": "failed",
                "running": False,
                "finished": True,
                "message": message,
                "error_kind": "auth" if zg_cred.is_auth_failure_message(message) else "other",
                "current": None,
                "logs": logs[-200:],
                "updated_at": _now_cn_iso(),
            }
        )


async def _backfill_worker_core(
    start_day: date,
    end_day: date,
    *,
    district_id: Optional[int] = None,
    cate_id: Optional[int] = None,
    forecast_sku_keys: Optional[list[str]] = None,
    slow: bool = False,
) -> None:
    calendar = _daterange_days(start_day, end_day)
    _BACKFILL_STATUS.update(
        {
            "status": "running",
            "running": True,
            "finished": False,
            "phase": "crawl",
            "progress": 0,
            "progress_pct": 0,
            "message": f"补抓启动：{start_day.isoformat()} ~ {end_day.isoformat()}",
            "logs": [
                f"补抓启动：{start_day.isoformat()} ~ {end_day.isoformat()}，正在扫描库内缺口…",
            ],
            "updated_at": _now_cn_iso(),
        }
    )
    scope = []
    if district_id is not None:
        scope.append(f"district_id={district_id}")
    if cate_id is not None:
        scope.append(f"cate_id={cate_id}")
    scope_text = f"（{', '.join(scope)}）" if scope else ""
    concurrency = max(1, int(settings.zgncpjgw_crawl_concurrency))

    # 全量：按日只补「分类未齐」的省，整日齐全的跳过；复用同一会话避免重复 Playwright 登录
    day_plans: list[tuple[date, set[int], str]] = []
    if district_id is None and cate_id is None:
        async with SessionLocal() as db:
            complete_days = await _complete_days_in_range(db, start_day, end_day)
            covered = await _complete_district_ids_by_day(db, start_day, end_day)
        logs = list(_BACKFILL_STATUS.get("logs") or [])
        logs.append("正在连接中农价格网（过 WAF + 登录，首次约 1 分钟内）…")
        _BACKFILL_STATUS.update(
            {
                "message": "正在登录中农价格网…",
                "progress": 2,
                "progress_pct": 2,
                "logs": logs[-200:],
                "updated_at": _now_cn_iso(),
            }
        )
        client_boot = ZgncpjgwClient()
        try:
            all_districts = await _fetch_districts(client_boot, None)
        finally:
            await client_boot.close()
        all_ids = {int(d.get("id") or 0) for d in all_districts if int(d.get("id") or 0)}
        id_to_name = {int(d.get("id") or 0): str(d.get("name") or "") for d in all_districts}
        skip_full_days = 0
        for day in calendar:
            if day in complete_days:
                skip_full_days += 1
                continue
            have = covered.get(day, set())
            missing = all_ids - have
            if not missing:
                skip_full_days += 1
                continue
            names = "、".join(id_to_name.get(i, str(i)) for i in sorted(missing)[:4])
            if len(missing) > 4:
                names += f" 等{len(missing)}省"
            day_plans.append((day, missing, names))
        start_logs = [
            (
                f"缺口补抓 {start_day.isoformat()} ~ {end_day.isoformat()}："
                f"日历 {len(calendar)} 日；整日齐全跳过 {skip_full_days} 日；"
                f"待处理 {len(day_plans)} 日（仅补缺失省份，不重复抓已齐省）；"
                f"并发 {concurrency} 省；会话复用。"
            ),
        ]
        if slow:
            lo, hi = _pause_range("zgncpjgw_day_pause_min", "zgncpjgw_day_pause_max", slow=True)
            start_logs.append(f"慢速模式：日间冷却约 {lo:g}～{hi:g} 秒。")
    else:
        async with SessionLocal() as db:
            existing = await _existing_scope_dates_in_range(db, start_day, end_day, district_id, cate_id)
        for day in calendar:
            if day in existing:
                continue
            only = {district_id} if district_id is not None else set()
            day_plans.append((day, only, scope_text))
        skipped = len(calendar) - len(day_plans)
        start_logs = [
            (
                f"扫描 {start_day.isoformat()} ~ {end_day.isoformat()}{scope_text}："
                f"日历共 {len(calendar)} 日；库内已有 {skipped} 日，待补 {len(day_plans)} 日。"
            ),
        ]

    if not day_plans:
        _BACKFILL_STATUS.update(
            {
                "status": "completed",
                "running": False,
                "finished": True,
                "progress": 100,
                "progress_pct": 100,
                "message": "无需补抓：区间内日期已齐全",
                "total": 0,
                "processed": 0,
                "success": 0,
                "current": None,
                "logs": start_logs,
                "updated_at": _now_cn_iso(),
            }
        )
        return

    province_total = _backfill_plan_province_total(day_plans)
    province_done = 0
    start_logs.append(f"进度按省统计：共 {province_total} 省次（{len(day_plans)} 日）。")
    _BACKFILL_STATUS.update(
        {
            "status": "running",
            "running": True,
            "finished": False,
            "phase": "crawl",
            "rebuild_pct": 0,
            "progress": 0,
            "progress_pct": 0,
            "message": "缺口补抓启动",
            "total": len(day_plans),
            "processed": 0,
            "success": 0,
            "sub_total": province_total,
            "sub_processed": 0,
            "current": None,
            "logs": start_logs,
            "updated_at": _now_cn_iso(),
        }
    )
    consecutive_failures = 0
    client = ZgncpjgwClient()
    try:
        for idx, (day, missing_ids, missing_label) in enumerate(day_plans, 1):
            if idx > 1:
                await _sleep_pause("zgncpjgw_day_pause_min", "zgncpjgw_day_pause_max", slow=slow)
                if consecutive_failures >= 2:
                    extra = random.uniform(15.0, 45.0) * min(consecutive_failures, 5)
                    await asyncio.sleep(extra)
            local_job = {
                "status": "running",
                "progress": 0,
                "message": f"补 {day.isoformat()}：{missing_label}",
            }
            day_province_total = _backfill_province_units(missing_ids)
            prep_pct = (
                min(99, int(province_done / province_total * 100))
                if province_total
                else int((idx - 1) / len(day_plans) * 100)
            )
            if prep_pct == 0 and (province_total or len(day_plans)):
                prep_pct = 1
            _BACKFILL_STATUS.update(
                {
                    "progress": prep_pct,
                    "progress_pct": prep_pct,
                    "current": f"{day.isoformat()} · 准备（{day_province_total} 省）",
                    "message": local_job["message"],
                    "updated_at": _now_cn_iso(),
                }
            )

            async def _on_district_done(dname: str, row_count: int, *, _day=day) -> None:
                nonlocal province_done
                province_done += 1
                pct = (
                    min(99, int(province_done / province_total * 100))
                    if province_total
                    else 0
                )
                _BACKFILL_STATUS.update(
                    {
                        "progress": pct,
                        "progress_pct": pct,
                        "sub_processed": province_done,
                        "sub_total": province_total,
                        "current": f"{_day.isoformat()} · {dname}",
                        "message": (
                            f"已补 {province_done}/{province_total} 省"
                            f"（{_day.isoformat()} {dname}，+{row_count} 条）"
                        ),
                        "updated_at": _now_cn_iso(),
                    }
                )

            await _crawl_and_store(
                day,
                local_job,
                district_id=district_id,
                cate_id=cate_id,
                only_district_ids=missing_ids if missing_ids else None,
                client=client,
                slow=slow,
                on_district_done=_on_district_done,
            )
            ok = local_job.get("status") == "completed"
            fail_msg = str(local_job.get("message") or "")
            if ok:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            logs = list(_BACKFILL_STATUS.get("logs") or [])
            logs.append(f"{'OK' if ok else 'WARN'} {day.isoformat()} [{missing_label}]：{fail_msg or '无返回'}")
            if not ok and zg_cred.is_auth_failure_message(fail_msg):
                logs.append("补抓已中止：账号或密码错误，请先在「配置」中修正并测试登录。")
                _BACKFILL_STATUS.update(
                    {
                        "status": "failed",
                        "running": False,
                        "finished": True,
                        "progress": int(idx / len(day_plans) * 100),
                        "progress_pct": int(idx / len(day_plans) * 100),
                        "message": fail_msg,
                        "error_kind": "auth",
                        "processed": idx,
                        "current": None,
                        "logs": logs[-200:],
                        "updated_at": _now_cn_iso(),
                    }
                )
                break
            day_pct = (
                min(99, int(province_done / province_total * 100))
                if province_total
                else int(idx / len(day_plans) * 100)
            )
            _BACKFILL_STATUS.update(
                {
                    "status": "running",
                    "progress": day_pct,
                    "progress_pct": day_pct,
                    "message": f"已处理 {day.isoformat()}：{local_job.get('message')}",
                    "running": True,
                    "finished": False,
                    "total": len(day_plans),
                    "processed": idx,
                    "success": int(_BACKFILL_STATUS.get("success") or 0) + (1 if ok else 0),
                    "sub_processed": province_done,
                    "sub_total": province_total,
                    "current": day.isoformat(),
                    "logs": logs[-200:],
                    "updated_at": _now_cn_iso(),
                }
            )
    finally:
        await client.close()

    if _BACKFILL_STATUS.get("error_kind") == "auth" or _BACKFILL_STATUS.get("status") == "failed":
        return

    logs = list(_BACKFILL_STATUS.get("logs") or [])
    logs.append(f"补抓结束：成功 {_BACKFILL_STATUS.get('success') or 0}/{len(day_plans)} 日。")
    # 补抓后自动重建派生表（指数/异动/预测序列），让数据"变活"
    refresh_msg = "补抓完成"

    def _rebuild_progress(done: int, total: int, label: str) -> None:
        _BACKFILL_STATUS.update(
            {
                "phase": "rebuild",
                "rebuild_done": done,
                "rebuild_total": total,
                "rebuild_pct": int(done / total * 100) if total else 0,
                "message": f"刷新派生指标：{label}",
                "updated_at": _now_cn_iso(),
            }
        )

    try:
        crawled_days = [d for (d, _missing, _names) in day_plans]
        logs.append("正在刷新派生指标（指数/异动/预测）…")
        _BACKFILL_STATUS.update({"phase": "rebuild", "rebuild_pct": 0, "message": "正在刷新派生指标…", "logs": logs[-200:], "updated_at": _now_cn_iso()})
        result = await refresh_derived(crawled_days, progress=_rebuild_progress)
        logs.append(f"派生指标已刷新：daily_agg {result['agg_rows']} 行 / price_index {result['index_rows']} 行。")
        refresh_msg = "补抓完成，派生指标已刷新"
    except Exception as exc:  # noqa: BLE001
        logs.append(f"派生指标刷新失败（不影响补抓结果）：{exc}")

    try:
        logs.append("正在训练本地预测模型（客户配置热门 SKU + 当前 SKU 优先）…")
        _BACKFILL_STATUS.update({"phase": "forecast", "message": "预测训练中：正在准备任务…", "logs": logs[-200:], "updated_at": _now_cn_iso()})
        await _train_forecast_batch(forecast_sku_keys or [], limit=20, include_popular=True, scope_mode="popular_batch")
        logs.extend([f"预测训练：{line}" for line in (_FORECAST_STATUS.get("logs") or [])[-20:]])
        refresh_msg = f"{refresh_msg}，预测已更新"
    except Exception as exc:  # noqa: BLE001
        logs.append(f"预测训练失败（保留上次成功预测）：{exc}")
    _BACKFILL_STATUS.update(
        {
            "status": "completed",
            "running": False,
            "finished": True,
            "phase": "done",
            "rebuild_pct": 100,
            "progress": 100,
            "progress_pct": 100,
            "message": refresh_msg,
            "current": None,
            "logs": logs[-200:],
            "updated_at": _now_cn_iso(),
        }
    )


@router.get("/credentials")
async def get_zg_credentials(_user: User = Depends(require_role("monitor"))):
    await zg_cred.refresh_credentials()
    snap = zg_cred.snapshot_for_api()
    snap["hint"] = (
        "密码仅监管端可见；保存后补抓/采集将使用此处账号。"
        if snap.get("password_configured")
        else "尚未配置，将尝试读取 backend/.env 中的 ZGNCPJGW_*。"
    )
    return snap


@router.put("/credentials")
async def put_zg_credentials(
    body: ZgCredentialsBody,
    user: User = Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await zg_cred.save_credentials(
            db,
            username=body.username.strip(),
            password=body.password,
            updated_by=user.username or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": "账号已保存，后续补抓将使用新密码",
        **zg_cred.snapshot_for_api(),
    }


@router.post("/credentials/test")
async def test_zg_credentials(
    body: Optional[ZgCredentialsBody] = None,
    _user: User = Depends(require_role("monitor")),
):
    """测试登录：同步 Playwright 放线程池 + 硬超时，避免 async 版无法取消导致 HTTP 挂死。"""
    if body:
        username = body.username.strip()
        password = body.password
    else:
        await zg_cred.refresh_credentials()
        _ensure_credentials()
        username = zg_cred.get_username()
        password = zg_cred.get_password()
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(zg_cred.test_login_sync, username, password),
            timeout=75.0,
        )
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "message": "登录测试超时（75 秒）：可能正在补抓占用浏览器，请稍后重试",
            "error_kind": "other",
            "username": username,
        }


@router.post("/crawl")
async def crawl(
    background_tasks: BackgroundTasks,
    date: str = "",
    district_id: Optional[int] = Query(default=None),
    cate_id: Optional[int] = Query(default=None),
        slow: bool = Query(default=False),
    _=Depends(_monitor_guard),
):
    _ensure_credentials()
    crawl_day = _parse_day(date, _default_date()) or _default_date()
    if _LAST_JOB.get("status") == "running":
        raise HTTPException(status_code=409, detail="已有单日采集任务在运行，请稍后再试")
    _LAST_JOB.update(
        {
            "job_id": f"zgncpjgw-{_now_cn().strftime('%Y%m%d%H%M%S')}",
            "status": "queued",
            "progress": 0,
            "message": f"已加入抓取队列：{crawl_day.isoformat()}",
            "date": crawl_day.isoformat(),
            "district_id": district_id,
            "cate_id": cate_id,
            "row_count": 0,
            "updated_at": _now_cn_iso(),
        }
    )

    async def _run() -> None:
        _LAST_JOB["status"] = "running"
        await _crawl_and_store(
            crawl_day,
            _LAST_JOB,
            district_id=district_id,
            cate_id=cate_id,
            slow=slow,
        )
        # 采集成功后自动重建该日派生表
        if _LAST_JOB.get("status") == "completed":
            try:
                await refresh_derived([crawl_day])
                await _train_forecast_batch([], limit=10, include_popular=True, scope_mode="popular_batch")
                _LAST_JOB["message"] = f"{_LAST_JOB.get('message')}（派生指标与预测已刷新）"
            except Exception as exc:  # noqa: BLE001
                _LAST_JOB["message"] = f"{_LAST_JOB.get('message')}（派生指标刷新失败：{exc}）"

    background_tasks.add_task(_run)
    return _LAST_JOB


@router.post("/backfill")
async def backfill(
    background_tasks: BackgroundTasks,
    body: Optional[BackfillBody] = None,
    _=Depends(_monitor_guard),
):
    _ensure_credentials()
    if _BACKFILL_STATUS.get("running"):
        raise HTTPException(status_code=409, detail="已有补抓任务在运行")
    payload = body or BackfillBody()
    start_day = _parse_day(payload.start_date, _default_date()) or _default_date()
    end_day = _parse_day(payload.end_date, _default_date()) or start_day
    if end_day < start_day:
        start_day, end_day = end_day, start_day
    queue_msg = f"补抓已排队：{start_day.isoformat()} ~ {end_day.isoformat()}"
    _BACKFILL_STATUS.update(
        {
            "status": "queued",
            "running": True,
            "finished": False,
            "phase": "crawl",
            "progress": 0,
            "progress_pct": 0,
            "message": queue_msg,
            "logs": [queue_msg, "后台任务即将启动，请稍候…"],
            "updated_at": _now_cn_iso(),
        }
    )
    background_tasks.add_task(
        _backfill_worker,
        start_day,
        end_day,
        district_id=payload.district_id,
        cate_id=payload.cate_id,
        forecast_sku_keys=payload.forecast_sku_keys,
        slow=payload.slow,
    )
    return _BACKFILL_STATUS


@router.get("/progress")
async def crawl_progress(_=Depends(_monitor_guard)):
    return _LAST_JOB


def _maybe_recover_stale_backfill() -> None:
    """Worker 崩溃或 Playwright 挂死时，避免 running 永远为 true。"""
    if not _BACKFILL_STATUS.get("running"):
        return
    updated_raw = _BACKFILL_STATUS.get("updated_at")
    if not updated_raw:
        return
    try:
        updated = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=_now_cn().tzinfo)
        age_sec = (_now_cn() - updated.astimezone(_now_cn().tzinfo)).total_seconds()
    except (TypeError, ValueError):
        return
    progress = int(_BACKFILL_STATUS.get("progress_pct") or _BACKFILL_STATUS.get("progress") or 0)
    # 长时间停在 0~2%：多为登录/扫描阶段挂死
    stale_limit = 20 * 60 if progress <= 2 else 3 * 3600
    if age_sec < stale_limit:
        return
    logs = list(_BACKFILL_STATUS.get("logs") or [])
    logs.append(
        f"任务已超过 {int(age_sec // 60)} 分钟无进展，已自动结束；请检查网络/VPN/账号后重新补抓。"
    )
    _BACKFILL_STATUS.update(
        {
            "status": "failed",
            "running": False,
            "finished": True,
            "message": "补抓任务超时无进展，已自动结束",
            "current": None,
            "logs": logs[-200:],
            "updated_at": _now_cn_iso(),
        }
    )


@router.get("/backfill/status")
async def backfill_status(_=Depends(_monitor_guard)):
    _maybe_recover_stale_backfill()
    return _BACKFILL_STATUS


@router.get("/backfill/preview")
async def backfill_preview(
    end_date: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """预览自库内最新日的次日到目标日之间，尚需缺口补抓的日期列表。"""
    end_day = _parse_day(end_date, _default_date()) or _default_date()
    result = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{_tbl()}`"))
    raw_mx = result.scalar_one_or_none()
    latest: Optional[date] = None
    if raw_mx is not None:
        if isinstance(raw_mx, datetime):
            latest = raw_mx.date()
        elif isinstance(raw_mx, date):
            latest = raw_mx

    if latest is None:
        start_day = end_day - timedelta(days=89)
        message = f"库内暂无数据，将从 {start_day.isoformat()} 补至 {end_day.isoformat()}（共 90 日）"
    elif latest >= end_day:
        return {
            "latest_date": latest.isoformat(),
            "end_date": end_day.isoformat(),
            "start_date": end_day.isoformat(),
            "missing_days": [],
            "day_count": 0,
            "complete_days": 0,
            "message": f"库内最新日为 {latest.isoformat()}，已覆盖至目标日 {end_day.isoformat()}，无需补抓",
        }
    else:
        start_day = latest + timedelta(days=1)
        message = f"库内最新 {latest.isoformat()}，待补 {start_day.isoformat()} ~ {end_day.isoformat()}"

    calendar = _daterange_days(start_day, end_day)
    complete = await _complete_days_in_range(db, start_day, end_day)
    pending = [d for d in calendar if d not in complete]
    return {
        "latest_date": latest.isoformat() if latest else "",
        "end_date": end_day.isoformat(),
        "start_date": start_day.isoformat(),
        "missing_days": [d.isoformat() for d in pending],
        "day_count": len(pending),
        "complete_days": len(complete),
        "message": (
            message
            + (f"：共 {len(pending)} 日待处理（整日 12 省齐全已跳过 {len(complete)} 日）" if pending else "，无需补抓")
        ),
    }


@router.get("/prices")
async def list_prices(
    date: str = "",
    start_date: str = "",
    end_date: str = "",
    district_id: Optional[int] = Query(default=None),
    cate_id: Optional[int] = Query(default=None),
    scate: str = "",
    goods_name: str = "",
    sku_key: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    clauses: list[str] = []
    params: dict[str, Any] = {}
    # 指定 sku_key 时精确锁定 (品名,规格,单位,分类,子类)，明细只显示该 SKU（规格/单位一致）
    if sku_key.strip():
        _n, _s, _u, _cid, _sc = split_sku_key(sku_key)
        clauses += ["goods_name = :sk_n", "spec = :sk_s", "unit = :sk_u", "cate_id = :sk_c", "scate_name = :sk_sc"]
        params.update({"sk_n": _n, "sk_s": _s, "sk_u": _u, "sk_c": _cid, "sk_sc": _sc})
    if date:
        clauses.append("crawl_date = :crawl_date")
        params["crawl_date"] = _parse_day(date)
    if start_date:
        clauses.append("crawl_date >= :start_date")
        params["start_date"] = _parse_day(start_date)
    if end_date:
        clauses.append("crawl_date <= :end_date")
        params["end_date"] = _parse_day(end_date)
    if district_id is not None:
        clauses.append("district_id = :district_id")
        params["district_id"] = district_id
    if not sku_key.strip():
        if cate_id is not None:
            clauses.append("cate_id = :cate_id")
            params["cate_id"] = cate_id
        if scate.strip():
            clauses.append("scate_name = :scate")
            params["scate"] = scate.strip()
        if goods_name.strip():
            clauses.append("goods_name LIKE :goods_name")
            params["goods_name"] = f"%{goods_name.strip()}%"
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM `{_tbl()}` {where_sql}"),
        params,
    )
    total = int(count_result.scalar_one() or 0)
    offset = (page - 1) * page_size
    params_with_page = {**params, "limit": page_size, "offset": offset}
    result = await db.execute(
        text(
            f"""
            SELECT id, crawl_date, district_id, district_name, cate_id, cate_name, scate_name,
                   goods_sn, goods_name, spec, unit, place, price, update_date, created_at, updated_at
            FROM `{_tbl()}`
            {where_sql}
            ORDER BY crawl_date DESC, district_id ASC, cate_id ASC, goods_name ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        params_with_page,
    )
    rows = []
    for row in result.fetchall():
        rows.append(
            {
                "id": row.id,
                "crawl_date": _fmt_day(row.crawl_date),
                "district_id": row.district_id,
                "district_name": row.district_name,
                "cate_id": row.cate_id,
                "cate_name": row.cate_name,
                "scate_name": row.scate_name,
                "goods_sn": row.goods_sn,
                "goods_name": row.goods_name,
                "spec": row.spec,
                "unit": row.unit,
                "place": row.place,
                "price": row.price,
                "update_date": _fmt_day(row.update_date),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "rows": rows,
    }


@router.get("/analytics/filters")
async def analytics_filters(_=Depends(_monitor_guard), db: AsyncSession = Depends(get_db)):
    """筛选项下拉数据：省份/分类目录（取最新采集日切片，命中 idx_crawl_date，避免全表 DISTINCT 扫描）、
    日期范围与覆盖天数。catalog 每日稳定，最新日即可代表全集。"""
    tbl = _tbl()
    # MIN/MAX 走 idx_crawl_date，瞬时返回
    r_res = await db.execute(
        text(f"SELECT MIN(crawl_date) AS mn, MAX(crawl_date) AS mx FROM `{tbl}`")
    )
    row = r_res.fetchone()
    mn = _parse_day(row.mn) if row else None
    mx = _parse_day(row.mx) if row else None

    districts: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []
    if mx is not None:
        d_res = await db.execute(
            text(
                f"SELECT DISTINCT district_id, district_name FROM `{tbl}` "
                f"WHERE crawl_date = :d ORDER BY district_id"
            ),
            {"d": mx},
        )
        districts = [{"id": r.district_id, "name": r.district_name} for r in d_res.fetchall()]
        c_res = await db.execute(
            text(
                f"SELECT DISTINCT cate_id, cate_name FROM `{tbl}` "
                f"WHERE crawl_date = :d ORDER BY cate_id"
            ),
            {"d": mx},
        )
        categories = [{"id": r.cate_id, "name": r.cate_name} for r in c_res.fetchall()]

    # 子类目录（挂在各分类下；子类→分类 1:1）
    subcategories: list[dict[str, Any]] = []
    if mx is not None:
        s_res = await db.execute(
            text(
                f"SELECT DISTINCT cate_id, scate_name FROM `{tbl}` "
                f"WHERE crawl_date = :d AND scate_name <> '' ORDER BY cate_id, scate_name"
            ),
            {"d": mx},
        )
        subcategories = [{"cate_id": r.cate_id, "name": r.scate_name} for r in s_res.fetchall()]

    # 覆盖天数：仅扫 crawl_date 索引（index-only），不碰表数据
    days_res = await db.execute(
        text(f"SELECT COUNT(DISTINCT crawl_date) AS days FROM `{tbl}`")
    )
    days_covered = int(days_res.scalar_one() or 0)

    # 累计入库条数：对派生表 sample_count 求和（≈ 原始 crawl 行数），仅在进入页时查一次，不随筛选刷新
    cumulative_rows = 0
    try:
        cum_res = await db.execute(
            text(f"SELECT COALESCE(SUM(sample_count), 0) AS n FROM `{AGG_TBL}`")
        )
        cumulative_rows = int(cum_res.scalar_one() or 0)
    except Exception:
        cumulative_rows = 0

    return {
        "districts": districts,
        "categories": categories,
        "subcategories": subcategories,
        "date_range": {
            "min": _fmt_day(mn) if mn else "",
            "max": _fmt_day(mx) if mx else "",
        },
        "earliest_date": _fmt_day(mn) if mn else "",
        "latest_date": _fmt_day(mx) if mx else "",
        "days_covered": days_covered,
        "cumulative_rows": cumulative_rows,
    }


@router.get("/analytics/overview")
async def analytics_overview(
    date: str = "",
    district_id: Optional[int] = Query(default=None),
    cate_id: Optional[int] = Query(default=None),
    scate: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """KPI 单日快照：缺省取最新采集日。所有聚合都落在 crawl_date=:date 单日切片上
    （命中 idx_crawl_date，几千行），避免对 1.9GB 全表做 COUNT(DISTINCT)/GROUP BY。
    distinct_skus = 品名+一级分类(cate_id)+二级分类(scate_name)+规格+单位 五维去重。"""
    tbl = _tbl()
    snapshot_day = _parse_day(date)
    if snapshot_day is None:
        mx_res = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{tbl}`"))
        mx_row = mx_res.fetchone()
        snapshot_day = _parse_day(mx_row.mx) if mx_row and mx_row.mx else None
    if snapshot_day is None:
        return {
            "snapshot_date": "",
            "total_rows": 0,
            "distinct_goods": 0,
            "distinct_skus": 0,
            "distinct_districts": 0,
            "distinct_categories": 0,
            "category_breakdown": [],
        }

    clauses = ["crawl_date = :d"]
    params: dict[str, Any] = {"d": snapshot_day}
    if district_id is not None:
        clauses.append("district_id = :did")
        params["did"] = district_id
    if cate_id is not None:
        clauses.append("cate_id = :cid")
        params["cid"] = cate_id
    if scate.strip():
        clauses.append("scate_name = :scate")
        params["scate"] = scate.strip()
    where_sql = f"WHERE {' AND '.join(clauses)}"

    res = await db.execute(
        text(
            f"""
            SELECT COUNT(*) AS total_rows,
                   COUNT(DISTINCT goods_name) AS distinct_goods,
                   COUNT(DISTINCT goods_name, cate_id, scate_name, spec, unit) AS distinct_skus,
                   COUNT(DISTINCT district_id) AS distinct_districts,
                   COUNT(DISTINCT cate_id) AS distinct_categories
            FROM `{tbl}` {where_sql}
            """
        ),
        params,
    )
    row = res.fetchone()
    cat_res = await db.execute(
        text(
            f"""
            SELECT cate_name, COUNT(DISTINCT goods_name, cate_id, scate_name, spec, unit) AS sku_count
            FROM `{tbl}` {where_sql}
            GROUP BY cate_name
            ORDER BY sku_count DESC
            LIMIT 12
            """
        ),
        params,
    )
    category_breakdown = [
        {"cate_name": r.cate_name or "未分类", "sku_count": int(r.sku_count or 0)}
        for r in cat_res.fetchall()
    ]
    # 快照日按省覆盖广度倒序的热门 SKU(品名+规格+单位)，给前端做数据驱动的默认选中与快捷 chips
    top_res = await db.execute(
        text(
            f"""
            SELECT goods_name, spec, unit, cate_id, cate_name, scate_name,
                   COUNT(DISTINCT district_name) AS prov, COUNT(*) AS c
            FROM `{tbl}` {where_sql}
            GROUP BY goods_name, spec, unit, cate_id, cate_name, scate_name
            ORDER BY prov DESC, c DESC
            LIMIT 10
            """
        ),
        params,
    )
    top_skus = _attach_sku_labels([
        {"goods_name": r.goods_name, "spec": r.spec, "unit": r.unit,
         "cate_id": r.cate_id, "cate_name": r.cate_name, "scate_name": r.scate_name}
        for r in top_res.fetchall() if r.goods_name
    ])
    return {
        "snapshot_date": _fmt_day(snapshot_day),
        "total_rows": int(row.total_rows or 0) if row else 0,
        "distinct_goods": int(row.distinct_goods or 0) if row else 0,
        "distinct_skus": int(row.distinct_skus or 0) if row else 0,
        "distinct_districts": int(row.distinct_districts or 0) if row else 0,
        "distinct_categories": int(row.distinct_categories or 0) if row else 0,
        "category_breakdown": category_breakdown,
        "top_skus": top_skus,
    }


@router.get("/analytics/products")
async def analytics_products(
    q: str = "",
    limit: int = Query(default=50, ge=1, le=100),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """SKU(品名+规格+单位) 联想搜索：从最新日 daily_agg 切片按品名匹配，按省覆盖度排序。"""
    mx_res = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{AGG_TBL}`"))
    mx_row = mx_res.fetchone()
    latest = _parse_day(mx_row.mx) if mx_row and mx_row.mx else None
    if latest is None:
        return {"products": []}
    clauses = ["crawl_date = :d"]
    params: dict[str, Any] = {"d": latest, "lim": limit}
    if q.strip():
        clauses.append("goods_name LIKE :q")
        params["q"] = f"%{q.strip()}%"
    res = await db.execute(
        text(
            f"""
            SELECT goods_name, spec, unit, cate_id, cate_name, scate_name, province_count
            FROM `{AGG_TBL}` WHERE {' AND '.join(clauses)}
            ORDER BY province_count DESC, sample_count DESC, goods_name
            LIMIT :lim
            """
        ),
        params,
    )
    products = _attach_sku_labels([
        {"goods_name": r.goods_name, "spec": r.spec, "unit": r.unit,
         "cate_id": r.cate_id, "cate_name": r.cate_name, "scate_name": r.scate_name}
        for r in res.fetchall() if r.goods_name
    ])
    return {"products": products}


@router.get("/analytics/hot-skus")
async def analytics_hot_skus(
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    configured = await _configured_hot_skus(db, only_enabled=False)
    recommended = await _recommended_hot_skus(db, limit=20)
    active = [x for x in configured if x.get("enabled")] if configured else recommended
    estimate = await _estimate_forecast_tasks(db, [x["sku_key"] for x in active], district_limit=40)
    all_estimate = await _estimate_all_forecast_tasks(db)
    return {
        "configured": configured,
        "recommended": recommended,
        "using_recommended": not bool(configured),
        "active_count": len(active),
        "estimate": estimate,
        "all_estimate": all_estimate,
    }


@router.put("/analytics/hot-skus")
async def save_analytics_hot_skus(
    body: HotSkuSaveBody,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_hot_sku_table(db)
    items = []
    seen: set[str] = set()
    for idx, item in enumerate(body.items[:80]):
        key = str(item.sku_key or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        label = str(item.label or key).strip()[:255]
        items.append({"sku_key": key, "label": label, "enabled": bool(item.enabled), "sort_order": idx})
    await db.execute(text(f"DELETE FROM `{HOT_SKU_TBL}`"))
    for item in items:
        await db.execute(
            text(
                f"""
                INSERT INTO `{HOT_SKU_TBL}` (sku_key, label, enabled, sort_order)
                VALUES (:sku_key, :label, :enabled, :sort_order)
                """
            ),
            item,
        )
    await db.commit()
    active = [x for x in items if x.get("enabled")]
    estimate = await _estimate_forecast_tasks(db, [x["sku_key"] for x in active], district_limit=40)
    all_estimate = await _estimate_all_forecast_tasks(db)
    return {
        "saved": True,
        "configured": items,
        "using_recommended": False,
        "active_count": len(active),
        "estimate": estimate,
        "all_estimate": all_estimate,
    }


def _sku_label(goods_name: str, spec: str, unit: str) -> str:
    if spec:
        return f"{goods_name} {spec}".strip()
    return goods_name + (f"（{unit}）" if unit else "")


def _attach_sku_labels(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把原始 SKU 行(含 goods_name/spec/unit/cate_id/cate_name/scate_name) 组装成带 sku_key + 消歧 label 的列表。
    同 (品名,规格,单位) 出现多条（鲜/冻等）时给 label 追加 '· 子类' 以区分。"""
    from collections import Counter

    base_counts = Counter((it["goods_name"], it.get("spec", ""), it.get("unit", "")) for it in items)
    out = []
    for it in items:
        gn, spec, unit = it["goods_name"], it.get("spec", "") or "", it.get("unit", "") or ""
        label = _sku_label(gn, spec, unit)
        scate = it.get("scate_name", "") or ""
        if base_counts[(gn, spec, unit)] > 1 and scate:
            label = f"{label} · {scate}"
        out.append({
            "sku_key": make_sku_key(gn, spec, unit, it.get("cate_id", 0), scate),
            "goods_name": gn, "spec": spec, "unit": unit,
            "cate_name": it.get("cate_name", "") or "", "scate_name": scate, "label": label,
        })
    return out


@router.get("/analytics/timeseries")
async def analytics_timeseries(
    sku_keys: str = "",
    district_id: Optional[int] = Query(default=None),
    start_date: str = "",
    end_date: str = "",
    days: int = Query(default=30, ge=1, le=365),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """价格趋势：按 SKU(品名+规格+单位，多个用换行分隔) + 日期范围聚合日中位价（同口径）。"""
    keys = [k for k in (sku_keys or "").split("\n") if k.strip()]
    if not keys:
        return {"dates": [], "series": []}
    triplets = {k: split_sku_key(k) for k in keys}
    names = list({t[0] for t in triplets.values() if t[0]})
    if not names:
        return {"dates": [], "series": []}
    tbl = _tbl()
    end_day = _parse_day(end_date) or _today()
    start_day = _parse_day(start_date) or (end_day - timedelta(days=days))
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    clauses = ["crawl_date >= :sd", "crawl_date <= :ed"]
    params: dict[str, Any] = {"sd": start_day, "ed": end_day}
    placeholders = []
    for i, n in enumerate(names):
        pk = f"g{i}"
        placeholders.append(f":{pk}")
        params[pk] = n
    clauses.append(f"goods_name IN ({', '.join(placeholders)})")
    if district_id is not None:
        clauses.append("district_id = :did")
        params["did"] = district_id
    res = await db.execute(
        text(f"SELECT crawl_date, goods_name, spec, unit, cate_id, scate_name, price FROM `{tbl}` WHERE {' AND '.join(clauses)}"),
        params,
    )
    wanted = set(keys)
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    all_dates: set[str] = set()
    for r in res.fetchall():
        sk = make_sku_key(r.goods_name, r.spec or "", r.unit or "", r.cate_id or 0, r.scate_name or "")
        if sk not in wanted:
            continue
        v = _price_to_float(r.price)
        if v is None:
            continue
        d = _fmt_day(r.crawl_date)
        if not d:
            continue
        buckets[sk][d].append(v)
        all_dates.add(d)
    dates = sorted(all_dates)
    series = []
    for k in keys:
        gn, spec, unit, _cid, _scate = triplets[k]
        per_date = buckets.get(k, {})
        values = [round(_stat_median(per_date[d]), 2) if per_date.get(d) else None for d in dates]
        series.append({"name": _sku_label(gn, spec, unit), "sku_key": k, "values": values})
    return {"dates": dates, "series": series}


@router.get("/analytics/compare")
async def analytics_compare(
    sku_key: str = "",
    date: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """省份对比：某 SKU(品名+规格+单位) 在某日（默认最新）各省份中位价，降序。"""
    if not (sku_key or "").strip():
        return {"date": "", "labels": [], "values": [], "label": ""}
    name, spec, unit, cate_id, scate = split_sku_key(sku_key)
    if not name:
        return {"date": "", "labels": [], "values": [], "label": ""}
    tbl = _tbl()
    sku_where = "goods_name = :g AND spec = :s AND unit = :u AND cate_id = :c AND scate_name = :sc"
    base_params = {"g": name, "s": spec, "u": unit, "c": cate_id, "sc": scate}
    target_day = _parse_day(date)
    if target_day is None:
        d_res = await db.execute(
            text(f"SELECT MAX(crawl_date) AS mx FROM `{tbl}` WHERE {sku_where}"), base_params
        )
        row = d_res.fetchone()
        target_day = _parse_day(row.mx) if row and row.mx else None
    if target_day is None:
        return {"date": "", "labels": [], "values": [], "label": _sku_label(name, spec, unit)}
    res = await db.execute(
        text(f"SELECT district_name, price FROM `{tbl}` WHERE {sku_where} AND crawl_date = :d"),
        {**base_params, "d": target_day},
    )
    buckets: dict[str, list[float]] = defaultdict(list)
    for r in res.fetchall():
        v = _price_to_float(r.price)
        if v is None:
            continue
        buckets[r.district_name or "未知"].append(v)
    pairs = [(k, round(_stat_median(v), 2)) for k, v in buckets.items() if v]
    pairs.sort(key=lambda x: x[1], reverse=True)
    return {
        "date": _fmt_day(target_day),
        "label": _sku_label(name, spec, unit),
        "labels": [p[0] for p in pairs],
        "values": [p[1] for p in pairs],
    }


@router.get("/analytics/index")
async def analytics_index(_=Depends(_monitor_guard), db: AsyncSession = Depends(get_db)):
    """大综价格指数（Jevons 几何均值价比，单位无关、抗离群）：读物化表 zgncpjgw_price_index。
    返回总指数时间序列 + 各分类最新值/环比 + 各分类序列。"""
    res = await db.execute(
        text(
            f"SELECT idx_date, cate_id, cate_name, index_value, basket_size FROM `{IDX_TBL}` ORDER BY idx_date"
        )
    )
    by_cate: dict[int, dict[str, Any]] = {}
    dates_set: set[str] = set()
    for r in res.fetchall():
        d = _fmt_day(r.idx_date)
        dates_set.add(d)
        c = by_cate.setdefault(
            int(r.cate_id), {"cate_id": int(r.cate_id), "cate_name": r.cate_name or "", "points": {}}
        )
        c["points"][d] = float(r.index_value)
        c["basket_size"] = int(r.basket_size or 0)
    dates = sorted(dates_set)
    if not dates:
        return {"base_date": "", "dates": [], "overall": [], "categories": []}

    def series_of(cid: int) -> list[Optional[float]]:
        pts = by_cate.get(cid, {}).get("points", {})
        return [pts.get(d) for d in dates]

    overall = series_of(0)
    cats = []
    for cid, c in by_cate.items():
        if cid == 0:
            continue
        s = series_of(cid)
        last = next((v for v in reversed(s) if v is not None), None)
        first = next((v for v in s if v is not None), None)
        cats.append(
            {
                "cate_id": cid,
                "cate_name": c["cate_name"],
                "basket_size": c.get("basket_size", 0),
                "latest": round(last, 2) if last is not None else None,
                "change_pct": round(last - 100, 2) if last is not None else None,
                "series": s,
            }
        )
    cats.sort(key=lambda x: (x["latest"] is None, -(x["latest"] or 0)))
    last_overall = next((v for v in reversed(overall) if v is not None), 100.0)
    latest_day = dates[-1]
    latest_overall_meta = by_cate.get(0, {})
    prov_res = await db.execute(
        text(
            f"""
            SELECT COUNT(DISTINCT district_id) AS province_count
            FROM `{_tbl()}`
            WHERE crawl_date = :d
            """
        ),
        {"d": _parse_day(latest_day)},
    )
    prov_row = prov_res.fetchone()
    return {
        "base_date": dates[0],
        "latest_date": latest_day,
        "dates": dates,
        "overall": overall,
        "overall_latest": round(last_overall, 2),
        "overall_change_pct": round(last_overall - 100, 2),
        "basket_meta": {
            "province_count": int(prov_row.province_count or 0) if prov_row else 0,
            "basket_size": int(latest_overall_meta.get("basket_size") or 0),
            "latest_date": latest_day,
        },
        "categories": cats,
    }


async def _latest_agg_date(db: AsyncSession) -> Optional[date]:
    res = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{_tbl()}`"))
    row = res.fetchone()
    return _parse_day(row.mx) if row and row.mx else None


@router.get("/analytics/map")
async def analytics_map(
    sku_key: str = "",
    cate_id: Optional[int] = Query(default=None),
    metric: str = "level",
    date: str = "",
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """全国 12 省热力地图。
    - 指定 sku_key：各省该 SKU 中位价（metric=level）或周环比%（metric=chg7）。
    - 指定 cate_id：各省相对价格指数（该省该品类各 SKU 的 省中位价/全国中位价 几何均值 ×100，>100 偏贵）。"""
    day = _parse_day(date) or await _latest_agg_date(db)
    if day is None:
        return {"date": "", "metric": metric, "scope": "", "provinces": []}
    tbl = _tbl()

    if (sku_key or "").strip():
        name, spec, unit, scate_cate, scate = split_sku_key(sku_key)

        async def province_medians(target: date) -> dict[str, float]:
            res = await db.execute(
                text(f"SELECT district_name, price FROM `{tbl}` WHERE goods_name=:g AND spec=:s AND unit=:u AND cate_id=:c AND scate_name=:sc AND crawl_date=:d"),
                {"g": name, "s": spec, "u": unit, "c": scate_cate, "sc": scate, "d": target},
            )
            buckets: dict[str, list[float]] = defaultdict(list)
            for r in res.fetchall():
                v = _price_to_float(r.price)
                if v is not None and r.district_name:
                    buckets[r.district_name].append(v)
            return {k: round(_stat_median(v), 2) for k, v in buckets.items() if v}

        cur = await province_medians(day)
        if metric == "chg7":
            prev = await province_medians(day - timedelta(days=7))
            provinces = [
                {"name": p, "value": round((cur[p] - prev[p]) / prev[p] * 100, 1)}
                for p in cur if p in prev and prev[p] > 0
            ]
        else:
            provinces = [{"name": p, "value": v} for p, v in cur.items()]
        return {"date": _fmt_day(day), "metric": metric, "scope": _sku_label(name, spec, unit), "provinces": provinces}

    # 按分类：相对价格指数（按 SKU 价比，单位无关、抗离群）
    if cate_id is None:
        return {"date": _fmt_day(day), "metric": metric, "scope": "", "provinces": []}
    res = await db.execute(
        text(f"SELECT district_name, goods_name, spec, unit, scate_name, price FROM `{tbl}` WHERE cate_id = :c AND crawl_date = :d"),
        {"c": cate_id, "d": day},
    )
    pg: dict[tuple, list[float]] = defaultdict(list)   # (省, sku) → 价
    national: dict[str, list[float]] = defaultdict(list)  # sku → 全国价
    for r in res.fetchall():
        v = _price_to_float(r.price)
        if v is None or not r.district_name or not r.goods_name:
            continue
        sk = make_sku_key(r.goods_name, r.spec or "", r.unit or "", cate_id, r.scate_name or "")
        pg[(r.district_name, sk)].append(v)
        national[sk].append(v)
    nat_med = {sk: _stat_median(v) for sk, v in national.items() if v}
    prov_rel: dict[str, list[float]] = defaultdict(list)
    for (prov, sk), vals in pg.items():
        nm = nat_med.get(sk)
        if nm and nm > 0:
            prov_rel[prov].append(math.log(_stat_median(vals) / nm))
    provinces = [
        {"name": prov, "value": round(100.0 * math.exp(sum(logs) / len(logs)), 1)}
        for prov, logs in prov_rel.items() if logs
    ]
    return {"date": _fmt_day(day), "metric": "rel_index", "scope": f"cate:{cate_id}", "provinces": provinces}


@router.get("/analytics/movers")
async def analytics_movers(
    window: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=12, ge=1, le=100),
    min_provinces: int = Query(default=6, ge=1),
    max_pct: float = Query(default=150.0),
    cate_id: Optional[int] = Query(default=None),
    scate: str = "",
    district_id: Optional[int] = Query(default=None),
    quality_policy: str = Query(default="strict", pattern="^(strict|warn|all)$"),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """价格异动雷达：全国用 daily_agg 跨省中位价；指定省份时用 crawl 表该省 SKU 中位价。
    覆盖度过滤(全国≥min_provinces 省)+ 可信区间过滤(|涨跌|≤max_pct)
    + 分类内中位数+MAD 稳健 z。返回暴涨/暴跌榜。"""
    window = int(_bare_route_param(window, 7))
    limit = int(_bare_route_param(limit, 12))
    min_provinces = int(_bare_route_param(min_provinces, 6))
    max_pct = float(_bare_route_param(max_pct, 150.0))
    cate_id = _bare_route_param(cate_id, None)
    district_id = _bare_route_param(district_id, None)
    quality_policy = normalize_quality_policy(_bare_route_param(quality_policy, "strict"))
    if district_id is not None:
        district_id = int(district_id)

    dres = await db.execute(text(f"SELECT MAX(idx_date) AS mx FROM `{IDX_TBL}`"))
    drow = dres.fetchone()
    latest = _parse_day(drow.mx) if drow and drow.mx else None
    if latest is None:
        agg_d = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{AGG_TBL}`"))
        ar = agg_d.fetchone()
        latest = _parse_day(ar.mx) if ar and ar.mx else None
    if latest is None:
        return {"latest_date": "", "window": window, "district_id": district_id, "district_name": "", "gainers": [], "losers": []}
    prev = latest - timedelta(days=window)
    # 只读：flags 在采集/重算时已落库，读接口不再 sync 写库（避免仪表盘并发死锁）
    quality_map = await quality_map_for_days(db, [latest, prev], sync_missing=False)
    # 按 SKU 级汇总(省="")统计被排除的 SKU 数，仅用于展示计数
    excluded_quality_keys = {
        sku_key
        for (quality_day, sku_key, prov), meta in quality_map.items()
        if prov == "" and quality_day in {latest, prev} and should_exclude_quality(meta, quality_policy)
    }
    district_name = ""

    if district_id is not None:
        tbl = _tbl()
        prov_clauses = ["crawl_date = :d", "district_id = :did"]
        prov_extra: dict[str, Any] = {"did": int(district_id)}
        if cate_id is not None:
            prov_clauses.append("cate_id = :cid")
            prov_extra["cid"] = cate_id
        if scate.strip():
            prov_clauses.append("scate_name = :scate")
            prov_extra["scate"] = scate.strip()
        prov_where = " AND ".join(prov_clauses)

        async def snap_province(target: date) -> dict[str, dict[str, Any]]:
            nonlocal district_name
            res = await db.execute(
                text(
                    f"SELECT goods_name, spec, unit, cate_id, cate_name, scate_name, district_name, price "
                    f"FROM `{tbl}` WHERE {prov_where}"
                ),
                {"d": target, **prov_extra},
            )
            prices_by_sku: dict[str, list[float]] = defaultdict(list)
            meta_by_sku: dict[str, dict[str, Any]] = {}
            for r in res.fetchall():
                if not district_name and r.district_name:
                    district_name = str(r.district_name)
                v = _price_to_float(r.price)
                if v is None or v <= 0:
                    continue
                sk = make_sku_key(r.goods_name, r.spec or "", r.unit or "", r.cate_id or 0, r.scate_name or "")
                prices_by_sku[sk].append(v)
                if sk not in meta_by_sku:
                    label = _sku_label(r.goods_name, r.spec or "", r.unit or "")
                    if r.scate_name:
                        label = f"{label} · {r.scate_name}"
                    meta_by_sku[sk] = {
                        "sku_key": sk,
                        "label": label,
                        "cate_id": int(r.cate_id or 0),
                        "cate_name": r.cate_name or "",
                    }
            out: dict[str, dict[str, Any]] = {}
            for sk, vals in prices_by_sku.items():
                m = meta_by_sku[sk]
                med = float(_stat_median(vals))
                out[sk] = {**m, "p": med, "prov": 1, "sample_count": len(vals)}
            return out

        cur = await snap_province(latest)
        old = await snap_province(prev)
        prov_filter = True
    else:
        snap_clauses = ["crawl_date = :d", "median_price > 0"]
        snap_extra: dict[str, Any] = {}
        if cate_id is not None:
            snap_clauses.append("cate_id = :cid")
            snap_extra["cid"] = cate_id
        if scate.strip():
            snap_clauses.append("scate_name = :scate")
            snap_extra["scate"] = scate.strip()
        snap_where = " AND ".join(snap_clauses)

        async def snap(target: date) -> dict[str, dict[str, Any]]:
            res = await db.execute(
                text(
                    f"SELECT sku_key, goods_name, spec, unit, cate_id, cate_name, scate_name, median_price, province_count, sample_count "
                    f"FROM `{AGG_TBL}` WHERE {snap_where}"
                ),
                {"d": target, **snap_extra},
            )
            return {
                r.sku_key: {
                    "sku_key": r.sku_key,
                    "label": _sku_label(r.goods_name, r.spec or "", r.unit or "") + (f" · {r.scate_name}" if r.scate_name else ""),
                    "cate_id": int(r.cate_id or 0),
                    "cate_name": r.cate_name or "",
                    "p": float(r.median_price),
                    "prov": int(r.province_count or 0),
                    "sample_count": int(r.sample_count or 0),
                }
                for r in res.fetchall()
            }

        cur = await snap(latest)
        old = await snap(prev)
        prov_filter = False

    recs = []
    excluded_count = len(excluded_quality_keys)
    by_cate_changes: dict[int, list[float]] = defaultdict(list)
    for sk, c in cur.items():
        o = old.get(sk)
        if not o or o["p"] <= 0.5 or c["p"] <= 0.5:
            continue
        # 省份口径按该省查质量；全国口径按 SKU 级汇总(省="")查
        _qprov = district_name if district_id is not None else ""
        current_quality = quality_map.get((latest, sk, _qprov))
        previous_quality = quality_map.get((prev, sk, _qprov))
        if should_exclude_quality(current_quality, quality_policy) or should_exclude_quality(previous_quality, quality_policy):
            continue
        if not prov_filter and (c["prov"] < min_provinces or o["prov"] < min_provinces):
            continue
        pct = (c["p"] - o["p"]) / o["p"] * 100
        if abs(pct) > max_pct:
            continue
        ln = math.log(c["p"] / o["p"])
        quality_level = max(
            (current_quality or {}).get("quality_level", "none"),
            (previous_quality or {}).get("quality_level", "none"),
            key={"none": 0, "medium": 1, "high": 2}.get,
        )
        quality_reasons = list(
            dict.fromkeys(
                ((current_quality or {}).get("quality_reasons") or [])
                + ((previous_quality or {}).get("quality_reasons") or [])
            )
        )
        recs.append({
            "sku_key": sk, "label": c["label"], "goods_name": c["label"],
            "cate_id": c["cate_id"], "cate_name": c["cate_name"],
            "old": round(o["p"], 2), "new": round(c["p"], 2),
            "pct": round(pct, 1), "ln": ln,
            "quality_level": quality_level,
            "quality_reasons": quality_reasons,
            "sample_count": int(c.get("sample_count") or 0),
        })
        by_cate_changes[c["cate_id"]].append(ln)
    cstat = {}
    for cid, arr in by_cate_changes.items():
        med = _stat_median(arr)
        mad = max(_stat_median([abs(x - med) for x in arr]), 0.02)
        cstat[cid] = (med, mad)
    for r in recs:
        med, mad = cstat.get(r["cate_id"], (0.0, 0.02))
        r["z"] = round((r["ln"] - med) / (1.4826 * mad), 2)
        r["anomaly_kind"] = "data_anomaly" if r["quality_level"] == "high" else "market_movement"
        r["confidence_score"] = round(
            min(
                99.0,
                45.0
                + min(35.0, abs(r["z"]) * 10.0)
                + min(19.0, r["sample_count"])
                - (15.0 if r["quality_level"] == "medium" else 0.0),
            ),
            1,
        )
        del r["ln"]
    gainers = sorted([r for r in recs if r["pct"] > 0], key=lambda x: x["pct"], reverse=True)[:limit]
    losers = sorted([r for r in recs if r["pct"] < 0], key=lambda x: x["pct"])[:limit]
    return {
        "latest_date": _fmt_day(latest),
        "window": window,
        "district_id": district_id,
        "district_name": district_name,
        "quality_policy": quality_policy,
        "excluded_count": excluded_count,
        "quality_summary": {
            "policy": quality_policy,
            "excluded_count": excluded_count,
            "flagged_included_count": sum(1 for row in recs if row["quality_level"] != "none"),
        },
        "gainers": gainers,
        "losers": losers,
    }


@router.get("/analytics/change-ranking")
async def analytics_change_ranking(
    district_id: Optional[int] = Query(default=None),
    cate_id: Optional[int] = Query(default=None),
    scate: str = "",
    baseline_days: int = Query(default=3, ge=1, le=14),
    limit: int = Query(default=10, ge=1, le=100),
    max_pct: float = Query(default=150.0),
    min_provinces: int = Query(default=6, ge=1),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """涨跌幅排名：统计日价 vs 前 baseline_days 日均价（与行情页涨跌幅排名一致）。"""
    return await compute_change_ranking(
        db,
        district_id=district_id,
        cate_id=cate_id,
        scate=scate,
        baseline_days=baseline_days,
        limit=limit,
        max_pct=max_pct,
        min_provinces=min_provinces,
    )


@router.get("/analytics/change-ratio")
async def analytics_change_ratio(
    district_id: Optional[int] = Query(default=None),
    cate_id: Optional[int] = Query(default=None),
    scate: str = "",
    baseline_days: int = Query(default=3, ge=1, le=14),
    flat_threshold_pct: float = Query(default=1.0, ge=0, le=20),
    max_pct: float = Query(default=150.0),
    min_provinces: int = Query(default=6, ge=1),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """涨跌比例：日（vs 前 N 日均价）、周（周末 vs 周初）、月（月末 vs 月初）SKU 占比。"""
    return await compute_change_ratio(
        db,
        district_id=district_id,
        cate_id=cate_id,
        scate=scate,
        baseline_days=baseline_days,
        flat_threshold_pct=flat_threshold_pct,
        max_pct=max_pct,
        min_provinces=min_provinces,
    )


@router.get("/analytics/spread")
async def analytics_spread(
    cate_id: Optional[int] = Query(default=None),
    scate: str = "",
    date: str = "",
    limit: int = Query(default=12, ge=1, le=100),
    min_provinces: int = Query(default=6, ge=2),
    max_ratio: float = Query(default=HIGH_RATIO),
    quality_policy: str = Query(default="strict", pattern="^(strict|warn|all)$"),
    transport_cost_pct: float = Query(default=8.0, ge=0, le=100),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """区域价差套利榜：某日各 SKU 的跨省中位价价差。为抗包装/单位记录错误：要求 ≥min_provinces 省，
    对各省中位价做"去掉最高最低各一省"的截尾后再算极差，且剔除原始 max/min>max_ratio 的明显异常 SKU。"""
    quality_policy = normalize_quality_policy(_bare_route_param(quality_policy, "strict"))
    max_ratio = float(_bare_route_param(max_ratio, HIGH_RATIO))
    transport_cost_pct = float(_bare_route_param(transport_cost_pct, 8.0))
    day = _parse_day(date) or await _latest_agg_date(db)
    if day is None:
        return {"date": "", "rows": []}
    tbl = _tbl()
    quality_map = await quality_map_for_days(db, [day], sync_missing=False)
    clauses = ["crawl_date = :d"]
    params: dict[str, Any] = {"d": day}
    if cate_id is not None:
        clauses.append("cate_id = :c")
        params["c"] = cate_id
    if scate.strip():
        clauses.append("scate_name = :scate")
        params["scate"] = scate.strip()
    res = await db.execute(
        text(
            f"SELECT district_name, goods_name, spec, unit, cate_id, cate_name, scate_name, price FROM `{tbl}` WHERE {' AND '.join(clauses)}"
        ),
        params,
    )
    # 按 (SKU, 省) 收集价 —— SKU 已固定品名+规格+单位+分类+子类，天然同口径，不再有跨单位/鲜冻假价差
    sku_prov: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    sku_meta: dict[str, dict[str, str]] = {}
    for r in res.fetchall():
        v = _price_to_float(r.price)
        if v is None or not r.district_name or not r.goods_name:
            continue
        sk = make_sku_key(r.goods_name, r.spec or "", r.unit or "", r.cate_id or 0, r.scate_name or "")
        prov_quality = quality_map.get((day, sk, r.district_name or ""))
        if should_exclude_quality(prov_quality, quality_policy):
            continue  # 逐省剔除：脏省不进价差，不连坐其它省
        if prov_quality and prov_quality.get("corrected_price") is not None:
            v = float(prov_quality["corrected_price"])
        sku_prov[sk][r.district_name].append(v)
        label = _sku_label(r.goods_name, r.spec or "", r.unit or "")
        if r.scate_name:
            label = f"{label} · {r.scate_name}"
        sku_meta.setdefault(sk, {"label": label, "cate": r.cate_name or ""})
    rows = []
    excluded_count = 0
    for sk, provmap_raw in sku_prov.items():
        # 脏省已在上方逐省剔除；此处仅取 SKU 级汇总(省="")用于展示标记
        quality_meta = quality_map.get((day, sk, ""))
        provmap = {prov: _stat_median(vals) for prov, vals in provmap_raw.items() if vals}
        if len(provmap) < min_provinces:
            continue
        items = sorted(provmap.items(), key=lambda kv: kv[1])
        raw_lo, raw_hi = items[0][1], items[-1][1]
        if raw_lo <= 0 or raw_hi / raw_lo > max_ratio:
            excluded_count += 1
            continue  # 极端离群护栏（同 SKU 跨省差异过大几乎必为脏数据）
        trimmed = items[1:-1] if len(items) >= 4 else items  # 截尾去单省离群
        lo_prov, lo = trimmed[0]
        hi_prov, hi = trimmed[-1]
        if lo <= 0:
            continue
        spread_pct = round((hi - lo) / lo * 100, 1)
        rows.append({
            "sku_key": sk,
            "goods_name": sku_meta[sk]["label"], "cate_name": sku_meta[sk]["cate"],
            "min_price": round(lo, 2), "max_price": round(hi, 2),
            "cheapest": lo_prov, "priciest": hi_prov,
            "province_count": len(provmap),
            "sample_count": sum(len(values) for values in provmap_raw.values()),
            "spread_pct": spread_pct,
            "transport_cost_pct": round(transport_cost_pct, 1),
            "net_spread_pct": round(spread_pct - transport_cost_pct, 1),
            "persistence_days": 1,
            "freshness_days": max(0, (_today() - day).days),
            "quality_level": (quality_meta or {}).get("quality_level", "none"),
            "quality_reasons": (quality_meta or {}).get("quality_reasons", []),
        })
    rows.sort(key=lambda x: x["spread_pct"], reverse=True)
    return {
        "date": _fmt_day(day),
        "quality_policy": quality_policy,
        "excluded_count": excluded_count,
        "quality_summary": {
            "policy": quality_policy,
            "excluded_count": excluded_count,
            "flagged_included_count": sum(1 for row in rows if row["quality_level"] != "none"),
        },
        "rows": rows[:limit],
    }


@router.get("/analytics/forecast")
async def analytics_forecast(
    sku_key: str = "",
    district_id: Optional[int] = Query(default=None),
    days: int = Query(default=14, ge=1, le=60),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """读取本地 AutoML 预测快照；没有快照时明确提示训练，不用全国预测冒充省份预测。"""
    if not (sku_key or "").strip():
        return {"status": "empty", "product": "", "ensemble": [], "message": "缺少 SKU"}
    await _ensure_forecast_table(db)
    scope = "province" if district_id is not None else "national"
    did = int(district_id or 0)
    res = await db.execute(
        text(
            f"""
            SELECT forecast_json, metrics_json, sample_count, data_latest_date, trained_at, winner_model, district_name
            FROM `{FORECAST_TBL}`
            WHERE sku_key = :sk AND scope = :scope AND district_id = :did
            LIMIT 1
            """
        ),
        {"sk": sku_key, "scope": scope, "did": did},
    )
    row = res.fetchone()
    if not row:
        _district_name, label, series, raw_series = await _forecast_series_for_scope(db, sku_key, district_id)
        eligible_days = len(series)
        clean_dates = {r["date"] for r in series}
        excluded_dates = [r["date"] for r in raw_series if r["date"] not in clean_dates]
        raw_days = await _raw_forecast_series_day_count(db, sku_key, district_id)
        display_scope = _district_name if scope == "province" and _district_name else ("全国" if scope == "national" else "当前口径")
        quality_hint = await build_forecast_sample_hint(
            db,
            sku_key,
            eligible_days=eligible_days,
            raw_days=raw_days,
            scope_label=f"{display_scope}口径",
        )
        default_msg = "该口径暂无预测快照，请更新当前预测。"
        return {
            "status": "needs_training",
            "product": label,
            "sku_key": sku_key,
            "scope": scope,
            "district_id": did,
            "sample_count": eligible_days,
            "raw_sample_count": raw_days,
            "ensemble": [],
            "history": [{"date": r["date"], "price": round(float(r["avg_price"]), 3)} for r in series[-60:]],
            "raw_history": [{"date": r["date"], "price": round(float(r["avg_price"]), 3)} for r in raw_series[-60:]],
            "excluded_dates": excluded_dates,
            "message": quality_hint or default_msg,
            "quality_hint": quality_hint,
            "reliability": "low",
            "reliability_label": "待训练",
            "reliability_reason": quality_hint or "暂无本地 AutoML 预测快照",
        }
    payload = _json_loads(row.forecast_json, {})
    metrics = _json_loads(row.metrics_json, {})
    ensemble = (payload.get("ensemble") or [])[:days]
    # 原始报价序列（用于「清洗后/原始报价」切换）：现算一次只读序列
    _dn, _lbl, _clean_series, _raw_series = await _forecast_series_for_scope(db, sku_key, district_id)
    _clean_dates = {r["date"] for r in _clean_series}
    payload.update(
        {
            "raw_history": [{"date": r["date"], "price": round(float(r["avg_price"]), 3)} for r in _raw_series[-60:]],
            "excluded_dates": [r["date"] for r in _raw_series if r["date"] not in _clean_dates],
        }
    )
    payload.update(
        {
            "ensemble": ensemble,
            "sample_count": int(row.sample_count or metrics.get("sample_count") or 0),
            "data_latest_date": _fmt_day(row.data_latest_date),
            "trained_at": row.trained_at.isoformat() if row.trained_at else None,
            "winner_model": row.winner_model or metrics.get("winner_model") or payload.get("winner_model") or "",
            "accuracy": {
                "mape": metrics.get("mape"),
                "mae": metrics.get("mae"),
                "hit_rate": metrics.get("hit_rate"),
                "backtest_days": metrics.get("backtest_days"),
            },
            "reliability": metrics.get("reliability") or payload.get("reliability") or "low",
            "reliability_label": metrics.get("reliability_label") or payload.get("reliability_label") or "谨慎参考",
            "reliability_reason": metrics.get("reliability_reason") or payload.get("reliability_reason") or "",
            "model_metrics": metrics.get("models") or [],
        }
    )
    return payload


@router.get("/analytics/forecast/status")
async def analytics_forecast_status(_=Depends(_monitor_guard)):
    return _FORECAST_STATUS


@router.post("/analytics/forecast/train")
async def analytics_forecast_train(
    background_tasks: BackgroundTasks,
    sku_key: str = "",
    district_id: Optional[int] = Query(default=None),
    scope: str = Query(default="single_current"),
    scope_mode: str = Query(default=""),
    _=Depends(_monitor_guard),
):
    if _FORECAST_STATUS.get("running"):
        return {"started": False, "message": "已有预测训练任务在运行", **_FORECAST_STATUS}
    keys = [sku_key] if sku_key.strip() else []
    mode = (scope_mode or scope or "single_current").strip()
    if mode == "current_sku":
        mode = "current_sku_all_scopes"
    if mode == "all_batch":
        # 全量训练已停用：2.5 万 SKU × 多省口径(8万+任务/数十小时)会拖垮系统，禁止触发。
        raise HTTPException(status_code=400, detail="全量训练已停用，请使用热门 SKU 批量训练")
    if mode not in {"single_current", "current_sku_all_scopes", "popular_batch"}:
        mode = "single_current"
    if mode == "single_current" and not keys:
        raise HTTPException(status_code=400, detail="缺少 SKU，无法训练当前预测")
    background_tasks.add_task(
        _train_forecast_batch,
        keys,
        limit=1 if mode in {"single_current", "current_sku_all_scopes"} else (50000 if mode == "all_batch" else 50),
        include_popular=mode == "popular_batch",
        district_limit=40 if mode != "popular_batch" else 12,
        scope_mode=mode,
        single_district_id=district_id,
    )
    if mode == "single_current":
        msg = "已开始训练当前 SKU 的当前省份/全国预测"
    elif mode == "current_sku_all_scopes":
        msg = "已开始训练当前 SKU 的全国及有数据省份预测"
    elif mode == "all_batch":
        msg = "已开始训练全量 SKU 批量预测"
    else:
        msg = "已开始训练客户配置热门 SKU 批量预测"
    return {"started": True, "message": msg}


def _scan_sku_prices_for_day(rows: list[Any]) -> tuple[int, int, dict[str, dict[str, Any]]]:
    """扫描单日 crawl 行：返回 (总行, 可解析行, sku_key → 聚合信息)。"""
    total_rows = 0
    parsed_rows = 0
    sku_agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        total_rows += 1
        v = _price_to_float(r.price)
        if v is None or v <= 0:
            continue
        parsed_rows += 1
        sk = make_sku_key(r.goods_name, r.spec or "", r.unit or "", r.cate_id or 0, r.scate_name or "")
        agg = sku_agg.setdefault(
            sk,
            {
                "sku_key": sk,
                "goods_name": r.goods_name or "",
                "spec": r.spec or "",
                "unit": r.unit or "",
                "cate_id": int(r.cate_id or 0),
                "cate_name": r.cate_name or "",
                "scate_name": r.scate_name or "",
                "min_p": v,
                "max_p": v,
                "provinces": set(),
                "sample_count": 0,
            },
        )
        agg["sample_count"] += 1
        if r.district_name:
            agg["provinces"].add(r.district_name)
        if v < agg["min_p"]:
            agg["min_p"] = v
        if v > agg["max_p"]:
            agg["max_p"] = v
    return total_rows, parsed_rows, sku_agg


@router.get("/analytics/quality")
async def analytics_quality(_=Depends(_monitor_guard), db: AsyncSession = Depends(get_db)):
    """数据可信度面板：最新采集日单日切片 + 指数篮子，~0.5s。
    返回 价格可解析率 / 疑似脏数据 SKU 数 / 指数篮子覆盖度 / 数据新鲜度 / 综合健康度(0-100)。"""
    tbl = _tbl()
    mx_res = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{tbl}`"))
    mx_row = mx_res.fetchone()
    latest = _parse_day(mx_row.mx) if mx_row and mx_row.mx else None
    if latest is None:
        return {"snapshot_date": "", "parse_rate": 0, "suspicious_skus": 0, "distinct_skus": 0,
                "basket_size": 0, "basket_coverage": 0, "freshness_gap_days": None, "health_score": 0}

    res = await db.execute(
        text(
            f"SELECT goods_name, spec, unit, cate_id, cate_name, scate_name, district_name, price "
            f"FROM `{tbl}` WHERE crawl_date = :d"
        ),
        {"d": latest},
    )
    raw_rows = list(res.fetchall())
    total_rows, parsed_rows, sku_agg = _scan_sku_prices_for_day(raw_rows)
    # 只读：flags 已在采集/重算时落库，看板不再 sync 写库（避免并发死锁）
    distinct_skus = len(sku_agg)
    # 命中率口径与正式规则一致：逐省偏离中位数的 high 标记，按 distinct SKU 计
    detected_suspicious = len({f["sku_key"] for f in detect_quality_flags(raw_rows, latest) if f["severity"] == "high"})
    parse_rate = round(parsed_rows / total_rows * 100, 1) if total_rows else 0.0

    # 指数篮子覆盖度（总指数 cate_id=0 的篮子规模 / 当日 distinct SKU）
    bs_res = await db.execute(
        text(f"SELECT basket_size FROM `{IDX_TBL}` WHERE cate_id = 0 ORDER BY idx_date DESC LIMIT 1")
    )
    bs_row = bs_res.fetchone()
    basket_size = int(bs_row.basket_size or 0) if bs_row else 0
    basket_coverage = round(basket_size / distinct_skus * 100, 1) if distinct_skus else 0.0

    gap_days = (_today() - latest).days

    status_res = await db.execute(
        text(
            "SELECT severity, status, COUNT(*) AS n FROM data_quality_flags "
            "WHERE data_date=:d GROUP BY severity, status"
        ),
        {"d": latest},
    )
    status_counts = {
        f"{row.severity}:{row.status}": int(row.n or 0)
        for row in status_res.fetchall()
    }
    trend_res = await db.execute(
        text(
            """
            SELECT data_date, severity, status, district_name, evidence_json
            FROM data_quality_flags
            WHERE data_date >= DATE_SUB(:d, INTERVAL 29 DAY)
            ORDER BY data_date
            """
        ),
        {"d": latest},
    )
    trend_by_day: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, int] = defaultdict(int)
    reviewed_total = 0
    total_flags = 0
    for row in trend_res.fetchall():
        day_key = _fmt_day(row.data_date)
        bucket = trend_by_day.setdefault(day_key, {"date": day_key, "high": 0, "medium": 0, "closed": 0})
        bucket[row.severity if row.severity in {"high", "medium"} else "medium"] += 1
        total_flags += 1
        if row.status in {"confirmed_valid", "corrected", "resolved"}:
            bucket["closed"] += 1
            reviewed_total += 1
        # 问题源省：逐省标记后直接用 flag 的 district_name（真正出错的省）
        if row.district_name:
            source_counts[str(row.district_name)] += 1
        else:
            evidence = parse_evidence(row.evidence_json)
            for key in ("min_province", "max_province"):
                if evidence.get(key):
                    source_counts[str(evidence[key])] += 1
    # headline 统计"有 high 标记的 distinct SKU 数"（逐省后标记是省级，故按 sku_key 去重）
    susp_res = await db.execute(
        text(
            "SELECT COUNT(DISTINCT sku_key) AS n FROM data_quality_flags "
            "WHERE data_date=:d AND severity='high' AND status IN ('open','quarantined')"
        ),
        {"d": latest},
    )
    suspicious = int(susp_res.scalar() or 0)
    # 综合健康度：解析率(40%) + (1-未闭环高风险占比)(25%) + 篮子覆盖(20%) + 新鲜度(15%)
    clean_ratio = (1 - suspicious / distinct_skus) * 100 if distinct_skus else 100.0
    fresh_score = max(0.0, 100.0 - gap_days * 12.0)
    health = round(parse_rate * 0.40 + clean_ratio * 0.25 + min(100.0, basket_coverage) * 0.20 + fresh_score * 0.15, 1)
    await db.commit()

    return {
        "snapshot_date": _fmt_day(latest),
        "parse_rate": parse_rate,
        "suspicious_skus": suspicious,
        "detected_suspicious_skus": detected_suspicious,
        "distinct_skus": distinct_skus,
        "basket_size": basket_size,
        "basket_coverage": basket_coverage,
        "freshness_gap_days": gap_days,
        "health_score": health,
        "status_counts": status_counts,
        "high_risk_open": status_counts.get("high:open", 0) + status_counts.get("high:quarantined", 0),
        "reviewed_count": sum(
            count for key, count in status_counts.items()
            if key.split(":", 1)[-1] in {"confirmed_valid", "corrected", "resolved"}
        ),
        "quality_trend": list(trend_by_day.values()),
        "source_ranking": [
            {"district_name": name, "flag_count": count}
            for name, count in sorted(source_counts.items(), key=lambda item: item[1], reverse=True)[:10]
        ],
        "closure_rate": round(reviewed_total / total_flags * 100, 1) if total_flags else 100.0,
        "rule_hit_rate": round(detected_suspicious / distinct_skus * 100, 3) if distinct_skus else 0.0,
    }


@router.get("/analytics/quality/suspicious-skus")
async def analytics_quality_suspicious_skus(
    date: str = "",
    limit: int = Query(default=500, ge=1, le=500),
    ratio_threshold: float = Query(default=5.0, ge=2.0, le=50.0),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """疑似脏数据 SKU 明细：当日同 SKU 各省最高价/最低价倍数超过阈值（默认>5倍）。"""
    tbl = _tbl()
    day = _parse_day(date)
    if day is None:
        mx_res = await db.execute(text(f"SELECT MAX(crawl_date) AS mx FROM `{tbl}`"))
        mx_row = mx_res.fetchone()
        day = _parse_day(mx_row.mx) if mx_row and mx_row.mx else None
    if day is None:
        return {"snapshot_date": "", "ratio_threshold": ratio_threshold, "total": 0, "rows": []}

    # 只读：直接查已落库的 flags（采集/重算时已写），不再 sync 写库
    res = await db.execute(
        text(
            """
            SELECT id, data_date, sku_key, district_name, goods_name, cate_id, cate_name, scate_name,
                   anomaly_type, severity, reason, evidence_json, status, corrected_price,
                   review_note, reviewed_by_user_id, reviewed_at, updated_at
            FROM data_quality_flags
            WHERE data_date=:d AND anomaly_type='cross_province_price_ratio'
            ORDER BY severity='high' DESC, updated_at DESC
            """
        ),
        {"d": day},
    )
    rows = []
    for row in res.fetchall():
        evidence = parse_evidence(row.evidence_json)
        if float(evidence.get("price_ratio") or 0) <= ratio_threshold:
            continue
        rows.append(
            {
                "id": int(row.id),
                "data_date": _fmt_day(row.data_date),
                "sku_key": row.sku_key,
                "goods_name": row.goods_name,
                "cate_id": int(row.cate_id or 0),
                "cate_name": row.cate_name or "",
                "scate_name": row.scate_name or "",
                "district_name": row.district_name or "",
                "anomaly_type": row.anomaly_type,
                "severity": row.severity,
                "reason": row.reason,
                "status": row.status,
                "corrected_price": float(row.corrected_price) if row.corrected_price is not None else None,
                "review_note": row.review_note or "",
                "reviewed_by_user_id": row.reviewed_by_user_id,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                **evidence,
            }
        )
    total = len(rows)
    rows = rows[:limit]
    await db.commit()
    return {
        "snapshot_date": _fmt_day(day),
        "ratio_threshold": ratio_threshold,
        "total": total,
        "rows": rows,
    }


@router.get("/analytics/quality/flags")
async def analytics_quality_flags(
    date: str = "",
    severity: str = "",
    status: str = "",
    cate_id: Optional[int] = Query(default=None),
    q: str = "",
    limit: int = Query(default=200, ge=1, le=500),
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """Quality workbench list with filters and original evidence."""
    day = _parse_day(date) or await _latest_agg_date(db)
    if day is None:
        return {"snapshot_date": "", "total": 0, "rows": []}
    # 只读：直接查已落库的 flags，不再 sync 写库（避免并发死锁）
    clauses = ["data_date=:d"]
    params: dict[str, Any] = {"d": day, "lim": limit}
    if severity.strip():
        clauses.append("severity=:severity")
        params["severity"] = severity.strip()
    if status.strip():
        clauses.append("status=:status")
        params["status"] = status.strip()
    if cate_id is not None:
        clauses.append("cate_id=:cate_id")
        params["cate_id"] = cate_id
    if q.strip():
        clauses.append("(goods_name LIKE :q OR reason LIKE :q)")
        params["q"] = f"%{q.strip()}%"
    count_res = await db.execute(
        text(f"SELECT COUNT(*) FROM data_quality_flags WHERE {' AND '.join(clauses)}"),
        params,
    )
    result = await db.execute(
        text(
            f"""
            SELECT id, data_date, sku_key, district_name, goods_name, cate_id, cate_name, scate_name,
                   anomaly_type, severity, reason, evidence_json, status, corrected_price,
                   review_note, reviewed_by_user_id, reviewed_at, updated_at
            FROM data_quality_flags
            WHERE {' AND '.join(clauses)}
            ORDER BY severity='high' DESC, updated_at DESC
            LIMIT :lim
            """
        ),
        params,
    )
    rows = []
    for row in result.fetchall():
        rows.append(
            {
                "id": int(row.id),
                "data_date": _fmt_day(row.data_date),
                "sku_key": row.sku_key,
                "district_name": row.district_name or "",
                "goods_name": row.goods_name,
                "cate_id": int(row.cate_id or 0),
                "cate_name": row.cate_name or "",
                "scate_name": row.scate_name or "",
                "anomaly_type": row.anomaly_type,
                "severity": row.severity,
                "reason": row.reason,
                "status": row.status,
                "corrected_price": float(row.corrected_price) if row.corrected_price is not None else None,
                "review_note": row.review_note or "",
                "reviewed_by_user_id": row.reviewed_by_user_id,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                **parse_evidence(row.evidence_json),
            }
        )
    await db.commit()
    return {"snapshot_date": _fmt_day(day), "total": int(count_res.scalar() or 0), "rows": rows}


@router.post("/analytics/quality/flags/{flag_id}/action")
async def analytics_quality_flag_action(
    flag_id: int,
    body: QualityActionBody,
    user: User = Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    action = body.action.strip().lower()
    if action == "confirm":
        raise HTTPException(status_code=400, detail="「确认有效」已废弃，请使用「修正」二次爬虫核验或「隔离」")
    target_status = quality_action_status(action)
    if not target_status:
        raise HTTPException(status_code=400, detail="action 仅支持 correct/isolate/restore")
    if action == "correct" and body.corrected_price is None:
        raise HTTPException(status_code=400, detail="修正操作必须提供 corrected_price")
    await ensure_quality_table(db)
    row_res = await db.execute(
        text("SELECT id, data_date, sku_key FROM data_quality_flags WHERE id=:id"),
        {"id": flag_id},
    )
    flag = row_res.fetchone()
    if not flag:
        raise HTTPException(status_code=404, detail="质量标记不存在")
    await db.execute(
        text(
            """
            UPDATE data_quality_flags
            SET status=:status, corrected_price=:corrected_price, review_note=:note,
                reviewed_by_user_id=:uid, reviewed_at=:reviewed_at
            WHERE id=:id
            """
        ),
        {
            "id": flag_id,
            "status": target_status,
            "corrected_price": body.corrected_price if action == "correct" else None,
            "note": body.note.strip(),
            "uid": int(user.id),
            "reviewed_at": now_naive(),
        },
    )
    await db.commit()
    # Rebuild the affected day so index and future forecast training immediately inherit the review decision.
    await refresh_derived([flag.data_date])
    await db.execute(
        text(f"DELETE FROM `{FORECAST_TBL}` WHERE sku_key=:sku_key"),
        {"sku_key": flag.sku_key},
    )
    await db.commit()
    return {"updated": True, "id": flag_id, "status": target_status, "data_date": _fmt_day(flag.data_date)}


@router.post("/analytics/quality/flags/{flag_id}/verify-recrawl")
async def analytics_quality_flag_verify_recrawl(
    flag_id: int,
    user: User = Depends(require_role("monitor")),
    db: AsyncSession = Depends(get_db),
):
    """对该 SKU 在快照日定向二次爬虫，核验官网是否已修正价格。"""
    if _BACKFILL_STATUS.get("running"):
        raise HTTPException(status_code=409, detail="已有补抓任务在运行，请稍后再试")
    if _LAST_JOB.get("status") == "running":
        raise HTTPException(status_code=409, detail="已有单日采集任务在运行，请稍后再试")
    _ensure_credentials()

    async def _run_targeted_recrawl(day: date, district_ids: set[int], cate_id: int) -> None:
        job: dict[str, Any] = {
            "status": "running",
            "progress": 0,
            "message": f"二次爬虫核验：{day.isoformat()}",
            "updated_at": _now_cn_iso(),
        }
        await _crawl_and_store(
            day,
            job,
            cate_id=cate_id or None,
            only_district_ids=district_ids,
            slow=True,
        )
        if job.get("status") != "completed":
            raise HTTPException(
                status_code=502,
                detail=str(job.get("message") or "二次爬虫核验失败"),
            )

    try:
        result = await verify_flag_by_recrawl(
            db,
            flag_id,
            run_recrawl=_run_targeted_recrawl,
            user_id=int(user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@router.post("/analytics/briefing")
async def analytics_briefing(_=Depends(_monitor_guard)):
    """AI 行情日报：清洗聚合后输出市场环境 / 板块异动 / 分类展望 / 分省要点（研报式结构）。"""
    from services.zg_market_briefing import build_market_insight_report

    async with SessionLocal() as db:
        payload = await build_market_insight_report(db, baseline_days=3)
    payload["generated_at"] = payload.get("generated_at") or _today().isoformat()
    return payload


@router.post("/analytics/daily-report")
async def analytics_daily_report(
    body: Optional[DailyReportBody] = None,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    """LLM 全国农产品价格日报：事实来自库内聚合，输出 PDF 或 JSON 预览。"""
    from fastapi.responses import Response
    from services.zgncpjgw_daily_report import ReportFilter, build_daily_report

    payload_in = body or DailyReportBody()
    fmt = (payload_in.format or "pdf").strip().lower()
    if fmt not in ("json", "pdf"):
        raise HTTPException(status_code=400, detail="format 仅支持 json 或 pdf")
    flt = ReportFilter(
        report_date=payload_in.report_date,
        district_id=payload_in.district_id,
        cate_id=payload_in.cate_id,
        scate=payload_in.scate or "",
        appendix_sku_key=payload_in.appendix_sku_key or "",
        appendix_start_date=payload_in.appendix_start_date or "",
        appendix_end_date=payload_in.appendix_end_date or "",
    )
    try:
        result, pdf_bytes = await build_daily_report(db, flt, output_format=fmt)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="日报生成超时，请稍后重试（PDF 渲染或 LLM 较慢）") from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"日报生成失败：{exc}") from exc

    if fmt == "pdf" and pdf_bytes:
        from routers.chat import _content_disposition

        rd = result.get("facts", {}).get("report_date") or _today().isoformat()
        filename = f"全国农产品价格日报_{rd}"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": _content_disposition(filename, "pdf")},
        )
    return result


_REBUILD_STATUS: dict[str, Any] = {"running": False, "message": "未重建", "updated_at": None}


@router.post("/analytics/rebuild")
async def analytics_rebuild(background_tasks: BackgroundTasks, _=Depends(_monitor_guard)):
    """手动安全网：后台全量重建派生表（daily_agg + price_index）。补抓已会自动重建，此处兜底。"""
    if _REBUILD_STATUS.get("running"):
        return {"started": False, "message": "已有重建任务在运行", **_REBUILD_STATUS}

    async def _run() -> None:
        _REBUILD_STATUS.update({"running": True, "pct": 0, "message": "正在全量重建派生指标…", "updated_at": _now_cn_iso()})

        def _prog(done: int, total: int, label: str) -> None:
            _REBUILD_STATUS.update({"pct": int(done / total * 100) if total else 0, "message": label, "updated_at": _now_cn_iso()})

        try:
            result = await refresh_derived(None, progress=_prog)
            _REBUILD_STATUS.update({"running": False, "pct": 100, "message": f"重建完成：daily_agg {result['agg_rows']} 行 / price_index {result['index_rows']} 行", "updated_at": _now_cn_iso()})
        except Exception as exc:  # noqa: BLE001
            _REBUILD_STATUS.update({"running": False, "message": f"重建失败：{exc}", "updated_at": _now_cn_iso()})

    background_tasks.add_task(_run)
    return {"started": True, "message": "已开始后台重建派生指标"}


@router.get("/analytics/rebuild/status")
async def analytics_rebuild_status(_=Depends(_monitor_guard)):
    return _REBUILD_STATUS
