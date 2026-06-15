#!/usr/bin/env python3
"""E2E smoke: dirty SKU 福建口径预测应展示 quality_hint 说明。"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000/api"
FRONT = "http://127.0.0.1"


def api(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    login = api("POST", "/auth/login", {"username": "monitor001", "password": "demo123"})
    token = login["token"]

    flags = api("GET", "/zgncpjgw/analytics/quality/flags?limit=50&q=" + urllib.parse.quote("东古"), token=token)
    rows = flags.get("rows") or []
    if not rows:
        print("FAIL: no 东古 dirty sku flags")
        return 1
    row = rows[0]
    sku_key = row["sku_key"]
    prov = row.get("max_province") or "福建"
    filters = api("GET", "/zgncpjgw/analytics/filters", token=token)
    did = {d["name"]: d["id"] for d in filters.get("districts") or []}.get(prov)
    if not did:
        print(f"FAIL: district id for {prov}")
        return 1

    fc = api(
        "GET",
        f"/zgncpjgw/analytics/forecast?sku_key={urllib.parse.quote(sku_key)}&district_id={did}&days=14",
        token=token,
    )
    hint = fc.get("quality_hint") or ""
    if not hint or "疑似脏数据" not in hint:
        print("FAIL API quality_hint:", hint or "(empty)")
        return 1
    print("PASS API:", hint[:80], "...")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP UI: playwright not installed")
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(f"{FRONT}/login", wait_until="networkidle", timeout=120000)
        page.fill('input[placeholder*="账号"], input[type="text"]', "monitor001")
        page.fill('input[type="password"]', "demo123")
        page.click('button:has-text("登录"), button[type="submit"]')
        page.wait_for_url("**/monitor/**", timeout=60000)
        page.goto(f"{FRONT}/monitor/dashboard?module=mining", wait_until="networkidle", timeout=120000)
        time.sleep(2)

        # 打开脏数据弹窗
        page.locator("text=疑似脏数据").first.click(timeout=15000)
        page.wait_for_selector("text=疑似脏数据 SKU 明细", timeout=15000)
        page.locator("button:has-text('去查询')").first.click()
        page.wait_for_timeout(2500)

        # 点福建省份
        page.locator(".province-picker button").filter(has_text="福建").click(timeout=15000)
        page.wait_for_timeout(3000)

        content = page.content()
        if "疑似脏数据" not in content and "质量规则" not in content and "源站原始报价" not in content:
            page.screenshot(path="/tmp/forecast_hint_fail.png", full_page=True)
            print("FAIL UI: hint text not found on page")
            browser.close()
            return 1
        page.screenshot(path="/tmp/forecast_hint_pass.png", full_page=True)
        print("PASS UI: dirty-data hint visible on mining page")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
