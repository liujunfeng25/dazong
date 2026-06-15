#!/usr/bin/env python3
"""Targeted dynamic security checks for the isolated Dazong QA stack."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import httpx
import websockets


BASE_URL = "http://127.0.0.1:18000"
OUTPUT = Path("qa-reports/2026-06-12/evidence/security/dynamic-security-checks.json")


def mysql_scalar(sql: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "dazong-qa-mysql-qa-1",
            "mysql",
            "--default-character-set=utf8mb4",
            "-uroot",
            "-pqa_root_password",
            "-N",
            "-B",
            "dazong_qa",
            "-e",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def item_ids(body: Any) -> set[int]:
    if isinstance(body, dict):
        for key in ("items", "data", "rows"):
            if isinstance(body.get(key), list):
                body = body[key]
                break
    if not isinstance(body, list):
        return set()
    ids: set[int] = set()
    for row in body:
        if isinstance(row, dict) and row.get("id") is not None:
            try:
                ids.add(int(row["id"]))
            except (TypeError, ValueError):
                pass
    return ids


async def login(client: httpx.AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "demo123"},
    )
    response.raise_for_status()
    return str(response.json()["token"])


async def request_json(
    client: httpx.AsyncClient,
    path: str,
    token: str | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.get(path, headers=headers, params=params)
    try:
        body = response.json()
    except Exception:
        body = response.text[:500]
    return response.status_code, body


async def check_disabled_monitor_ws(monitor_token: str) -> dict[str, Any]:
    monitor_id = int(mysql_scalar("SELECT id FROM users WHERE username='monitor001' LIMIT 1"))
    mysql_scalar(f"UPDATE users SET status='disabled' WHERE id={monitor_id}")
    result: dict[str, Any] = {"monitor_user_id": monitor_id}
    try:
        uri = f"ws://127.0.0.1:18000/ws/monitor?token={monitor_token}"
        try:
            async with websockets.connect(uri, open_timeout=5) as websocket:
                result["connected_while_disabled"] = True
                try:
                    first = await asyncio.wait_for(websocket.recv(), timeout=3)
                    result["received_message"] = bool(first)
                    result["message_bytes"] = len(first) if isinstance(first, (str, bytes)) else None
                except asyncio.TimeoutError:
                    result["received_message"] = False
        except Exception as exc:
            result["connected_while_disabled"] = False
            result["error_type"] = type(exc).__name__
    finally:
        mysql_scalar(f"UPDATE users SET status='active' WHERE id={monitor_id}")
    return result


async def run() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20) as client:
        tokens = {
            role: await login(client, username)
            for role, username in {
                "factory": "factory001",
                "supplier": "supplier001",
                "monitor": "monitor001",
            }.items()
        }

        generic_status, generic_orders = await request_json(
            client,
            "/api/orders",
            tokens["factory"],
            {
                "created_date_start": "2020-01-01",
                "created_date_end": "2030-01-01",
            },
        )
        factory_status, factory_orders = await request_json(
            client,
            "/api/factory/orders",
            tokens["factory"],
        )
        generic_ids = item_ids(generic_orders)
        factory_ids = item_ids(factory_orders)
        results["factory_global_order_visibility"] = {
            "generic_status": generic_status,
            "factory_status": factory_status,
            "generic_order_count": len(generic_ids),
            "factory_scoped_order_count": len(factory_ids),
            "unrelated_visible_count": len(generic_ids - factory_ids),
            "sample_unrelated_ids": sorted(generic_ids - factory_ids)[:10],
        }

        contract_status, contracts = await request_json(
            client,
            "/api/contracts/list",
            tokens["supplier"],
        )
        tender_status, tenders = await request_json(
            client,
            "/api/contracts/tender/list",
            tokens["supplier"],
        )
        results["supplier_commercial_data_visibility"] = {
            "contract_status": contract_status,
            "contract_count": len(item_ids(contracts)),
            "tender_status": tender_status,
            "tender_count": len(item_ids(tenders)),
        }

        client_accounts_status, client_accounts = await request_json(
            client, "/api/demo/client-accounts"
        )
        supplier_accounts_status, supplier_accounts = await request_json(
            client, "/api/demo/supplier-accounts"
        )
        results["public_demo_account_enumeration"] = {
            "client_status": client_accounts_status,
            "client_count": len(client_accounts) if isinstance(client_accounts, list) else None,
            "supplier_status": supplier_accounts_status,
            "supplier_count": len(supplier_accounts)
            if isinstance(supplier_accounts, list)
            else None,
        }

        vehicle_no = mysql_scalar(
            "SELECT vehicle_no FROM delivery_vehicles WHERE status='active' ORDER BY id LIMIT 1"
        )
        driver_response = await client.post(
            "/api/driver/login",
            json={"vehicle_no": vehicle_no, "password": "demo123"},
        )
        driver_result: dict[str, Any] = {
            "vehicle_no": vehicle_no,
            "login_status": driver_response.status_code,
        }
        if driver_response.status_code == 200:
            driver_token = driver_response.json()["token"]
            trip_status, trips = await request_json(
                client,
                "/api/driver/trips/today",
                driver_token,
                {"planning_date": "2026-06-12"},
            )
            driver_result["trips_status"] = trip_status
            driver_result["trip_count"] = len(item_ids(trips))
        results["driver_shared_password"] = driver_result
        results["disabled_monitor_websocket"] = await check_disabled_monitor_ws(
            tokens["monitor"]
        )

    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
