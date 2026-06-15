#!/usr/bin/env python3
"""Runtime timeout checks against the isolated QA backend."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:18000/api"
OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "qa-reports"
    / "2026-06-12"
    / "evidence"
    / "security"
    / "runtime-resilience.json"
)


def timed_get(client: httpx.Client, path: str, **kwargs):
    started = time.perf_counter()
    try:
        response = client.get(path, **kwargs)
        return {
            "status": response.status_code,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "body_preview": response.text[:500],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        login = client.post(
            "/auth/login",
            json={"username": "delivery001", "password": "demo123"},
        )
        login.raise_for_status()
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        result = {
            "health_before": timed_get(client, "/system/healthz"),
            "ready_before": timed_get(client, "/system/readyz"),
            "delivery_vehicles": timed_get(
                client,
                "/delivery/vehicles",
                headers=headers,
            ),
            "health_after_timeout": timed_get(client, "/system/healthz"),
            "token_recorded": False,
        }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
