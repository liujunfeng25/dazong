#!/usr/bin/env python3
"""Compare legacy bills and period statements after client settlement."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:18000/api"
ORDER_ID = 2648
CANTEEN_ID = 51
OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "qa-reports"
    / "2026-06-12"
    / "evidence"
    / "database"
    / "settlement-consistency.json"
)


def query(sql: str) -> list[dict[str, object]]:
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
    rows = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        kind, role, direction, status, count = line.split("\t")
        rows.append(
            {
                "kind": kind,
                "role": role,
                "direction": direction,
                "status": status,
                "count": int(count),
            }
        )
    return rows


def snapshot() -> list[dict[str, object]]:
    return query(
        f"""
SELECT 'bill', role, bill_type, status, COUNT(*)
FROM bills WHERE order_id={ORDER_ID}
GROUP BY role,bill_type,status
UNION ALL
SELECT 'statement', role, direction, status, COUNT(*)
FROM billing_statements
WHERE JSON_CONTAINS(source_snapshot_json, '{ORDER_ID}', '$.order_ids')
GROUP BY role,direction,status
ORDER BY 1,2,3,4;
"""
    )


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        login = client.post(
            "/auth/login",
            json={"username": "client001", "password": "demo123"},
        )
        login.raise_for_status()
        session = client.post(
            "/client/canteen-session",
            headers={"Authorization": f"Bearer {login.json()['token']}"},
            json={"canteen_id": CANTEEN_ID},
        )
        session.raise_for_status()
        headers = {
            "Authorization": f"Bearer {session.json()['token']}",
            "Idempotency-Key": "qa-settle-consistency-20260612",
        }
        before = snapshot()
        response = client.post(f"/orders/{ORDER_ID}/settle", headers=headers)
        after = snapshot()

    payload = {
        "order_id": ORDER_ID,
        "before": before,
        "settle_response": {
            "status": response.status_code,
            "body": response.text[:1000],
        },
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
    main()
