#!/usr/bin/env python3
"""
一次性验证：同一设备绑 A 车后不能再绑 B 车；候选列表不含该设备。
需 MySQL 可连（与后端 .env 一致），在项目 backend 目录执行：
  PYTHONPATH=. python3 scripts/verify_vehicle_device_binding.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import httpx
from httpx import ASGITransport

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import app


async def run() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as client:
        r = await client.post(
            "/api/auth/login",
            json={"username": "delivery001", "password": "demo123"},
        )
        assert r.status_code == 200, f"登录失败 {r.status_code} {r.text}"
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        rv = await client.get("/api/delivery/vehicles", headers=h)
        assert rv.status_code == 200, f"车辆列表 {rv.status_code} {rv.text}"
        vehicles = rv.json()
        suf = uuid.uuid4().hex[:8]
        while len(vehicles) < 2:
            plate = f"脚本测{suf}{len(vehicles)}"
            cr = await client.post(
                "/api/delivery/vehicles",
                headers=h,
                json={
                    "vehicle_no": plate,
                    "vehicle_model": "测试",
                    "driver_name": "测",
                    "status": "active",
                },
            )
            assert cr.status_code == 200, f"创建车辆 {cr.status_code} {cr.text}"
            vehicles.append(cr.json())
        va, vb = int(vehicles[0]["id"]), int(vehicles[1]["id"])

        # 每次新建设备，避免复用「已绑在其他车辆」的旧设备导致首次绑定 400
        suf2 = uuid.uuid4().hex[:12]
        cr = await client.post(
            "/api/delivery/devices",
            headers=h,
            json={
                "device_type": "beidou",
                "vendor": "beidou",
                "device_code": f"VERIFY-BIND-{suf2}",
                "device_name": "脚本验证",
                "channel_no": 0,
                "status": "active",
            },
        )
        assert cr.status_code == 200, f"创建设备 {cr.status_code} {cr.text}"
        device_id = int(cr.json()["id"])

        for vid in (va, vb):
            br = await client.get(f"/api/delivery/vehicles/{vid}/bindings", headers=h)
            if br.status_code == 200:
                for b in br.json():
                    await client.delete(
                        f"/api/delivery/vehicles/{vid}/bindings/{b['id']}",
                        headers=h,
                    )

        b1 = await client.post(
            f"/api/delivery/vehicles/{va}/bindings",
            headers=h,
            json={"device_id": device_id},
        )
        assert b1.status_code == 200, f"首次绑定应成功 {b1.status_code} {b1.text}"

        b2 = await client.post(
            f"/api/delivery/vehicles/{vb}/bindings",
            headers=h,
            json={"device_id": device_id},
        )
        assert b2.status_code == 400, f"第二次绑定应返回 400，实际 {b2.status_code} {b2.text}"
        detail = str(b2.json().get("detail", ""))
        assert "解绑" in detail or "占用" in detail or "其他车辆" in detail, detail

        listed = await client.get(
            "/api/delivery/devices",
            headers=h,
            params={"bind_vehicle_id": vb},
        )
        assert listed.status_code == 200, f"候选设备列表 {listed.status_code}"
        ids = {int(x["id"]) for x in listed.json()}
        assert device_id not in ids, f"设备仍出现在车辆 {vb} 的候选列表中"

        br = await client.get(f"/api/delivery/vehicles/{va}/bindings", headers=h)
        for b in br.json():
            await client.delete(
                f"/api/delivery/vehicles/{va}/bindings/{b['id']}",
                headers=h,
            )


if __name__ == "__main__":
    try:
        asyncio.run(run())
        print("OK: 重复绑定已拦截；候选列表已过滤；测试绑定已清理")
    except AssertionError as exc:
        print("FAIL:", exc)
        sys.exit(1)
