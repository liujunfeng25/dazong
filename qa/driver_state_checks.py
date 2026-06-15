#!/usr/bin/env python3
"""Destructive driver workflow checks for the isolated QA database."""

from __future__ import annotations

import json
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:18000/api"
OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "qa-reports"
    / "2026-06-12"
    / "evidence"
    / "android"
    / "driver-state-checks.json"
)


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=20.0) as client:
        login = client.post(
            "/driver/login",
            json={"vehicle_no": "京B67890", "password": "demo123"},
        )
        login.raise_for_status()
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        before = client.get("/driver/trips/42", headers=headers)
        before.raise_for_status()
        before_json = before.json()
        target_stop = next(
            stop for stop in before_json["stops"] if int(stop["id"]) == 179
        )
        first_stop = next(
            stop for stop in before_json["stops"] if int(stop["sequence"]) == 1
        )

        deliver = client.post("/driver/stops/179/deliver", headers=headers)
        after = client.get("/driver/trips/42", headers=headers)

    payload = {
        "scenario": "Deliver sequence 5 before sequence 1 on a canceled trip",
        "trip_id": 42,
        "trip_status_before": before_json["status"],
        "first_stop_before": first_stop,
        "target_stop_before": target_stop,
        "deliver_status": deliver.status_code,
        "deliver_body": deliver.json(),
        "trip_status_after": after.json()["status"],
        "stops_after": after.json()["stops"],
        "token_recorded": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "trip_status_before": payload["trip_status_before"],
                "target_sequence": target_stop["sequence"],
                "deliver_status": deliver.status_code,
                "trip_status_after": payload["trip_status_after"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
