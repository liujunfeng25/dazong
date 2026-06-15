from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0
_TOKEN_TTL_SEC = 50 * 60
_ACCESS_PREFIX = "/api/data-api/elitechAccess"
_CN_TZ = ZoneInfo("Asia/Shanghai")
_CACHE_TTL_DEVICE_LIST = 300.0
_CACHE_TTL_REALTIME = 45.0
_CACHE_TTL_HISTORY = 120.0

_api_lock = asyncio.Lock()
_last_api_at: float = 0.0
_response_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class ElitechApiError(Exception):
    def __init__(self, message: str, *, code: Optional[int | str] = None) -> None:
        super().__init__(message)
        self.code = code


class _ElitechTokenStore:
    """进程内 token 缓存：只有过期/缺失时才请求 getToken。"""

    token: str = ""
    expires_at: float = 0.0
    _lock = asyncio.Lock()

    @classmethod
    def read(cls) -> Optional[str]:
        if cls.token and time.time() < cls.expires_at:
            return cls.token
        return None

    @classmethod
    def write(cls, token: str, *, ttl: float = _TOKEN_TTL_SEC) -> str:
        cls.token = token
        cls.expires_at = time.time() + ttl
        return token

    @classmethod
    def clear(cls) -> None:
        cls.token = ""
        cls.expires_at = 0.0


def _parse_time_param(value: Optional[str | int | float]) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = int(value)
        return ts if ts > 1_000_000_000_000 else ts
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        ts = int(text)
        return ts // 1000 if ts > 1_000_000_000_000 else ts
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=_CN_TZ)
            return int(dt.timestamp())
        except ValueError:
            continue
    return None


def _cache_key(path: str, body: dict[str, Any]) -> str:
    return f"{path}:{json.dumps(body, sort_keys=True, ensure_ascii=False)}"


