from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from config import settings

_TIMEOUT = 10.0


@dataclass
class BeidouDevice:
    device_code: str
    device_name: str
    raw: dict[str, Any]


class BeidouClient:
    def __init__(self) -> None:
        self.base_url = (settings.gps18_base_url or "").rstrip("/")
        self.username = (settings.gps18_username or "").strip()
        self.password = (settings.gps18_password or "").strip()

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{self.base_url}{path}", params=params)
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("北斗接口响应格式错误")
        return data

    async def login(self) -> dict[str, str]:
        if not self.base_url or not self.username or not self.password:
            raise ValueError("北斗配置未完成")
        # 不同 GPS18 账号体系存在两种登录参数格式，先尝试 ENTERPRISE 形态，再回退旧参数。
        data = await self._request(
            "/GetDateServices.asmx/loginSystem",
            {
                "LoginName": self.username,
                "LoginPassword": self.password,
                "LoginType": "ENTERPRISE",
                "language": "cn",
                "ISMD5": "0",
                "timeZone": "8",
                "apply": "APP",
            },
        )
        if data.get("success") not in (True, "true"):
            data = await self._request(
                "/GetDateServices.asmx/loginSystem",
                {"name": self.username, "pwd": self.password},
            )
        if data.get("success") not in (True, "true"):
            raise ValueError(str(data.get("msg") or "北斗登录失败"))
        payload = data.get("data") or {}
        unit_id = str(data.get("id") or payload.get("id") or "").strip()
        if not unit_id:
            raise ValueError("北斗登录返回缺少单位ID")
        mds = str(data.get("mds") or payload.get("mds") or "").strip()
        return {"unit_id": unit_id, "mds": mds}

    async def list_devices(self) -> list[BeidouDevice]:
        session = await self.login()
        data = await self._request(
            "/GetDateServices.asmx/GetDate",
            {
                "method": "getDeviceListByCustomId",
                "id": session["unit_id"],
                "mapType": "BAIDU",
                "mds": session.get("mds", ""),
            },
        )
        if data.get("success") not in (True, "true"):
            raise ValueError(str(data.get("msg") or "北斗设备拉取失败"))
        rows = data.get("data") or []
        # 部分账号返回 [{key:{字段索引}, records:[[...],[...]]}] 结构，这里转成字典列表
        if rows and isinstance(rows, list) and isinstance(rows[0], dict) and "records" in rows[0]:
            block = rows[0]
            key_map = block.get("key") or {}
            records = block.get("records") or []
            converted = []
            if isinstance(key_map, dict) and isinstance(records, list):
                for rec in records:
                    if not isinstance(rec, list):
                        continue
                    item = {}
                    for name, idx in key_map.items():
                        try:
                            item[str(name)] = rec[int(idx)]
                        except Exception:  # noqa: BLE001
                            continue
                    converted.append(item)
            rows = converted
        devices: list[BeidouDevice] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = self._pick_code(row)
            if not code:
                continue
            name = str(
                row.get("car_no")
                or row.get("device_name")
                or row.get("sim")
                or row.get("macid")
                or code
            ).strip()
            devices.append(BeidouDevice(device_code=code, device_name=name, raw=row))
        return devices

    @staticmethod
    def _pick_code(row: dict[str, Any]) -> str:
        for key in ("macid", "sim_id", "sim", "device_id", "imei", "user_name"):
            val = str(row.get(key) or "").strip()
            if val:
                return val
        return ""
