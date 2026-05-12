from __future__ import annotations

import io
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from dependencies import require_role
from models import Alert, ClientCanteen, Order, Product, User


router = APIRouter(prefix="/chat", tags=["ai_chat"])


class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: Optional[str] = None
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False


class ExportRequest(BaseModel):
    title: str = "监管分析报告"
    content: str = ""
    markdown: str = ""
    filename: Optional[str] = None
    format: str = "docx"


def _monitor_guard(_=Depends(require_role("monitor"))) -> None:
    return None


def _num(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _today() -> date:
    return datetime.utcnow().date()


def _latest_user_text(body: ChatRequest) -> str:
    if body.message:
        return body.message.strip()
    for msg in reversed(body.messages):
        if msg.role == "user" and msg.content.strip():
            return msg.content.strip()
    return ""


def _line_rows(order: Order) -> list[dict[str, Any]]:
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    rows = []
    for idx in range(max(len(items), len(snaps))):
        item = items[idx] if idx < len(items) and isinstance(items[idx], dict) else {}
        snap = snaps[idx] if idx < len(snaps) and isinstance(snaps[idx], dict) else {}
        qty = _num(snap.get("order_quantity", item.get("quantity", item.get("qty", 0))))
        price = _num(snap.get("order_unit_price", item.get("unit_price", item.get("price", 0))))
        rows.append(
            {
                "product_id": item.get("product_id") or snap.get("product_id"),
                "goods_name": str(snap.get("product_name") or item.get("product_name") or item.get("goods_name") or f"商品#{idx + 1}"),
                "category_name": str(snap.get("category1_name") or "未归类"),
                "qty": qty,
                "amount": round(qty * price, 2),
            }
        )
    return rows


def _district_from_address(address: Optional[str]) -> str:
    text_value = address or ""
    for name in ("东城区", "西城区", "朝阳区", "丰台区", "石景山区", "海淀区", "门头沟区", "房山区", "通州区", "顺义区", "昌平区", "大兴区", "怀柔区", "平谷区", "密云区", "延庆区"):
        if name in text_value:
            return name
    return "未标注区域"


def _mask_name(value: Any) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    return text_value[0] + "**"


def _mask_phone(value: Any) -> str:
    return re.sub(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)", r"\1****\3", str(value or ""))


def _repair_text(value: Any) -> str:
    text_value = str(value or "")
    if not text_value:
        return ""
    if not re.search(r"[åèéçæä]", text_value):
        return text_value
    try:
        return text_value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text_value


def _extract_xinfadi_keyword(text_value: str) -> str:
    text_value = (text_value or "").strip()
    known = [
        "大白菜",
        "小白菜",
        "圆白菜",
        "奶白菜",
        "白菜",
        "山药",
        "黄瓜",
        "番茄",
        "西红柿",
        "土豆",
        "马铃薯",
        "芋头",
        "冬瓜",
        "菠菜",
        "油麦菜",
        "油菜",
        "苦菊",
        "胡萝卜",
        "红薯",
        "玉米",
        "苹果",
        "香蕉",
        "西瓜",
        "火龙果",
    ]
    for name in known:
        if name in text_value:
            return "番茄" if name == "西红柿" else "土豆" if name == "马铃薯" else name
    cleaned = re.sub(
        r"(新发地|行情|价格|报价|未来|预测|趋势|今天|明天|后天|多少|怎么样|如何|查询|查一下|给我|帮我|的|近|最近|天|日|周|月|\d+)",
        "",
        text_value,
    )
    match = re.search(r"[\u4e00-\u9fff]{2,8}", cleaned)
    return match.group(0) if match else text_value


def _range_from_args(args: dict[str, Any]) -> tuple[date, date]:
    today = _today()
    scope = args.get("scope")
    if scope == "today":
        return today, today
    try:
        start = date.fromisoformat(str(args.get("start_date") or ""))
    except ValueError:
        start = today - timedelta(days=29)
    try:
        end = date.fromisoformat(str(args.get("end_date") or ""))
    except ValueError:
        end = today
    if end < start:
        start, end = end, start
    return start, end


async def _orders_in_range(db: AsyncSession, start: date, end: date) -> list[Order]:
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
    return (
        await db.scalars(
            select(Order).where(Order.created_at >= start_dt, Order.created_at < end_dt).order_by(Order.id.desc()).limit(5000)
        )
    ).all()


async def _names(db: AsyncSession, orders: list[Order]) -> dict[int, str]:
    user_ids = {int(o.client_id) for o in orders if o.client_id}
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    canteens = (await db.scalars(select(ClientCanteen))).all()
    out = {int(u.id): u.company_name or u.username for u in users}
    out.update({int(c.id): c.name for c in canteens})
    return out


async def _tool_kpi_summary(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    start, end = _range_from_args(args)
    orders = await _orders_in_range(db, start, end)
    alerts = (await db.scalars(select(Alert).where(Alert.status == "open").limit(500))).all()
    gmv = sum(_num(o.total_amount) for o in orders)
    fulfilled = len([o for o in orders if o.status in {"收货确认", "已结算"}])
    rows = [
        {"metric": "订单数", "value": len(orders), "unit": "单"},
        {"metric": "GMV", "value": round(gmv, 2), "unit": "元"},
        {"metric": "开放预警", "value": len(alerts), "unit": "条"},
        {"metric": "履约完成率", "value": round(fulfilled / len(orders) * 100, 2) if orders else 0, "unit": "%"},
    ]
    return {
        "type": "kpi",
        "title": f"{start.isoformat()} 至 {end.isoformat()} 核心 KPI",
        "columns": [{"key": "metric", "label": "指标"}, {"key": "value", "label": "数值"}, {"key": "unit", "label": "单位"}],
        "rows": rows,
        "summary": f"区间订单 {len(orders)} 单，GMV ¥{gmv:.2f}，开放预警 {len(alerts)} 条。",
    }


async def _tool_rank(db: AsyncSession, args: dict[str, Any], mode: str) -> dict[str, Any]:
    start, end = _range_from_args(args)
    limit = int(args.get("limit") or 10)
    orders = await _orders_in_range(db, start, end)
    names = await _names(db, orders)
    bucket: dict[str, dict[str, Any]] = {}
    for order in orders:
        if mode == "region":
            key = _district_from_address(order.delivery_address)
            row = bucket.setdefault(key, {"name": key, "order_count": 0, "gmv": 0.0})
            row["order_count"] += 1
            row["gmv"] += _num(order.total_amount)
        elif mode == "customer":
            key = names.get(int(order.canteen_id or order.client_id or 0), f"客户#{order.client_id}")
            row = bucket.setdefault(key, {"name": _mask_name(key), "order_count": 0, "gmv": 0.0})
            row["order_count"] += 1
            row["gmv"] += _num(order.total_amount)
        else:
            seen = set()
            for line in _line_rows(order):
                key = line["goods_name"] if mode == "goods" else line["category_name"]
                row = bucket.setdefault(key, {"name": key, "order_count": 0, "amount": 0.0, "qty": 0.0})
                row["amount"] += _num(line["amount"])
                row["qty"] += _num(line["qty"])
                seen.add(key)
            for key in seen:
                bucket[key]["order_count"] += 1
    metric = "gmv" if mode in {"region", "customer"} else "amount"
    rows = sorted(bucket.values(), key=lambda row: row.get(metric, 0), reverse=True)[:limit]
    for row in rows:
        for key in ("gmv", "amount", "qty"):
            if key in row:
                row[key] = round(_num(row[key]), 2)
    titles = {"region": "区域 GMV 排行", "customer": "客户 GMV 排行", "goods": "商品排行", "category": "品类排行"}
    return {
        "type": "rank",
        "title": titles.get(mode, "排行"),
        "columns": [{"key": k, "label": v} for k, v in ({"name": "名称", "order_count": "订单", metric: "金额"}).items()],
        "rows": rows,
        "summary": f"已生成{titles.get(mode, '排行')}，共 {len(rows)} 条。",
        "_pii_masked": mode == "customer",
    }


async def _tool_daily_trend(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    start, end = _range_from_args(args)
    orders = await _orders_in_range(db, start, end)
    bucket: dict[str, dict[str, Any]] = {}
    day = start
    while day <= end:
        bucket[day.isoformat()] = {"date": day.isoformat(), "orders": 0, "gmv": 0.0}
        day += timedelta(days=1)
    for order in orders:
        key = order.created_at.date().isoformat()
        if key in bucket:
            bucket[key]["orders"] += 1
            bucket[key]["gmv"] += _num(order.total_amount)
    rows = list(bucket.values())
    for row in rows:
        row["gmv"] = round(row["gmv"], 2)
    return {
        "type": "chart",
        "chart_type": "line",
        "title": "GMV 趋势",
        "columns": [{"key": "date", "label": "日期"}, {"key": "orders", "label": "订单"}, {"key": "gmv", "label": "GMV"}],
        "rows": rows,
        "summary": f"已生成 {start.isoformat()} 至 {end.isoformat()} 的趋势序列。",
    }


async def _tool_ops_alerts(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 20)
    alerts = (await db.scalars(select(Alert).order_by(Alert.id.desc()).limit(limit))).all()
    rows = [
        {
            "level": a.level,
            "type": a.type,
            "description": a.description,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else "",
        }
        for a in alerts
    ]
    return {
        "type": "alerts",
        "title": "运营预警",
        "columns": [{"key": "level", "label": "等级"}, {"key": "type", "label": "类型"}, {"key": "description", "label": "描述"}],
        "rows": rows,
        "summary": f"最近预警 {len(rows)} 条，其中开放预警 {len([r for r in rows if r['status'] == 'open'])} 条。",
    }


async def _tool_today_orders(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    start, end = _today(), _today()
    orders = await _orders_in_range(db, start, end)
    rows = [
        {
            "order_no": o.order_no,
            "status": o.status,
            "amount": round(_num(o.total_amount), 2),
            "created_at": o.created_at.isoformat() if o.created_at else "",
        }
        for o in orders[:30]
    ]
    return {
        "type": "orders",
        "title": "今日订单",
        "columns": [{"key": "order_no", "label": "订单号"}, {"key": "status", "label": "状态"}, {"key": "amount", "label": "金额"}],
        "rows": rows,
        "summary": f"今日共有 {len(orders)} 单。",
    }


async def _xinfadi_rows(db: AsyncSession, product_name: str = "", limit: int = 500) -> list[dict[str, Any]]:
    product_name = _extract_xinfadi_keyword(product_name)
    clause = "WHERE product_name LIKE :p" if product_name else ""
    params = {"limit": limit}
    if product_name:
        params["p"] = f"%{product_name}%"
    result = await db.execute(
        text(
            f"""
            SELECT crawl_date, product_name, category1, min_price, avg_price, max_price, unit, origin
            FROM `{settings.xinfadi_price_table}`
            {clause}
            ORDER BY crawl_date DESC
            LIMIT :limit
            """
        ),
        params,
    )
    return [
        {
            "date": row.crawl_date.isoformat() if row.crawl_date else "",
            "product_name": _repair_text(row.product_name),
            "category": _repair_text(row.category1),
            "min_price": _num(row.min_price),
            "avg_price": _num(row.avg_price),
            "max_price": _num(row.max_price),
            "unit": _repair_text(row.unit),
            "origin": _repair_text(row.origin),
        }
        for row in result.fetchall()
    ]


def _forecast(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    values = [_num(row["avg_price"]) for row in rows if _num(row.get("avg_price")) > 0]
    baseline = sum(values[:14]) / len(values[:14]) if values[:14] else 1
    vol = 0.04
    if len(values) > 2 and baseline:
        vol = min(0.22, max(0.015, (max(values[:30]) - min(values[:30])) / baseline))
    last = _today()
    if rows and rows[0].get("date"):
        try:
            last = date.fromisoformat(rows[0]["date"])
        except ValueError:
            pass
    out = []
    for i in range(1, days + 1):
        drift = ((i % 7) - 3) * vol * 0.15
        yhat = baseline * (1 + drift)
        out.append({"date": (last + timedelta(days=i)).isoformat(), "price": round(yhat, 2), "lower": round(yhat * (1 - vol), 2), "upper": round(yhat * (1 + vol), 2)})
    return out


async def _tool_xinfadi_price(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    product = _extract_xinfadi_keyword(str(args.get("product_name") or args.get("query_text") or "").strip())
    rows = await _xinfadi_rows(db, product, limit=60)
    return {
        "type": "xinfadi_price",
        "title": f"{product or '新发地'} 行情",
        "columns": [{"key": "date", "label": "日期"}, {"key": "product_name", "label": "品名"}, {"key": "avg_price", "label": "均价"}],
        "rows": rows[:20],
        "summary": f"匹配到 {len(rows)} 条新发地行情。",
    }


async def _tool_xinfadi_forecast(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    query = _extract_xinfadi_keyword(str(args.get("query_text") or args.get("product_name") or "").strip())
    days = int(args.get("days") or 7)
    rows = await _xinfadi_rows(db, query, limit=500)
    if not rows:
        return {"type": "forecast", "title": "新发地价格预测", "rows": [], "summary": f"未找到“{query}”的新发地行情。"}
    product = rows[0]["product_name"]
    exact_rows = await _xinfadi_rows(db, product, limit=500)
    forecast = _forecast(exact_rows, days)
    return {
        "type": "forecast",
        "title": f"{product} 未来 {days} 天预测",
        "columns": [{"key": "date", "label": "日期"}, {"key": "price", "label": "预测价"}, {"key": "lower", "label": "下界"}, {"key": "upper", "label": "上界"}],
        "rows": forecast,
        "summary": f"{product} 的预测已生成，基于 {len(exact_rows)} 条新发地历史行情。",
        "fallback": len(exact_rows) < 120,
    }


async def _tool_schema_overview(db: AsyncSession, _args: dict[str, Any]) -> dict[str, Any]:
    result = await db.execute(text("SHOW TABLES"))
    tables = [list(row._mapping.values())[0] for row in result.fetchall()]
    return {
        "type": "plain",
        "title": "可查询数据范围",
        "rows": [{"table": t} for t in tables if any(k in t for k in ("order", "alert", "xinfadi", "product", "delivery", "bill"))][:50],
        "summary": "可查询订单、履约、预警、账务、商品、客户、新发地行情和价格预测相关数据。",
    }


async def _tool_generate_report(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    kpi = await _tool_kpi_summary(db, {"scope": "today"})
    alerts = await _tool_ops_alerts(db, {"limit": 8})
    report = (
        "# 监管日报\n\n"
        f"## 核心态势\n\n{kpi['summary']}\n\n"
        "## 风险预警\n\n"
        f"{alerts['summary']}\n\n"
        "## 建议\n\n"
        "- 优先处理开放预警和履约异常。\n"
        "- 对新发地行情波动较大的商品进行采购价复核。\n"
        "- 对未闭环工单跟踪责任方和处理时限。\n"
    )
    return {"type": "report", "title": "监管日报", "rows": [], "summary": "已生成监管日报草稿。", "report_content": report}


TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "get_kpi_summary", "description": "查询核心 KPI：订单数、GMV、开放预警、履约完成率。", "parameters": {"type": "object", "properties": {"scope": {"type": "string", "enum": ["today", "range"]}, "start_date": {"type": "string"}, "end_date": {"type": "string"}}, "required": ["scope"]}}},
    {"type": "function", "function": {"name": "get_region_rank", "description": "查询区域 GMV 排行。", "parameters": {"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_category_distribution", "description": "查询品类销售排行。", "parameters": {"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_top_goods", "description": "查询商品销售排行。", "parameters": {"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_daily_trend", "description": "查询每日 GMV 和订单趋势。", "parameters": {"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_ops_alerts", "description": "查询运营预警和异常。", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_today_orders", "description": "查询今日订单。", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_xinfadi_price", "description": "查询新发地历史行情。", "parameters": {"type": "object", "properties": {"product_name": {"type": "string"}, "query_text": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_xinfadi_forecast_price", "description": "查询新发地未来价格预测。", "parameters": {"type": "object", "properties": {"query_text": {"type": "string"}, "product_name": {"type": "string"}, "days": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "generate_report", "description": "生成监管日报、周报、月报或经营分析报告。", "parameters": {"type": "object", "properties": {"report_type": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_schema_overview", "description": "说明可查询的数据范围。", "parameters": {"type": "object", "properties": {}}}},
]


async def _dispatch_tool(name: str, args: dict[str, Any], db: AsyncSession) -> dict[str, Any]:
    if name == "get_kpi_summary":
        return await _tool_kpi_summary(db, args)
    if name == "get_region_rank":
        return await _tool_rank(db, args, "region")
    if name == "get_category_distribution":
        return await _tool_rank(db, args, "category")
    if name == "get_top_goods":
        return await _tool_rank(db, args, "goods")
    if name == "get_top_members":
        return await _tool_rank(db, args, "customer")
    if name == "get_daily_trend":
        return await _tool_daily_trend(db, args)
    if name == "get_ops_alerts":
        return await _tool_ops_alerts(db, args)
    if name == "get_today_orders":
        return await _tool_today_orders(db, args)
    if name == "get_xinfadi_price":
        return await _tool_xinfadi_price(db, args)
    if name == "get_xinfadi_forecast_price":
        return await _tool_xinfadi_forecast(db, args)
    if name == "generate_report":
        return await _tool_generate_report(db, args)
    if name == "get_schema_overview":
        return await _tool_schema_overview(db, args)
    return {"type": "error", "summary": f"未知工具：{name}", "rows": []}


def _heuristic_tool(text_value: str) -> tuple[str, dict[str, Any]]:
    if any(k in text_value for k in ("能查", "哪些数据", "表结构", "数据范围")):
        return "get_schema_overview", {}
    if any(k in text_value for k in ("日报", "周报", "月报", "报告", "简报", "导出")):
        return "generate_report", {"report_type": "daily"}
    if any(k in text_value for k in ("未来", "预测", "明天", "后天")) and any(k in text_value for k in ("价", "行情", "新发地")):
        return "get_xinfadi_forecast_price", {"query_text": text_value, "days": 7}
    if any(k in text_value for k in ("新发地", "行情", "价格", "多少钱")):
        return "get_xinfadi_price", {"query_text": text_value}
    if any(k in text_value for k in ("趋势", "折线", "走势")):
        return "get_daily_trend", {"start_date": (_today() - timedelta(days=6)).isoformat(), "end_date": _today().isoformat()}
    if any(k in text_value for k in ("异常", "预警", "告警")):
        return "get_ops_alerts", {"limit": 20}
    if "今天" in text_value and any(k in text_value for k in ("单", "订单")):
        return "get_today_orders", {}
    if any(k in text_value for k in ("区域", "哪个区")):
        return "get_region_rank", {"start_date": (_today() - timedelta(days=29)).isoformat(), "end_date": _today().isoformat(), "limit": 10}
    if "商品" in text_value:
        return "get_top_goods", {"start_date": (_today() - timedelta(days=29)).isoformat(), "end_date": _today().isoformat(), "limit": 10}
    if "品类" in text_value:
        return "get_category_distribution", {"start_date": (_today() - timedelta(days=29)).isoformat(), "end_date": _today().isoformat(), "limit": 10}
    return "get_kpi_summary", {"scope": "today"}


def _system_prompt() -> str:
    return (
        "你是大宗供应链监管端 AI 分析助手。必须基于工具返回数据回答，不编造数字。"
        "涉及客户、手机号、地址时只使用工具已脱敏结果。"
        "回答要简洁，给出监管判断和下一步建议。"
    )


async def _dashscope_chat(messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    api_key = (settings.ai_api_key or "").strip()
    if not api_key:
        raise RuntimeError("AI_API_KEY 未配置")
    payload: dict[str, Any] = {
        "model": settings.ai_model_answer or "qwen-plus",
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{(settings.ai_base_url or '').rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0), trust_env=False) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def _first_choice(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") or []
    return choices[0].get("message") if choices else {}


def _artifact_from_tool(tool_result: dict[str, Any]) -> tuple[Optional[dict[str, Any]], str]:
    report = str(tool_result.get("report_content") or "")
    if tool_result.get("type") == "report":
        return None, report
    return {
        "type": tool_result.get("type") or "table",
        "title": tool_result.get("title") or "数据卡片",
        "columns": tool_result.get("columns") or [],
        "rows": tool_result.get("rows") or [],
    }, report


async def _local_answer(text_value: str, db: AsyncSession) -> dict[str, Any]:
    tool, args = _heuristic_tool(text_value)
    result = await _dispatch_tool(tool, args, db)
    data_card, report = _artifact_from_tool(result)
    return {
        "reply": result.get("summary") or "已完成分析。",
        "data_card": data_card,
        "report_content": report,
        "session_id": f"chat-{datetime.utcnow().strftime('%Y%m%d')}",
        "debug": {"provider": "local_rule_fallback", "tool_calls": [{"name": tool, "arguments": args}]},
    }


async def _dispatch(text_value: str, history: list[ChatMessage], db: AsyncSession) -> dict[str, Any]:
    base_messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt()}]
    for msg in history[-8:]:
        if msg.role in {"user", "assistant"} and msg.content:
            base_messages.append({"role": msg.role, "content": msg.content})
    if not any(m.get("role") == "user" and m.get("content") == text_value for m in base_messages):
        base_messages.append({"role": "user", "content": text_value})

    tool_calls_debug: list[dict[str, Any]] = []
    provider = "dashscope" if (settings.ai_api_key or "").strip() else "local_rule_fallback"
    try:
        first = await _dashscope_chat(base_messages, TOOLS)
        message = _first_choice(first)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            name, args = _heuristic_tool(text_value)
            tool_calls = [{"id": "local-tool-1", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]
            message = {"role": "assistant", "content": "", "tool_calls": tool_calls}
        answer_messages = [*base_messages, message if message else {"role": "assistant", "content": ""}]
        final_tool_result: dict[str, Any] = {}
        for call in tool_calls[:5]:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            try:
                raw_args = fn.get("arguments") or "{}"
                args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            final_tool_result = await _dispatch_tool(name, args, db)
            tool_calls_debug.append({"name": name, "arguments": args})
            answer_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"tool-{len(tool_calls_debug)}",
                    "content": json.dumps(final_tool_result, ensure_ascii=False),
                }
            )
        final = await _dashscope_chat(
            [
                *answer_messages,
                {
                    "role": "system",
                    "content": "请用中文总结工具结果。不要输出原始 JSON。若有 report_content，仅说明已生成报告。",
                },
            ],
            None,
        )
        reply = _first_choice(final).get("content") or final_tool_result.get("summary") or "已完成分析。"
        data_card, report = _artifact_from_tool(final_tool_result)
        return {
            "reply": reply,
            "data_card": data_card,
            "report_content": report,
            "session_id": f"chat-{datetime.utcnow().strftime('%Y%m%d')}",
            "debug": {"provider": provider, "tool_calls": tool_calls_debug, "model": settings.ai_model_answer},
        }
    except Exception as exc:  # noqa: BLE001
        result = await _local_answer(text_value, db)
        message = str(exc) or repr(exc) or exc.__class__.__name__
        result["debug"]["provider_error"] = message[:220]
        return result


@router.post("")
async def chat(
    body: ChatRequest,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    text_value = _latest_user_text(body)
    return await _dispatch(text_value, body.messages, db)


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    _=Depends(_monitor_guard),
    db: AsyncSession = Depends(get_db),
):
    text_value = _latest_user_text(body)
    result = await _dispatch(text_value, body.messages, db)

    async def events():
        yield f"event: phase\ndata: {json.dumps({'phase': 'planning', 'message': '解析监管问题'}, ensure_ascii=False)}\n\n"
        yield f"event: tool\ndata: {json.dumps(result.get('debug', {}), ensure_ascii=False)}\n\n"
        for chunk in re.split(r"([。；\n])", result.get("reply") or ""):
            if chunk:
                yield f"event: delta\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/catalog")
async def catalog(_=Depends(_monitor_guard), db: AsyncSession = Depends(get_db)):
    schema = await _tool_schema_overview(db, {})
    sample = await _tool_kpi_summary(db, {"scope": "today"})
    return {
        "updated_at": datetime.utcnow().isoformat(),
        "provider_configured": bool((settings.ai_api_key or "").strip()),
        "tables": schema.get("rows", []),
        "api_samples": {"kpi": sample},
    }


@router.post("/catalog/refresh")
async def catalog_refresh(_=Depends(_monitor_guard), db: AsyncSession = Depends(get_db)):
    return await catalog(_=None, db=db)


@router.post("/report/export")
async def export_report(
    body: ExportRequest,
    _=Depends(_monitor_guard),
):
    title = body.title.strip() or "监管分析报告"
    content = (body.markdown or body.content or "").strip() or "# 监管分析报告\n\n暂无报告内容。"
    fmt = (body.format or "docx").lower()
    if fmt == "docx":
        try:
            from docx import Document

            doc = Document()
            doc.add_heading(title, 0)
            for line in content.splitlines():
                clean = line.strip()
                if not clean:
                    continue
                if clean.startswith("# "):
                    doc.add_heading(clean[2:].strip(), level=1)
                elif clean.startswith("## "):
                    doc.add_heading(clean[3:].strip(), level=2)
                elif clean.startswith("- "):
                    doc.add_paragraph(clean[2:].strip(), style="List Bullet")
                else:
                    doc.add_paragraph(clean)
            buf = io.BytesIO()
            doc.save(buf)
            filename = body.filename or title
            return Response(
                content=buf.getvalue(),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'},
            )
        except Exception:
            fmt = "md"
    if fmt == "pptx":
        try:
            from pptx import Presentation

            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            slide.shapes.title.text = title
            slide.placeholders[1].text = "\n".join([ln.strip("# ").strip() for ln in content.splitlines() if ln.strip()][:8])
            buf = io.BytesIO()
            prs.save(buf)
            filename = body.filename or title
            return Response(
                content=buf.getvalue(),
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                headers={"Content-Disposition": f'attachment; filename="{filename}.pptx"'},
            )
        except Exception:
            fmt = "md"
    payload = f"{title}\n\n{content}".encode("utf-8")
    filename = body.filename or title
    return Response(
        content=payload,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.md"'},
    )
