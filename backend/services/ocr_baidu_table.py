"""
百度表格文字识别 API：https://ai.baidu.com/ai-doc/OCR/Al1zvpylt
POST v1/table，解析为 { tables: [{ headers, rows }], key_values }。
"""
from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import List

import httpx

logger = logging.getLogger(__name__)

TABLE_API_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/table"
TIMEOUT = 60.0
MAX_CONNECT_ATTEMPTS = 4
CONNECT_RETRY_SLEEP_SEC = 0.7


def _build_grid_from_body(body: List[dict]) -> List[List[str]]:
    if not body:
        return []
    max_r = max(c.get("row_end", 0) for c in body)
    max_c = max(c.get("col_end", 0) for c in body)
    if max_r <= 0 or max_c <= 0:
        return []
    grid = [["" for _ in range(max_c)] for _ in range(max_r)]
    for c in body:
        words = (c.get("words") or "").strip()
        rs, re = c.get("row_start", 0), c.get("row_end", 0)
        cs, ce = c.get("col_start", 0), c.get("col_end", 0)
        for r in range(rs, min(re, max_r)):
            for col in range(cs, min(ce, max_c)):
                grid[r][col] = words
    return grid


def _table_result_to_structured(table: dict) -> dict:
    header_list = table.get("header") or []
    headers = [str(h.get("words") or "").strip() for h in header_list]
    body = table.get("body") or []
    grid = _build_grid_from_body(body)
    if not headers and grid:
        headers = [str(i) for i in range(len(grid[0]))]
    if headers and grid and len(grid[0]) != len(headers):
        nc = max(len(headers), len(grid[0]) if grid else 0)
        headers = (headers + [""] * nc)[:nc]
        grid = [list(row) + [""] * (nc - len(row)) for row in grid]
    return {"headers": headers, "rows": grid}


def parse_baidu_table_response(data: dict) -> dict:
    if "error_code" in data and data.get("error_code"):
        raise RuntimeError(data.get("error_msg", "百度表格识别接口返回错误"))
    tables_result = data.get("tables_result") or []
    tables = []
    for t in tables_result:
        st = _table_result_to_structured(t)
        if st["headers"] or st["rows"]:
            tables.append(st)
    return {"tables": tables, "key_values": []}


def mock_table_structured() -> dict:
    return {
        "tables": [
            {
                "headers": ["品名", "规格", "数量", "单位", "备注"],
                "rows": [
                    ["白菜", "箱", "100", "箱", ""],
                    ["萝卜", "斤", "50", "斤", ""],
                    ["土豆", "袋", "30", "袋", ""],
                ],
            }
        ],
        "key_values": [
            {"key": "单据类型", "value": "采购单（演示）"},
            {"key": "日期", "value": "2026-04-28"},
        ],
    }


async def run_baidu_table_ocr(image_path: Path, api_key: str) -> dict:
    if not (api_key or "").strip():
        raise ValueError("未配置百度表格识别 API Key")
    img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    key = api_key.strip()
    auth = key if key.lower().startswith("bearer ") else f"Bearer {key}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": auth,
    }
    body = {"image": img_b64}
    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt in range(MAX_CONNECT_ATTEMPTS):
            try:
                r = await client.post(TABLE_API_URL, data=body, headers=headers)
                r.raise_for_status()
                return parse_baidu_table_response(r.json())
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                last_err = e
                logger.warning(
                    "百度表格 OCR 请求失败 (%s/%s): %s",
                    attempt + 1,
                    MAX_CONNECT_ATTEMPTS,
                    e,
                )
                if attempt + 1 >= MAX_CONNECT_ATTEMPTS:
                    raise RuntimeError(
                        "连接百度 OCR 失败。请检查网络、系统时间、代理与 API 配置。原始错误："
                        + str(e)
                    ) from e
                await asyncio.sleep(CONNECT_RETRY_SLEEP_SEC * (attempt + 1))
    raise RuntimeError("百度 OCR 未返回") from last_err
