#!/usr/bin/env python3
"""Concurrent receive/idempotency check against one isolated QA order."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:18000/api"
ORDER_ID = 2648
CANTEEN_ID = 51
IDEMPOTENCY_KEY = "qa-receive-concurrency-20260612"
OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "qa-reports"
    / "2026-06-12"
    / "evidence"
    / "database"
    / "receive-concurrency.json"
)


def db_snapshot() -> dict[str, object]:
    sql = f"""
SELECT
  o.status,
  o.version,
  (SELECT COUNT(*) FROM bills b WHERE b.order_id=o.id),
  (SELECT COUNT(*) FROM order_status_logs l WHERE l.order_id=o.id),
  (SELECT COUNT(*) FROM idempotency_keys k
    WHERE k.scope='order_receive' AND k.resource_id=o.id
      AND k.idempotency_key='{IDEMPOTENCY_KEY}'),
  (SELECT COUNT(*) FROM iot_data i WHERE i.device_id=CONCAT('SCALE-', o.id))
FROM orders o WHERE o.id={ORDER_ID};
"""
    result = subprocess.run(
        [
            "mysql",
            "-h127.0.0.1",
            "-P13306",
            "-uroot",
            "-pqa_root_password",
            "-D",
            "dazong_qa",
            "-N",
            "-B",
            "-e",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    values = result.stdout.strip().split("\t")
    return {
        "order_status": values[0],
        "order_version": int(values[1]),
        "bill_count": int(values[2]),
        "status_log_count": int(values[3]),
        "idempotency_key_count": int(values[4]),
        "iot_scale_row_count": int(values[5]),
    }


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        login = await client.post(
            "/auth/login",
            json={"username": "client001", "password": "demo123"},
        )
        login.raise_for_status()
        base_headers = {"Authorization": f"Bearer {login.json()['token']}"}
        session = await client.post(
            "/client/canteen-session",
            headers=base_headers,
            json={"canteen_id": CANTEEN_ID},
        )
        session.raise_for_status()
        headers = {
            "Authorization": f"Bearer {session.json()['token']}",
            "Idempotency-Key": IDEMPOTENCY_KEY,
        }

        before = db_snapshot()
        gate = asyncio.Event()

        async def submit() -> dict[str, object]:
            await gate.wait()
            try:
                response = await client.post(
                    f"/orders/{ORDER_ID}/receive",
                    headers=headers,
                    json={},
                )
                return {
                    "status": response.status_code,
                    "body": response.text[:1000],
                }
            except Exception as exc:  # noqa: BLE001
                return {"error_type": type(exc).__name__, "error": str(exc)}

        tasks = [asyncio.create_task(submit()) for _ in range(2)]
        gate.set()
        responses = await asyncio.gather(*tasks)
        after = db_snapshot()

    payload = {
        "order_id": ORDER_ID,
        "same_idempotency_key": True,
        "before": before,
        "responses": responses,
        "after": after,
        "token_recorded": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
