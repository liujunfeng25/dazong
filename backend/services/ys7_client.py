from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from config import settings

_TIMEOUT = 10.0
_TOKEN_CACHE_TTL_SEC = 6 * 3600
_cached_access_token: str = ""
_cached_access_token_at: float = 0.0


@dataclass
class YS7Channel:
    device_code: str
    device_name: str
    channel_no: int
    raw: dict[str, Any]


class YS7Client:
    def __init__(self) -> None:
        self.base_url = (settings.ys7_base_url or "").rstrip("/")
        self.app_key = (settings.ys7_app_key or "").strip()
        self.app_secret = (settings.ys7_app_secret or "").strip()

    async def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{self.base_url}{path}", data=data)
            resp.raise_for_status()
            payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("萤石接口响应格式错误")
        return payload

    async def _get_access_token(self) -> str:
        if not self.base_url or not self.app_key or not self.app_secret:
            raise ValueError("萤石配置未完成")
        payload = await self._post(
            "/token/get",
            {"appKey": self.app_key, "appSecret": self.app_secret},
        )
        if str(payload.get("code")) != "200":
            raise ValueError(str(payload.get("msg") or "萤石token获取失败"))
        token = str((payload.get("data") or {}).get("accessToken") or "").strip()
        if not token:
            raise ValueError("萤石token为空")
        return token

    async def get_access_token(self) -> str:
        global _cached_access_token, _cached_access_token_at
        now = time.time()
        if _cached_access_token and now < _cached_access_token_at + _TOKEN_CACHE_TTL_SEC:
            return _cached_access_token
        token = await self._get_access_token()
        _cached_access_token = token
        _cached_access_token_at = now
        return token

    async def list_channels(self) -> list[YS7Channel]:
        token = await self._get_access_token()
        page_start = 0
        channels: list[YS7Channel] = []
        while True:
            payload = await self._post(
                "/device/list",
                {"accessToken": token, "pageStart": page_start, "pageSize": 50},
            )
            if str(payload.get("code")) != "200":
                raise ValueError(str(payload.get("msg") or "萤石设备列表获取失败"))
            data = payload.get("data")
            if isinstance(data, dict):
                devices = data.get("list") or []
            elif isinstance(data, list):
                devices = data
            else:
                devices = []
            if not devices:
                break
            for device in devices:
                serial = str(device.get("deviceSerial") or "").strip()
                if not serial:
                    continue
                name = str(device.get("deviceName") or serial).strip()
                ch_payload = await self._post(
                    "/device/camera/list",
                    {"accessToken": token, "deviceSerial": serial},
                )
                if str(ch_payload.get("code")) != "200":
                    continue
                cams = (ch_payload.get("data") or []) or []
                for cam in cams:
                    channel_no = int(cam.get("channelNo") or 1)
                    channels.append(
                        YS7Channel(
                            device_code=serial,
                            device_name=name,
                            channel_no=channel_no,
                            raw={"device": device, "camera": cam},
                        )
                    )
            page_start += 1
        return channels

    @staticmethod
    def build_ezopen_live_url(device_serial: str, channel_no: int, quality: int) -> str:
        """Ys7Api::buildEzopenLiveUrl"""
        serial = str(device_serial or "").strip()
        ch = int(channel_no or 1)
        if not serial or ch < 1:
            return ""
        suffix = "hd.live" if int(quality) == 1 else "live"
        return f"ezopen://open.ys7.com/{serial}/{ch}.{suffix}"

    async def try_live_video_open(self, device_serial: str, channel_no: int) -> None:
        """Ys7Api::tryLiveVideoOpen"""
        if not settings.ys7_live_open_before_get:
            return
        try:
            token = await self.get_access_token()
        except ValueError:
            return
        serial = str(device_serial).strip()
        ch = int(channel_no or 1)
        if not serial or ch < 1:
            return
        source = f"{serial}:{ch}"
        try:
            await self._post("/live/video/open", {"accessToken": token, "source": source})
        except (httpx.HTTPError, ValueError, OSError):
            return

    @staticmethod
    def _pick_playback_url_from_live_address_data(data: Any) -> str:
        """Ys7Api::pickPlaybackUrlFromLiveAddressData（仅接受 http(s) 直链）。"""
        if isinstance(data, list):
            for item in data:
                u = YS7Client._pick_playback_url_from_live_address_data(item)
                if u:
                    return u
            return ""
        if not isinstance(data, dict):
            return ""
        for k in ("url", "address", "hls", "hlsHd", "hlsSd", "liveUrl", "streamUrl"):
            v = data.get(k)
            if isinstance(v, str):
                u = v.strip()
                if u.startswith("http"):
                    return u
        for _k, v in data.items():
            if isinstance(v, (dict, list)):
                u = YS7Client._pick_playback_url_from_live_address_data(v)
                if u:
                    return u
        return ""

    async def get_live_address_hls(
        self, device_serial: str, channel_no: int, quality: int, *, wake_first: bool = False
    ) -> str:
        """Ys7Api::getLiveAddressHls（仅 live/address/get + 与 PHP 相同重试/兼容分支）。"""
        serial = str(device_serial or "").strip()
        ch = int(channel_no or 1)
        if not serial or ch < 1:
            raise ValueError("参数错误")

        expire = int(settings.ys7_live_url_expire)
        expire = max(60, min(86400, expire))
        proto = int(settings.ys7_live_protocol)
        if proto < 1 or proto > 4:
            proto = 2

        token = await self.get_access_token()
        source = f"{serial}:{ch}"

        def params_primary() -> dict[str, Any]:
            p: dict[str, Any] = {
                "accessToken": token,
                "source": source,
                "protocol": proto,
                "supportH265": 0,
            }
            if settings.ys7_live_address_include_expire:
                p["expire"] = expire
            return p

        async def post_live_address_get(body: dict[str, Any]) -> dict[str, Any]:
            return await self._post("/live/address/get", body)

        if wake_first or settings.ys7_live_open_before_get:
            await self.try_live_video_open(serial, ch)
            if wake_first:
                delay = float(settings.ys7_battery_wake_seconds or 0)
                if delay > 0:
                    await asyncio.sleep(delay)

        resp = await post_live_address_get(params_primary())
        if str(resp.get("code")) == "200":
            url = self._pick_playback_url_from_live_address_data(resp.get("data"))
            if url:
                return url

        if not wake_first:
            await self.try_live_video_open(serial, ch)

        resp = await post_live_address_get(params_primary())
        if str(resp.get("code")) == "200":
            url = self._pick_playback_url_from_live_address_data(resp.get("data"))
            if url:
                return url
            raise ValueError("live/address 未返回 URL")

        legacy = {
            "accessToken": token,
            "deviceSerial": serial,
            "channelNo": ch,
            "protocol": 2,
            "quality": int(quality),
            "expire": expire,
            "supportH265": 0,
        }
        resp2 = await post_live_address_get(legacy)
        if str(resp2.get("code")) == "200":
            url = self._pick_playback_url_from_live_address_data(resp2.get("data"))
            if url:
                return url

        msg = str(resp.get("msg") or resp2.get("msg") or "萤石直播地址获取失败")
        raise ValueError(msg)

    async def get_live_address(self, device_serial: str, channel_no: int = 1) -> str:
        """配送端取「标清」HLS，等同 sxw getPlayableHlsForDevice 里对 sd 的选取（quality=2）。"""
        return await self.get_live_address_hls(device_serial, channel_no, 2)

    async def get_device_status(self, device_serial: str, channel_no: int = 1) -> dict[str, Any]:
        """萤石设备状态（电池机含 battryStatus 电量百分比）。"""
        serial = str(device_serial or "").strip().upper()
        ch = int(channel_no or 1)
        if not serial or ch < 1:
            raise ValueError("设备参数错误")
        token = await self._get_access_token()
        payload = await self._post(
            "/device/status/get",
            {"accessToken": token, "deviceSerial": serial, "channelNo": ch},
        )
        if str(payload.get("code")) != "200":
            raise ValueError(str(payload.get("msg") or "萤石设备状态获取失败"))
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    async def ptz_start(
        self, device_serial: str, channel_no: int, direction: int, speed: int = 1
    ) -> None:
        """萤石开放平台：开始云台控制。direction 0-11，speed 1-2（海康设备不可为 0）。"""
        await self._ptz("start", device_serial, channel_no, direction, speed)

    async def ptz_stop(
        self, device_serial: str, channel_no: int, direction: int, speed: int = 1
    ) -> None:
        """萤石开放平台：停止云台控制（direction 须与 start 一致）。"""
        await self._ptz("stop", device_serial, channel_no, direction, speed)

    async def _ptz(
        self, action: str, device_serial: str, channel_no: int, direction: int, speed: int
    ) -> None:
        serial = str(device_serial or "").strip().upper()
        ch = int(channel_no or 1)
        if not serial or ch < 1:
            raise ValueError("设备参数错误")
        d = int(direction)
        if d < 0 or d > 11:
            raise ValueError("云台方向参数无效")
        spd = int(speed)
        if spd < 1 or spd > 2:
            spd = 1
        token = await self._get_access_token()
        path = "/device/ptz/start" if action == "start" else "/device/ptz/stop"
        payload = await self._post(
            path,
            {
                "accessToken": token,
                "deviceSerial": serial,
                "channelNo": ch,
                "direction": d,
                "speed": spd,
            },
        )
        if str(payload.get("code")) != "200":
            raise ValueError(str(payload.get("msg") or "萤石云台控制失败"))