class ElitechClient:
    """精创冷云 i-elitech.net 标准 API（data-api / elitechAccess）。"""

    def __init__(self) -> None:
        self.base_url = (settings.elitech_base_url or "https://www.i-elitech.net").rstrip("/")
        self.key_id = (settings.elitech_client_id or "").strip()
        self.key_secret = (settings.elitech_key_secret or "").strip()
        self.username = (settings.elitech_username or "").strip()
        self.password = (settings.elitech_password or "").strip()

    def configured(self) -> bool:
        return bool(self.base_url and self.key_id and self.key_secret and self.username and self.password)

    def _known_device_guids(self) -> list[str]:
        raw = (settings.elitech_device_guids or "").strip()
        if not raw:
            return []
        guids: list[str] = []
        seen: set[str] = set()
        for chunk in raw.replace("\n", ",").split(","):
            guid = chunk.strip()
            if guid and guid not in seen:
                seen.add(guid)
                guids.append(guid)
        return guids

    def _credentials(self) -> dict[str, str]:
        return {
            "keyId": self.key_id,
            "keySecret": self.key_secret,
        }

    @staticmethod
    def _ok_code(code: Any) -> bool:
        return str(code) in ("0", "200")

    @staticmethod
    def _parse_payload(payload: dict[str, Any]) -> dict[str, Any]:
        code = payload.get("code")
        if code is not None and not ElitechClient._ok_code(code):
            msg = str(payload.get("msg") or payload.get("message") or "精创接口调用失败")
            raise ElitechApiError(msg, code=code)
        return payload

    @staticmethod
    def _cache_get(key: str) -> Optional[dict[str, Any]]:
        entry = _response_cache.get(key)
        if entry and time.time() < entry[0]:
            return entry[1]
        return None

    @staticmethod
    def _cache_set(key: str, payload: dict[str, Any], ttl: float) -> None:
        _response_cache[key] = (time.time() + ttl, payload)

    async def _remote_post(self, path: str, body: dict[str, Any], *, headers: Optional[dict[str, str]] = None) -> dict[str, Any]:
        global _last_api_at
        url = f"{self.base_url}{path}"
        async with _api_lock:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(url, json=body, headers=headers or {})
            _last_api_at = time.time()
        if resp.status_code == 401 and headers and "Authorization" in headers:
            _ElitechTokenStore.clear()
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("精创接口响应格式错误")
        return self._parse_payload(payload)

    async def _fetch_token_remote(self) -> str:
        if not self.configured():
            raise ValueError("精创冷云未配置完整（需 Key ID、Key Secret、API 用户名与密码）")
        body = {
            **self._credentials(),
            "userName": self.username,
            "password": self.password,
        }
        logger.info("Elitech: 请求 getToken（缓存未命中）")
        last_err: Optional[ElitechApiError] = None
        payload: dict[str, Any] | None = None
        for attempt in range(2):
            try:
                payload = await self._remote_post(f"{_ACCESS_PREFIX}/getToken", body)
                break
            except ElitechApiError as exc:
                last_err = exc
                if str(exc.code) == "5110" and attempt == 0:
                    await asyncio.sleep(10.5)
                    continue
                raise
        if payload is None:
            if last_err:
                raise last_err
            raise ElitechApiError("精创 accessToken 获取失败")

        token = payload.get("data")
        if isinstance(token, dict):
            token = token.get("accessToken") or token.get("token")
        token = str(token or "").strip()
        if not token:
            raise ElitechApiError("精创 accessToken 为空")
        if not token.lower().startswith("bearer "):
            token = f"Bearer {token}"
        return _ElitechTokenStore.write(token)

    async def _ensure_token(self) -> str:
        cached = _ElitechTokenStore.read()
        if cached:
            return cached

        async with _ElitechTokenStore._lock:
            cached = _ElitechTokenStore.read()
            if cached:
                return cached
            return await self._fetch_token_remote()

    async def _post_auth(
        self,
        path: str,
        body: dict[str, Any],
        *,
        cache_ttl: float = 0,
    ) -> dict[str, Any]:
        cache_key = _cache_key(path, body) if cache_ttl > 0 else ""
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        token = await self._ensure_token()
        req_body = {**self._credentials(), **body}
        last_err: Optional[Exception] = None

        for attempt in range(2):
            try:
                parsed = await self._remote_post(
                    path,
                    req_body,
                    headers={"Authorization": token},
                )
                if cache_key:
                    self._cache_set(cache_key, parsed, cache_ttl)
                return parsed
            except ElitechApiError as exc:
                last_err = exc
                if str(exc.code) == "5110" and attempt == 0:
                    await asyncio.sleep(10.5)
                    continue
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401 and attempt == 0:
                    _ElitechTokenStore.clear()
                    token = await self._ensure_token()
                    continue
                raise
            except Exception as exc:
                last_err = exc
                raise

        if last_err:
            raise last_err
        raise ElitechApiError("精创接口调用失败")

    def _device_body(self, device_guid: str, **extra: Any) -> dict[str, Any]:
        guid = str(device_guid).strip()
        body: dict[str, Any] = {
            "deviceGuid": guid,
            "deviceGuids": [guid],
            "subUid": 0,
            **extra,
        }
        return body

    def _history_time_body(
        self,
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        default_hours: int = 24,
    ) -> dict[str, int]:
        end_ts = _parse_time_param(end_time) or int(time.time())
        start_ts = _parse_time_param(start_time) or (end_ts - default_hours * 3600)
        if start_ts > end_ts:
            start_ts, end_ts = end_ts, start_ts
        return {"startTime": start_ts, "endTime": end_ts}

    async def list_open_devices(self) -> dict[str, Any]:
        guids = self._known_device_guids()
        if guids:
            return await self._post_auth(
                f"{_ACCESS_PREFIX}/getDeviceInfo",
                {"deviceGuids": guids},
                cache_ttl=_CACHE_TTL_DEVICE_LIST,
            )
        try:
            return await self._post_auth(
                f"{_ACCESS_PREFIX}/getOpenDeviceList",
                {},
                cache_ttl=_CACHE_TTL_DEVICE_LIST,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        return {"code": 0, "message": "Successful", "data": []}

    async def get_device_info(self, device_guid: str) -> dict[str, Any]:
        return await self._post_auth(
            f"{_ACCESS_PREFIX}/getDeviceInfo",
            self._device_body(device_guid),
            cache_ttl=_CACHE_TTL_DEVICE_LIST,
        )

    async def get_realtime(self, device_guid: str) -> dict[str, Any]:
        return await self._post_auth(
            f"{_ACCESS_PREFIX}/getRealTimeData",
            self._device_body(device_guid),
            cache_ttl=_CACHE_TTL_REALTIME,
        )

    async def get_realtime_curve(self, device_guid: str) -> dict[str, Any]:
        return await self.get_history_data(
            device_guid,
            page=0,
            rows=500,
            default_hours=24,
        )

    async def get_history_data(
        self,
        device_guid: str,
        *,
        page: int = 0,
        rows: int = 50,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        default_hours: int = 24,
    ) -> dict[str, Any]:
        body = self._device_body(
            device_guid,
            pageNum=max(int(page), 0) + 1,
            pageSize=int(rows),
            **self._history_time_body(
                start_time=start_time,
                end_time=end_time,
                default_hours=default_hours,
            ),
        )
        return await self._post_auth(
            f"{_ACCESS_PREFIX}/getHistoryData",
            body,
            cache_ttl=_CACHE_TTL_HISTORY,
        )

    async def get_history_curve(
        self,
        device_guid: str,
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict[str, Any]:
        return await self.get_history_data(
            device_guid,
            page=0,
            rows=1000,
            start_time=start_time,
            end_time=end_time,
        )

    async def get_warnings(
        self,
        device_guid: str,
        *,
        page: int = 0,
        rows: int = 50,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict[str, Any]:
        body = self._device_body(
            device_guid,
            pageNum=max(int(page), 0) + 1,
            pageSize=int(rows),
            **self._history_time_body(start_time=start_time, end_time=end_time),
        )
        try:
            return await self._post_auth(
                f"{_ACCESS_PREFIX}/getAlarmData",
                body,
                cache_ttl=_CACHE_TTL_HISTORY,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"code": 0, "message": "Successful", "data": []}
            raise
