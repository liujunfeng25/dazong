from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from config import settings

_TIMEOUT = 10.0


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

    async def get_live_address(self, device_code: str, channel_no: int = 1) -> str:
        token = await self._get_access_token()
        serial = str(device_code).strip()
        ch = int(channel_no or 1)

        # 新版接口（不需要 source）
        payload = await self._post(
            "/v2/live/address/get",
            {
                "accessToken": token,
                "deviceSerial": serial,
                "channelNo": ch,
                "protocol": 2,  # HLS
                "quality": 2,
                "expireTime": 300,
            },
        )
        if str(payload.get("code")) == "200":
            data = payload.get("data") or {}
            if isinstance(data, dict):
                for key in ("url", "hlsHd", "hls", "rtmpHd", "rtmp", "flvHd", "flv"):
                    value = data.get(key)
                    if value:
                        return str(value)

        # 兼容旧接口（需要 source=序列号:通道号）
        payload = await self._post(
            "/live/address/get",
            {
                "accessToken": token,
                "source": f"{serial}:{ch}",
                "protocol": 2,
                "quality": 2,
                "expireTime": 300,
            },
        )
        if str(payload.get("code")) != "200":
            raise ValueError(str(payload.get("msg") or "萤石直播地址获取失败"))
        data = payload.get("data") or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        if isinstance(data, dict):
            for key in ("url", "hlsHd", "hls", "rtmpHd", "rtmp", "flvHd", "flv"):
                value = data.get(key)
                if value:
                    return str(value)
        raise ValueError("萤石未返回可用直播地址")
