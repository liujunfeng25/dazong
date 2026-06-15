#!/usr/bin/env python3
"""Run destructive-safe API audit checks against the isolated Dazong QA stack."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx


DEFAULT_USERS = {
    "operation": ("operation001", "demo123"),
    "client": ("client001", "demo123"),
    "supplier": ("supplier001", "demo123"),
    "delivery": ("delivery001", "demo123"),
    "factory": ("factory001", "demo123"),
    "monitor": ("monitor001", "demo123"),
}

ROLE_PROBES = {
    "/api/operation": "client",
    "/api/client": "supplier",
    "/api/supplier": "client",
    "/api/factory": "client",
    "/api/delivery": "client",
    "/api/delivery-sort": "client",
    "/api/monitor": "client",
    "/api/zgncpjgw": "client",
    "/api/xinfadi": "client",
    "/api/chat": "client",
    "/api/demo": "client",
}


def compact_body(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except Exception:
        body = response.text
    body = redact_secrets(body)
    if isinstance(body, str):
        return body[:800]
    encoded = json.dumps(body, ensure_ascii=False)
    if len(encoded) > 1600:
        return encoded[:1600] + "..."
    return body


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if key.lower()
                in {
                    "token",
                    "access_token",
                    "refresh_token",
                    "password",
                    "password_hash",
                    "secret",
                    "app_secret",
                }
                else redact_secrets(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def path_value(name: str, schema: dict[str, Any]) -> str:
    lname = name.lower()
    if schema.get("format") == "date" or "date" in lname:
        return date.today().isoformat()
    if "status" in lname:
        return "active"
    if "role" in lname:
        return "client"
    if "vendor" in lname:
        return "qa"
    if "code" in lname or "sn" in lname or "no" in lname:
        return "1"
    if schema.get("type") == "string":
        return "1"
    return "1"


def concrete_path(path: str, parameters: list[dict[str, Any]]) -> tuple[str, dict[str, str]]:
    query: dict[str, str] = {}
    for parameter in parameters:
        name = parameter.get("name", "")
        schema = parameter.get("schema") or {}
        value = path_value(name, schema)
        if parameter.get("in") == "path":
            path = path.replace("{" + name + "}", value)
        elif parameter.get("in") == "query" and parameter.get("required"):
            query[name] = value
    path = re.sub(r"\{[^}]+\}", "1", path)
    return path, query


def request_kwargs(method: str, operation: dict[str, Any]) -> dict[str, Any]:
    if method in {"get", "delete", "head", "options"}:
        return {}
    content = (operation.get("requestBody") or {}).get("content") or {}
    if "multipart/form-data" in content:
        return {"data": {}}
    if "application/x-www-form-urlencoded" in content:
        return {"data": {}}
    return {"json": {}}


async def login(client: httpx.AsyncClient, username: str, password: str) -> dict[str, Any]:
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    result = {
        "username": username,
        "status": response.status_code,
        "body": compact_body(response),
    }
    if response.status_code == 200:
        payload = response.json()
        result["role"] = payload.get("role")
        result["token"] = payload.get("token")
    return result


async def scan_operation(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    path: str,
    method: str,
    operation: dict[str, Any],
    inherited_parameters: list[dict[str, Any]],
    tokens: dict[str, str],
) -> dict[str, Any]:
    parameters = [*inherited_parameters, *(operation.get("parameters") or [])]
    concrete, query = concrete_path(path, parameters)
    kwargs = request_kwargs(method, operation)
    result: dict[str, Any] = {
        "path": path,
        "method": method.upper(),
        "operation_id": operation.get("operationId"),
        "tags": operation.get("tags") or [],
    }
    async with semaphore:
        for label, auth_header in (
            ("no_token", None),
            ("invalid_token", "Bearer qa.invalid.token"),
        ):
            headers = {"Authorization": auth_header} if auth_header else {}
            try:
                response = await client.request(
                    method,
                    concrete,
                    params=query,
                    headers=headers,
                    timeout=6,
                    **kwargs,
                )
                result[label] = {
                    "status": response.status_code,
                    "body": compact_body(response),
                }
            except Exception as exc:
                result[label] = {"error": f"{type(exc).__name__}: {exc}"}

        probe_role = next(
            (role for prefix, role in ROLE_PROBES.items() if path.startswith(prefix)),
            None,
        )
        if probe_role and probe_role in tokens:
            try:
                response = await client.request(
                    method,
                    concrete,
                    params=query,
                    headers={"Authorization": f"Bearer {tokens[probe_role]}"},
                    timeout=6,
                    **kwargs,
                )
                result["wrong_role"] = {
                    "probe_role": probe_role,
                    "status": response.status_code,
                    "body": compact_body(response),
                }
            except Exception as exc:
                result["wrong_role"] = {
                    "probe_role": probe_role,
                    "error": f"{type(exc).__name__}: {exc}",
                }
    return result


async def post_case(
    client: httpx.AsyncClient,
    path: str,
    token: str,
    payload: dict[str, Any],
    *,
    method: str = "POST",
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra_headers or {})
    try:
        response = await client.request(method, path, json=payload, headers=headers, timeout=20)
        return {
            "method": method,
            "path": path,
            "payload": payload,
            "status": response.status_code,
            "body": compact_body(response),
        }
    except Exception as exc:
        return {
            "method": method,
            "path": path,
            "payload": payload,
            "error": f"{type(exc).__name__}: {exc}",
        }


def extract_items(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    if isinstance(body, dict):
        for key in ("items", "data", "products", "deliveries"):
            value = body.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


async def targeted_tests(
    client: httpx.AsyncClient,
    tokens: dict[str, str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    operation_token = tokens["operation"]

    categories_response = await client.get(
        "/api/operation/categories",
        headers={"Authorization": f"Bearer {operation_token}"},
    )
    categories = extract_items(categories_response.json())
    category1 = next((row for row in categories if row.get("level") == 1), None)
    category2 = next(
        (
            row
            for row in categories
            if row.get("level") == 2
            and category1
            and row.get("parent_id") == category1.get("id")
        ),
        None,
    )
    if not category1 or not category2:
        results.append(
            {
                "case": "fixture.category_pair",
                "status": "blocked",
                "detail": "QA 数据中没有可用的一二级分类组合",
            }
        )
    else:
        base_product = {
            "name": "QA-AUDIT-PRODUCT",
            "category1_id": category1["id"],
            "category2_id": category2["id"],
            "unit": "件",
            "reference_price": 10,
            "standard_type": "standard",
            "quality_report_mode": "batch",
            "status": "active",
        }
        product_cases = {
            "product.standard_with_jin": {**base_product, "unit": "斤"},
            "product.non_standard_with_piece": {
                **base_product,
                "standard_type": "non_standard",
                "unit": "件",
            },
            "product.blank_name": {**base_product, "name": "   "},
            "product.negative_price": {**base_product, "reference_price": -0.01},
            "product.zero_price": {**base_product, "reference_price": 0},
            "product.negative_dimensions": {
                **base_product,
                "length_cm": -1,
                "width_cm": -2,
                "height_cm": -3,
                "unit_weight_kg": -1,
            },
        }
        for case, payload in product_cases.items():
            outcome = await post_case(
                client, "/api/operation/products", operation_token, payload
            )
            outcome["case"] = case
            results.append(outcome)
            body = outcome.get("body")
            if outcome.get("status") in {200, 201} and isinstance(body, dict) and body.get("id"):
                cleanup = await client.delete(
                    f"/api/operation/products/{body['id']}",
                    headers={"Authorization": f"Bearer {operation_token}"},
                )
                outcome["cleanup_status"] = cleanup.status_code

    account_cases = {
        "account.short_password": {
            "username": "qa_short_password",
            "password": "1",
            "role": "operation",
            "company_name": "QA 短密码",
            "status": "active",
        },
        "account.invalid_status": {
            "username": "qa_invalid_status",
            "password": "demo123",
            "role": "operation",
            "company_name": "QA 非法状态",
            "status": "not-a-status",
        },
        "account.invalid_role": {
            "username": "qa_invalid_role",
            "password": "demo123",
            "role": "admin",
            "company_name": "QA 非法角色",
            "status": "active",
        },
    }
    for case, payload in account_cases.items():
        outcome = await post_case(
            client, "/api/operation/accounts", operation_token, payload
        )
        outcome["case"] = case
        results.append(outcome)
        body = outcome.get("body")
        if outcome.get("status") in {200, 201} and isinstance(body, dict) and body.get("id"):
            if case == "account.short_password":
                login_result = await login(client, payload["username"], payload["password"])
                login_result.pop("token", None)
                outcome["short_password_login"] = login_result
            cleanup = await client.delete(
                f"/api/operation/accounts/{body['id']}",
                headers={"Authorization": f"Bearer {operation_token}"},
            )
            outcome["cleanup_status"] = cleanup.status_code

    client_token = tokens["client"]
    canteens_response = await client.get(
        "/api/client/canteens",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    own_canteens = extract_items(canteens_response.json())
    foreign_canteens_response = await client.get(
        "/api/operation/client-canteens",
        params={"school_client_id": 12},
        headers={"Authorization": f"Bearer {operation_token}"},
    )
    foreign_canteens = extract_items(foreign_canteens_response.json())
    if foreign_canteens:
        outcome = await post_case(
            client,
            "/api/client/canteen-session",
            client_token,
            {"canteen_id": foreign_canteens[0]["id"]},
        )
        outcome["case"] = "client.cross_school_canteen"
        results.append(outcome)

    if not own_canteens:
        results.append(
            {
                "case": "fixture.client_canteen",
                "status": "blocked",
                "detail": "client001 没有可用食堂",
            }
        )
        return results

    session_response = await client.post(
        "/api/client/canteen-session",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"canteen_id": own_canteens[0]["id"]},
    )
    if session_response.status_code != 200:
        results.append(
            {
                "case": "fixture.client_canteen_session",
                "status": session_response.status_code,
                "body": compact_body(session_response),
            }
        )
        return results
    canteen_token = session_response.json()["token"]

    meta_response = await client.get(
        "/api/orders/meta",
        headers={"Authorization": f"Bearer {canteen_token}"},
    )
    meta_body = meta_response.json()
    deliveries = extract_items(meta_body)
    if not deliveries and isinstance(meta_body, dict):
        deliveries = meta_body.get("deliveries") or []
    if not deliveries:
        results.append(
            {
                "case": "fixture.active_contract",
                "status": "blocked",
                "detail": "client001 没有有效配送合约",
                "body": compact_body(meta_response),
            }
        )
        return results
    delivery_id = deliveries[0].get("id") or deliveries[0].get("delivery_id")
    products_response = await client.get(
        "/api/orders/products/search",
        params={"delivery_id": delivery_id, "keyword": "", "page": 1, "page_size": 20},
        headers={"Authorization": f"Bearer {canteen_token}"},
    )
    products = extract_items(products_response.json())
    if not products:
        results.append(
            {
                "case": "fixture.order_product",
                "status": "blocked",
                "detail": "有效合约下没有可下单商品",
                "body": compact_body(products_response),
            }
        )
        return results
    product_id = products[0].get("id") or products[0].get("product_id")
    delivery_date = (date.today() + timedelta(days=2)).isoformat()
    base_order = {
        "delivery_id": delivery_id,
        "items": [{"product_id": product_id, "quantity": 1, "unit_price": 0.01}],
        "expected_delivery_date": delivery_date,
        "expected_delivery_slot": "14:00-15:00",
        "service_duration_min": 30,
        "force": True,
    }
    order_cases = {
        "order.empty_items": {**base_order, "items": []},
        "order.zero_quantity": {
            **base_order,
            "items": [{"product_id": product_id, "quantity": 0, "unit_price": 0.01}],
        },
        "order.negative_quantity": {
            **base_order,
            "items": [{"product_id": product_id, "quantity": -1, "unit_price": 0.01}],
        },
    }
    created_order_ids: list[int] = []
    for case, payload in order_cases.items():
        outcome = await post_case(client, "/api/orders", canteen_token, payload)
        outcome["case"] = case
        results.append(outcome)
        body = outcome.get("body")
        if outcome.get("status") in {200, 201} and isinstance(body, dict) and body.get("id"):
            created_order_ids.append(int(body["id"]))

    duplicate_results = await asyncio.gather(
        post_case(client, "/api/orders", canteen_token, base_order),
        post_case(client, "/api/orders", canteen_token, base_order),
    )
    duplicate_ids = []
    for item in duplicate_results:
        body = item.get("body")
        if item.get("status") in {200, 201} and isinstance(body, dict) and body.get("id"):
            duplicate_ids.append(int(body["id"]))
            created_order_ids.append(int(body["id"]))
    results.append(
        {
            "case": "order.concurrent_duplicate_submit",
            "requests": duplicate_results,
            "created_order_ids": duplicate_ids,
        }
    )

    review_source_id = created_order_ids[-1] if created_order_ids else None
    if review_source_id:
        review_outcome = await post_case(
            client,
            f"/api/orders/{review_source_id}/review",
            canteen_token,
            {"rating": 99, "comment": "QA-AUDIT review before completion"},
        )
        review_outcome["case"] = "order.review_before_completion_invalid_rating"
        results.append(review_outcome)

    for order_id in sorted(set(created_order_ids)):
        cleanup = await client.put(
            f"/api/orders/{order_id}/cancel",
            headers={"Authorization": f"Bearer {canteen_token}"},
        )
        results.append(
            {
                "case": "cleanup.cancel_order",
                "order_id": order_id,
                "status": cleanup.status_code,
                "body": compact_body(cleanup),
            }
        )
    return results


async def run(args: argparse.Namespace) -> int:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(
        base_url=args.base_url,
        follow_redirects=False,
        timeout=10,
    ) as client:
        openapi_response = await client.get("/openapi.json")
        openapi_response.raise_for_status()
        openapi = openapi_response.json()
        (output / "openapi.json").write_text(
            json.dumps(openapi, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        login_results: dict[str, dict[str, Any]] = {}
        tokens: dict[str, str] = {}
        for expected_role, (username, password) in DEFAULT_USERS.items():
            result = await login(client, username, password)
            login_results[expected_role] = {k: v for k, v in result.items() if k != "token"}
            if result.get("token"):
                tokens[expected_role] = str(result["token"])
        (output / "login_results.json").write_text(
            json.dumps(login_results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        operations = []
        semaphore = asyncio.Semaphore(args.concurrency)
        for path, path_item in openapi.get("paths", {}).items():
            inherited = path_item.get("parameters") or []
            for method, operation in path_item.items():
                if method.lower() not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                }:
                    continue
                operations.append(
                    scan_operation(
                        client,
                        semaphore,
                        path,
                        method.lower(),
                        operation,
                        inherited,
                        tokens,
                    )
                )
        scan_results = await asyncio.gather(*operations)
        (output / "api_auth_scan.json").write_text(
            json.dumps(scan_results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        target_results: list[dict[str, Any]]
        if set(DEFAULT_USERS).issubset(tokens):
            target_results = await targeted_tests(client, tokens)
        else:
            target_results = [
                {
                    "case": "targeted_tests",
                    "status": "blocked",
                    "detail": "一个或多个演示角色无法登录",
                }
            ]
        (output / "api_targeted_tests.json").write_text(
            json.dumps(target_results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    protected = sum(
        1
        for row in scan_results
        if row.get("no_token", {}).get("status") in {401, 403}
    )
    invalid_rejected = sum(
        1
        for row in scan_results
        if row.get("invalid_token", {}).get("status") in {401, 403}
    )
    unexpected_no_token = [
        row
        for row in scan_results
        if row["path"] not in {"/api/auth/login", "/api/system/healthz"}
        and row.get("no_token", {}).get("status") not in {401, 403}
    ]
    summary = {
        "base_url": args.base_url,
        "path_count": len(openapi.get("paths", {})),
        "operation_count": len(scan_results),
        "no_token_rejected": protected,
        "invalid_token_rejected": invalid_rejected,
        "unexpected_no_token_count": len(unexpected_no_token),
        "unexpected_no_token": [
            {
                "path": row["path"],
                "method": row["method"],
                "result": row.get("no_token"),
            }
            for row in unexpected_no_token
        ],
    }
    (output / "api_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument(
        "--output",
        default="qa-reports/2026-06-12/evidence/api",
    )
    parser.add_argument("--concurrency", type=int, default=12)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
