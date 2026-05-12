"""
验证：同一设备不能重复绑定到第二辆车（需可连 MySQL，与 test_system_health 相同环境）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.verify_vehicle_device_binding import run as verify_vehicle_binding  # noqa: E402


def test_no_duplicate_binding_across_vehicles():
    asyncio.run(verify_vehicle_binding())
