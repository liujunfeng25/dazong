"""快麦云打印 cloud.kuaimai.com API 封装。"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from config import settings
from models import ClientCanteen, Order, OrderItemAllocation, Product, User

PRINT_URL = "https://cloud.kuaimai.com/api/cloud/print/tsplTemplatePrint"
RESULT_URL = "https://cloud.kuaimai.com/api/cloud/print/result"
BATCH_SIZE = 50
CHINA_TZ = timezone(timedelta(hours=8))
# 快麦结果码 2006：任务已受理但结果尚未生成，需继续轮询（非最终失败）
KUAIMAI_RESULT_PENDING_CODES = frozenset({2006})
# 快麦结果码 6021：按序列号查询过于频繁，退避后重试
KUAIMAI_RESULT_RATE_LIMIT_CODE = 6021


class KuaimaiPrintError(Exception):
    def __init__(self, message: str, *, code: Any = None, raw: Any = None):
        super().__init__(message)
        self.code = code
        self.raw = raw


def resolve_printer_sn(user: User) -> str:
    sn = (getattr(user, "kuaimai_printer_sn", None) or "").strip()
    if not sn:
        sn = (settings.kuaimai_printer_sn or "").strip()
    return sn


def _sign_value_to_string(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def create_sign(params: dict[str, Any], secret: str) -> str:
    filtered = {
        k: v
        for k, v in params.items()
        if k != "sign" and v is not None and v != ""
    }
    sign_str = "".join(k + _sign_value_to_string(filtered[k]) for k in sorted(filtered.keys()))
    return hashlib.md5((secret + sign_str + secret).encode("utf-8")).hexdigest()


def china_now_str() -> str:
    return datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _require_credentials() -> tuple[str, str, int, str]:
    app_id = (settings.kuaimai_app_id or "").strip()
    app_secret = (settings.kuaimai_app_secret or "").strip()
    template_id = int(settings.kuaimai_template_id or 0)
    bind_table = (settings.kuaimai_bind_table or "FoodLink").strip() or "FoodLink"
    if not app_id or not app_secret:
        raise KuaimaiPrintError("未配置快麦云打印 appId/appSecret")
    if template_id <= 0:
        raise KuaimaiPrintError("未配置快麦云打印模板 ID（KUAIMAI_TEMPLATE_ID）")
    return app_id, app_secret, template_id, bind_table


def build_label_fields(
    *,
    order: Order,
    alloc: OrderItemAllocation,
    product: Product,
    canteen_name: str,
    supplier_user: User,
    print_time: Optional[str] = None,
) -> dict[str, str]:
    spec = (product.spec or "").strip()
    unit = (product.unit or "").strip()
    if spec and unit:
        spec_unit = f"{spec}/{unit}"
    elif spec:
        spec_unit = spec
    elif unit:
        spec_unit = unit
    else:
        spec_unit = "-"

    exp_date = order.expected_delivery_date
    if isinstance(exp_date, date):
        expected_delivery_date = exp_date.isoformat()
    elif exp_date:
        expected_delivery_date = str(exp_date)
    else:
        expected_delivery_date = "-"

    return {
        "product_name": (product.name or "").strip() or "-",
        "spec_unit": spec_unit,
        "allocation_id": str(int(alloc.id)),
        "allocation_label": f"{order.order_no}-A{int(alloc.id)}",
        "print_time": print_time or china_now_str(),
        "expected_delivery_date": expected_delivery_date,
        "expected_delivery_slot": (order.expected_delivery_slot or "").strip() or "-",
        "supplier_name": (supplier_user.company_name or supplier_user.username or "").strip() or "-",
        "canteen_name": (canteen_name or "").strip() or "-",
        "order_no": (order.order_no or "").strip() or "-",
        "line_no": str(int(alloc.line_no)),
    }


def _raise_http_from_kuaimai(resp: dict[str, Any], default: str) -> None:
    msg = str(resp.get("message") or resp.get("exceptionMessage") or default)
    code = resp.get("code")
    raise KuaimaiPrintError(msg, code=code, raw=resp)


async def _post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    app_id, app_secret, _, _ = _require_credentials()
    body = {**body, "appId": app_id}
    body["sign"] = create_sign(body, app_secret)
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        resp = await client.post(url, json=body)
    try:
        data = resp.json()
    except Exception as exc:
        raise KuaimaiPrintError(f"快麦接口响应非 JSON（HTTP {resp.status_code}）") from exc
    if not isinstance(data, dict):
        raise KuaimaiPrintError("快麦接口响应格式异常", raw=data)
    return data


async def tspl_template_print(sn: str, field_rows: list[dict[str, str]]) -> dict[str, Any]:
    """提交标签打印；field_rows 为模板字段 dict 列表，每项一张标签。"""
    if not sn:
        raise KuaimaiPrintError("未配置云打印机序列号")
    if not field_rows:
        raise KuaimaiPrintError("没有可打印的分单")
    _, _, template_id, bind_table = _require_credentials()
    print_time = china_now_str()
    render_items = build_render_data_array(field_rows, bind_table=bind_table, print_time=print_time)

    body = {
        "timestamp": print_time,
        "sn": sn,
        "templateId": template_id,
        "renderDataArray": json.dumps(render_items, ensure_ascii=False, separators=(",", ":")),
        "printTimes": 1,
    }
    data = await _post_json(PRINT_URL, body)
    if data.get("status") is not True:
        _raise_http_from_kuaimai(data, "快麦云打印提交失败")
    payload = data.get("data") or {}
    job_ids = [str(i) for i in (payload.get("jobIds") or [])]
    return {"job_ids": job_ids, "raw": data}


def build_render_data_array(
    field_rows: list[dict[str, str]],
    *,
    bind_table: Optional[str] = None,
    print_time: Optional[str] = None,
) -> list[dict[str, list[dict[str, str]]]]:
    """构造快麦模板渲染数据，供打印提交和本地 dry-run 校验共用。"""
    table = (bind_table or settings.kuaimai_bind_table or "FoodLink").strip() or "FoodLink"
    ts = print_time or china_now_str()
    return [{table: [{**row, "print_time": ts}]} for row in field_rows]


async def query_print_results(sn: str, job_ids: list[str]) -> list[dict[str, Any]]:
    if not job_ids:
        return []
    body = {
        "timestamp": china_now_str(),
        "sn": sn,
        "jobIdStr": json.dumps(job_ids, ensure_ascii=False),
    }
    data = await _post_json(RESULT_URL, body)
    if data.get("status") is not True:
        if int(data.get("code") or 0) == KUAIMAI_RESULT_RATE_LIMIT_CODE:
            return []
        _raise_http_from_kuaimai(data, "快麦打印结果查询失败")
    rows = data.get("data") or []
    return list(rows) if isinstance(rows, list) else []


def _is_pending_print_result_row(row: dict[str, Any]) -> bool:
    code = int(row.get("code") or 0)
    if code in KUAIMAI_RESULT_PENDING_CODES:
        return True
    if code == 2000:
        return False
    desc = str(row.get("desc") or "")
    return "未查询到打印结果" in desc and code not in (2000,)


def _normalize_job_id(value: Any) -> str:
    """统一 jobId 键，避免接口返回 int/float 与提交时不一致。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def _verify_timing_for_label_count(label_count: int) -> tuple[float, float, int]:
    """按本批标签张数估算轮询节奏；张数越多，快麦落库/出结果通常越慢。"""
    n = max(1, int(label_count or 1))
    initial_wait = min(18.0, 2.5 + 0.15 * n)
    poll_interval = min(4.0, 1.5 + 0.05 * min(n, 50))
    max_polls = min(24, 8 + n // 4)
    return initial_wait, poll_interval, max_polls


async def verify_print_results(
    sn: str,
    job_ids: list[str],
    *,
    label_count: int = 1,
    initial_wait_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
    max_polls: int | None = None,
) -> None:
    """轮询打印结果；任一任务非 2000 则抛错，结果未就绪则重试。"""
    if not job_ids or not settings.kuaimai_verify_print_result:
        return

    if initial_wait_seconds is None or poll_interval_seconds is None or max_polls is None:
        auto_initial, auto_interval, auto_polls = _verify_timing_for_label_count(label_count)
        if initial_wait_seconds is None:
            initial_wait_seconds = auto_initial
        if poll_interval_seconds is None:
            poll_interval_seconds = auto_interval
        if max_polls is None:
            max_polls = auto_polls

    await asyncio.sleep(initial_wait_seconds)
    pending = list(job_ids)

    for attempt in range(max_polls):
        rows = await query_print_results(sn, pending)
        by_id = {
            _normalize_job_id(r.get("jobId")): r
            for r in rows
            if r.get("jobId") is not None
        }

        failures: list[str] = []
        next_pending: list[str] = []
        for jid in pending:
            row = by_id.get(_normalize_job_id(jid))
            if not row:
                next_pending.append(jid)
                continue
            if _is_pending_print_result_row(row):
                next_pending.append(jid)
                continue
            code = int(row.get("code") or 0)
            if code != 2000:
                failures.append(f"任务 {jid}: {row.get('desc') or code}")

        if failures:
            raise KuaimaiPrintError("；".join(failures))
        if not next_pending:
            return

        pending = next_pending
        if attempt < max_polls - 1:
            await asyncio.sleep(poll_interval_seconds)

    raise KuaimaiPrintError(
        "；".join(f"任务 {jid}: 未查询到打印结果，请稍后再试" for jid in pending)
    )


async def print_label_fields_batches(sn: str, field_rows: list[dict[str, str]]) -> list[str]:
    """分批提交（每批最多 50 张），返回全部 jobIds。"""
    all_job_ids: list[str] = []
    for i in range(0, len(field_rows), BATCH_SIZE):
        chunk = field_rows[i : i + BATCH_SIZE]
        result = await tspl_template_print(sn, chunk)
        job_ids = result.get("job_ids") or []
        await verify_print_results(sn, job_ids, label_count=len(chunk))
        all_job_ids.extend(job_ids)
        if i + BATCH_SIZE < len(field_rows):
            await asyncio.sleep(1.0)
    return all_job_ids


def kuaimai_error_to_http(exc: KuaimaiPrintError) -> HTTPException:
    detail = str(exc)
    if exc.code is not None:
        detail = f"{detail}（快麦 code={exc.code}）"
    return HTTPException(status_code=502, detail=detail)
