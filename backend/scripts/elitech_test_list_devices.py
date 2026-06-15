#!/usr/bin/env python3
"""精创冷云 API V2 连通性测试（i-elitech.net）。需在 backend/.env 配置 ELITECH_USERNAME（API 用户名）/PASSWORD。"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.elitech_client import ElitechApiError, ElitechClient
from services.elitech_meta import normalize_device_list


async def main() -> None:
    client = ElitechClient()
    if not client.configured():
        print("请在 backend/.env 配置 ELITECH_CLIENT_ID、ELITECH_KEY_SECRET、ELITECH_USERNAME（API 用户名）、ELITECH_PASSWORD")
        sys.exit(1)
    try:
        payload = await client.list_open_devices()
        devices = normalize_device_list(payload)
        print(json.dumps({"devices": devices, "raw": payload}, ensure_ascii=False, indent=2))
    except ElitechApiError as e:
        print(f"API error code={e.code}: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(3)


if __name__ == "__main__":
    asyncio.run(main())
