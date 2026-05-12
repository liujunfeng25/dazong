import asyncio

import pytest
from fastapi import HTTPException

from routers.delivery import _normalize_device_payload, _validate_binding_limits


class _FakeSession:
    def __init__(self, value: int):
        self.value = value

    async def scalar(self, _stmt):
        return self.value


class _FakeDevice:
    def __init__(self, vendor: str, device_type: str):
        self.vendor = vendor
        self.device_type = device_type


def test_normalize_device_payload_reject_invalid_pair():
    class _Payload:
        device_type = "camera"
        vendor = "beidou"
        device_code = "X001"
        device_name = "d"
        channel_no = 0
        status = "active"

    with pytest.raises(HTTPException) as err:
        _normalize_device_payload(_Payload())
    assert err.value.status_code == 400
    assert "北斗设备类型必须是 beidou" in err.value.detail


def test_validate_binding_limits_beidou_second_should_fail():
    db = _FakeSession(1)
    device = _FakeDevice(vendor="beidou", device_type="beidou")
    with pytest.raises(HTTPException) as err:
        asyncio.run(_validate_binding_limits(db, vehicle_id=1, device=device))
    assert err.value.status_code == 400
    assert "最多绑定1个北斗设备" in err.value.detail


def test_validate_binding_limits_ys7_fourth_should_fail():
    db = _FakeSession(3)
    device = _FakeDevice(vendor="ys7", device_type="camera")
    with pytest.raises(HTTPException) as err:
        asyncio.run(_validate_binding_limits(db, vehicle_id=2, device=device))
    assert err.value.status_code == 400
    assert "最多绑定3个萤石摄像头" in err.value.detail
