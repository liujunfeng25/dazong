#!/usr/bin/env python3
"""监管端 AI 问答回归（目标 ≥25 条稳定通过）。"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


BASE_URL = os.environ.get("CHAT_REGRESSION_BASE_URL", "http://127.0.0.1:8000")
USERNAME = os.environ.get("CHAT_REGRESSION_USER", "monitor001")
PASSWORD = os.environ.get("CHAT_REGRESSION_PASS", "demo123")


@dataclass
class Case:
    prompt: str
    session_id: str = "dazong-chat-regression"
    expect_tool: str | None = None
    expect_tool_any: tuple[str, ...] = ()
    expect_intent: str | None = None
    expect_not_intent: str | None = None
    expect_reply_any: tuple[str, ...] = ()
    expect_reply_all: tuple[str, ...] = ()
    expect_preview_all: tuple[str, ...] = ()
    expect_card_type: str | None = None
    expect_chart_type: str | None = None
    expect_no_card: bool = False
    expect_report: bool = False
    expect_report_any: tuple[str, ...] = ()
    expect_tool_args: dict[str, str] = field(default_factory=dict)
    expect_tool_in_chain: tuple[str, ...] = ()
    expect_tools_min: int = 0
    expect_route_any: tuple[str, ...] = ()
    prior_messages: tuple[dict[str, str], ...] = field(default_factory=tuple)


CASES = [
    Case(
        prompt="白菜明天多少钱",
        session_id="qa-price-followup",
        expect_tool="get_national_ag_forecast_price",
        expect_reply_all=("多个可能品名",),
        expect_preview_all=("zgncpjgw", '"status": "ambiguous"'),
        expect_no_card=True,
    ),
    Case(
        prompt="就大白菜",
        session_id="qa-price-followup",
        expect_tool="get_national_ag_forecast_price",
        expect_reply_all=("全国农产品",),
        expect_preview_all=("zgncpjgw", '"status": "ok"'),
        expect_card_type="trend",
    ),
    Case(
        prompt="大白菜以后价格怎么样",
        session_id="qa-price-direct",
        expect_tool="get_national_ag_forecast_price",
        expect_reply_all=("全国农产品",),
        expect_preview_all=("zgncpjgw", '"status": "ok"'),
        expect_card_type="trend",
    ),
    Case(
        prompt="明儿个土豆什么价",
        session_id="qa-potato",
        expect_tool="get_national_ag_forecast_price",
        expect_reply_all=("土豆", "全国"),
        expect_preview_all=("zgncpjgw", '"status": "ok"'),
        expect_card_type="kpi",
    ),
    Case(
        prompt="后天西红柿大概多少钱一斤",
        session_id="qa-tomato",
        expect_tool="get_national_ag_forecast_price",
        expect_reply_any=("番茄", "西红柿", "后日参考价", "全国"),
        expect_preview_all=("zgncpjgw", '"target_offset": 2'),
        expect_card_type="kpi",
    ),
    Case(
        prompt="昨天大白菜（平头型）二级多少钱",
        session_id="qa-cabbage-yesterday",
        expect_tool="get_national_ag_price",
        expect_intent="national_price",
        expect_reply_any=("元/斤", "全国农产品", "均价"),
        expect_preview_all=("product_query", "大白菜"),
        expect_card_type="kpi",
    ),
    Case(
        prompt="大白菜（平头型）二级历史价格",
        session_id="qa-cabbage-history",
        expect_tool="get_national_ag_price",
        expect_intent="national_price",
        expect_reply_any=("全国农产品", "行情", "匹配到", "均价"),
        expect_preview_all=("大白菜", '"ok": true'),
        expect_card_type="national_price",
    ),
    Case(
        prompt="一周前大白菜（平头型）二级什么价",
        session_id="qa-cabbage-week",
        expect_tool="get_national_ag_price",
        expect_intent="national_price",
        expect_reply_any=("元/斤", "全国农产品", "均价"),
        expect_preview_all=("product_query", "大白菜"),
    ),
    Case(
        prompt="现在北京时间是几月几号",
        session_id="qa-date",
        expect_reply_all=("北京时间",),
        expect_no_card=True,
    ),
    Case(
        prompt="演示账号是什么",
        session_id="qa-howto-account",
        expect_tool_any=("search_docs",),
        expect_tool_in_chain=("search_docs",),
        expect_reply_any=("monitor001", "demo123", "演示", "账号"),
    ),
    Case(
        prompt="稽核链路怎么查",
        session_id="qa-howto-audit",
        expect_tool_any=("search_docs",),
        expect_tool_in_chain=("search_docs",),
        expect_reply_any=("稽核", "链路", "查"),
    ),
    Case(
        prompt="AI助手在哪里",
        session_id="qa-howto-ai",
        expect_tool_any=("search_docs",),
        expect_reply_any=("AI", "助手", "浮窗", "右下"),
    ),
    Case(
        prompt="给我生成一个今天卖的一级分类的饼图",
        session_id="qa-pie-today",
        expect_tool_in_chain=("get_category_distribution",),
        expect_card_type="rank",
        expect_chart_type="pie",
    ),
    Case(
        prompt="生成今日监管日报",
        session_id="qa-daily-report",
        expect_tool_in_chain=("generate_report",),
        expect_report=True,
        expect_report_any=("## 核心 KPI", "## 当日告警类型汇总"),
        expect_reply_any=("日报", "监管"),
    ),
    Case(
        prompt="生成昨天的监管日报",
        session_id="qa-daily-report-yesterday",
        expect_tool_in_chain=("generate_report",),
        expect_report=True,
        expect_report_any=("## 核心 KPI", "## 当日告警类型汇总"),
        expect_reply_any=("日报", "监管"),
    ),
    Case(
        prompt="今天开放告警有几条",
        session_id="qa-alerts-open",
        expect_intent="analytics",
        expect_not_intent="how_to",
        expect_tool_any=("search_alerts", "get_kpi_summary"),
        expect_reply_any=("告警", "预警", "开放"),
    ),
    Case(
        prompt="稽核链路怎么查，顺便看今天开放告警几条",
        session_id="qa-mixed-audit-alerts",
        expect_intent="analytics",
        expect_not_intent="how_to",
        expect_tool_any=("search_alerts", "get_kpi_summary"),
        expect_reply_any=("告警", "预警"),
    ),
    Case(
        prompt="中农食迅的日报",
        session_id="qa-subject-report",
        expect_tool_in_chain=("generate_report",),
        expect_report=True,
        expect_reply_any=("日报", "报告", "中农"),
    ),
    Case(
        prompt="中农食迅是谁",
        session_id="qa-lookup-subject",
        expect_tool_in_chain=("lookup_entity_by_name",),
        expect_reply_any=("中农", "配送", "候选", "匹配"),
    ),
    Case(
        prompt="今天GMV多少",
        session_id="qa-gmv-today",
        expect_intent="analytics",
        expect_tool_any=("get_kpi_summary",),
        expect_reply_any=("GMV", "订单", "元"),
    ),
    Case(
        prompt="指挥广播怎么发",
        session_id="qa-howto-broadcast",
        expect_tool_in_chain=("search_docs",),
        expect_reply_any=("广播", "CMD", "指挥"),
    ),
    Case(
        prompt="怎么导出监管日报",
        session_id="qa-howto-export-report",
        expect_tool_in_chain=("search_docs",),
        expect_reply_any=("导出", "Word", "Markdown", "日报"),
    ),
    Case(
        prompt="今日监管日报",
        session_id="qa-daily-report-short",
        expect_tool_in_chain=("generate_report",),
        expect_report=True,
    ),
    Case(
        prompt="今天一级分类饼图",
        session_id="qa-pie-short",
        expect_tool_in_chain=("get_category_distribution",),
        expect_chart_type="pie",
    ),
    Case(
        prompt="能查哪些数据",
        session_id="qa-schema",
        expect_tool_any=("get_schema_overview",),
        expect_reply_any=("表", "数据", "订单", "schema", "范围"),
    ),
    Case(
        prompt="最近30天区域GMV排行",
        session_id="qa-region-rank",
        expect_tool_any=("get_region_rank", "run_sql"),
        expect_card_type="rank",
    ),
    Case(
        prompt="今天有多少订单",
        session_id="qa-orders-today",
        expect_tool_any=("get_today_orders", "get_kpi_summary", "search_orders"),
        expect_reply_any=("订单", "单"),
    ),
    Case(
        prompt="超期未付账单有多少",
        session_id="qa-overdue-bills",
        expect_tool_any=("get_overdue_bills", "search_statements"),
        expect_reply_any=("账单", "超期", "未付"),
    ),
    Case(
        prompt="大白菜明天多少钱",
        session_id="qa-cabbage-direct",
        expect_tool="get_national_ag_forecast_price",
        expect_reply_any=("大白菜", "全国农产品", "多个可能品名"),
    ),
    Case(
        prompt="监管端能改订单吗",
        session_id="qa-scope-readonly",
        expect_reply_any=("只读", "不能", "无法", "查询"),
    ),
    Case(
        prompt="怎么在浮窗里看参考来源",
        session_id="qa-howto-citations",
        expect_tool_in_chain=("search_docs",),
        expect_reply_any=("参考来源", "手册", "AI", "Alt"),
    ),
    # --- LLM-first 口语化 / 多轮 / 混合 ---
    Case(
        prompt="昨天生意咋样",
        session_id="qa-colloquial-kpi",
        expect_tool_any=("get_kpi_summary",),
        expect_reply_any=("订单", "GMV", "元", "单"),
    ),
    Case(
        prompt="最近谁卖最多",
        session_id="qa-colloquial-rank",
        expect_tool_any=("get_region_rank", "get_top_goods", "run_sql"),
        expect_reply_any=("排行", "GMV", "区域", "商品", "订单"),
    ),
    Case(
        prompt="链路在哪查",
        session_id="qa-doc-variant-audit",
        expect_tool_in_chain=("search_docs",),
        expect_reply_any=("稽核", "链路", "查"),
    ),
    Case(
        prompt="给我整一份昨天的监管日报",
        session_id="qa-colloquial-report",
        expect_tool_in_chain=("generate_report",),
        expect_report=True,
        expect_reply_any=("日报", "监管"),
    ),
    Case(
        prompt="演示账号是啥，顺便看今天GMV",
        session_id="qa-mixed-account-gmv",
        expect_tools_min=1,
        expect_reply_any=("GMV", "账号", "demo", "monitor", "订单"),
    ),
    Case(
        prompt="查一下订单",
        session_id="qa-vague-orders",
        expect_tool_any=("search_orders", "get_today_orders", "get_kpi_summary", "ask_clarification"),
        expect_reply_any=("订单", "今天", "时间", "范围", "单"),
    ),
    Case(
        prompt="换成昨天呢",
        session_id="qa-multi-subject-day",
        prior_messages=(
            {"role": "user", "content": "中农食迅的日报"},
            {"role": "assistant", "content": "已为中农食迅生成监管日报，如需其他日期请说明。"},
        ),
        expect_tool_in_chain=("generate_report",),
        expect_reply_any=("日报", "监管", "昨天", "2026", "5月", "28"),
    ),
    Case(
        prompt="今天开放告警",
        session_id="qa-alerts-colloquial",
        expect_tool_any=("search_alerts", "get_kpi_summary"),
        expect_reply_any=("告警", "预警"),
    ),
    Case(
        prompt="本周GMV趋势",
        session_id="qa-week-trend",
        expect_tool_any=("get_daily_trend", "get_kpi_summary"),
        expect_reply_any=("GMV", "趋势", "订单", "元"),
    ),
    Case(
        prompt="超期账单清单",
        session_id="qa-overdue-list",
        expect_tool_any=("get_overdue_bills", "search_statements"),
        expect_reply_any=("账单", "超期", "未付", "未结"),
    ),
    Case(
        prompt="你好",
        session_id="qa-greeting",
        expect_route_any=("greeting", "fallback", "llm_first"),
        expect_reply_any=("你好", "助手", "监管"),
    ),
    Case(
        prompt="帮我取消这个订单",
        session_id="qa-refuse-write",
        expect_route_any=("safety", "fallback", "llm_first"),
        expect_reply_any=("只读", "无法", "不能", "业务端"),
    ),
    Case(
        prompt="一级分类占比怎么样",
        session_id="qa-category-share",
        expect_tool_any=("get_category_distribution",),
        expect_reply_any=("品类", "分类", "占比", "金额", "订单"),
    ),
    Case(
        prompt="今天下了多少单",
        session_id="qa-orders-colloquial",
        expect_tool_any=("get_kpi_summary", "get_today_orders", "search_orders"),
        expect_reply_any=("订单", "单"),
    ),
    Case(
        prompt="财务报表",
        session_id="qa-financial-report",
        expect_tool_in_chain=("generate_report",),
        expect_reply_any=("财务", "应付", "应收", "报表", "账单"),
    ),
    Case(
        prompt="设备离线情况",
        session_id="qa-device-offline",
        expect_tool_any=("get_device_status", "search_alerts"),
        expect_reply_any=("设备", "离线", "在线", "告警", "无记录"),
    ),
    Case(
        prompt="工单待处理有几条",
        session_id="qa-tickets-pending",
        expect_tool_any=("search_tickets", "run_sql"),
        expect_reply_any=("工单", "待处理", "条"),
    ),
    Case(
        prompt="新发地今天大白菜价格",
        session_id="qa-xinfadi-history",
        expect_tool_any=("get_national_ag_price", "get_national_ag_forecast_price", "get_xinfadi_price", "get_xinfadi_forecast_price"),
        expect_reply_any=("大白菜", "价格", "元", "行情", "全国", "暂无"),
    ),
    Case(
        prompt="能帮我看看中农那边最近咋样",
        session_id="qa-subject-colloquial",
        expect_tools_min=1,
        expect_reply_any=("中农", "履约", "订单", "GMV", "配送"),
    ),
    Case(
        prompt="监管端演示密码",
        session_id="qa-demo-password",
        expect_tool_in_chain=("search_docs",),
        expect_reply_any=("demo123", "密码", "演示", "账号"),
    ),
    Case(
        prompt="最近7天订单趋势",
        session_id="qa-order-trend-week",
        expect_tool_any=("get_daily_trend", "get_kpi_summary"),
        expect_reply_any=("订单", "GMV", "趋势", "天"),
    ),
    Case(
        prompt="哪个区域卖得好",
        session_id="qa-region-colloquial",
        expect_tool_any=("get_region_rank", "run_sql"),
        expect_reply_any=("区域", "GMV", "排行", "订单"),
    ),
]


def _post_json(url: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _login() -> str:
    data = _post_json(f"{BASE_URL}/api/auth/login", {"username": USERNAME, "password": PASSWORD})
    return str(data["token"])


def _first_tool(resp: dict[str, Any]) -> dict[str, Any]:
    calls = ((resp.get("debug") or {}).get("tool_calls") or [])
    return calls[0] if calls and isinstance(calls[0], dict) else {}


def _all_tools(resp: dict[str, Any]) -> list[str]:
    calls = ((resp.get("debug") or {}).get("tool_calls") or [])
    return [str(t.get("name") or "") for t in calls if isinstance(t, dict) and t.get("name")]


def _check(case: Case, resp: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    reply = str(resp.get("reply") or resp.get("answer") or "")
    tool = _first_tool(resp)
    tool_name = str(tool.get("name") or "")
    all_tools = _all_tools(resp)
    preview = str(tool.get("result_preview") or "")
    card = resp.get("data_card")
    card_type = str(card.get("type") or "") if isinstance(card, dict) else ""
    chart_type = str(card.get("chart_type") or "") if isinstance(card, dict) else ""
    intent = str((resp.get("debug") or {}).get("intent") or "")
    route = str((resp.get("debug") or {}).get("route") or "")
    if case.expect_route_any and route not in case.expect_route_any:
        errors.append(f"路由不符：期望 {case.expect_route_any}，实际 {route or '无'}")
    if case.expect_tools_min and len(all_tools) < case.expect_tools_min:
        errors.append(f"工具链过短：期望 ≥{case.expect_tools_min}，实际 {len(all_tools)}")
    if case.expect_tool_in_chain and not any(t in all_tools for t in case.expect_tool_in_chain):
        errors.append(f"工具链未命中任一 {case.expect_tool_in_chain}，实际 {all_tools or '无'}")
    card = resp.get("data_card")
    card_type = str(card.get("type") or "") if isinstance(card, dict) else ""
    chart_type = str(card.get("chart_type") or "") if isinstance(card, dict) else ""
    intent = str((resp.get("debug") or {}).get("intent") or "")
    if case.expect_intent and intent != case.expect_intent:
        errors.append(f"意图不符：期望 {case.expect_intent}，实际 {intent or '无'}")
    if case.expect_not_intent and intent == case.expect_not_intent:
        errors.append(f"意图不应为 {case.expect_not_intent}，实际为 {intent}")
    if case.expect_tool and tool_name != case.expect_tool:
        errors.append(f"工具不符：期望 {case.expect_tool}，实际 {tool_name or '无'}")
    if case.expect_tool_any and tool_name not in case.expect_tool_any:
        errors.append(f"工具未命中任一 {case.expect_tool_any}，实际 {tool_name or '无'}")
    for frag in case.expect_reply_all:
        if frag not in reply:
            errors.append(f"回复缺少：{frag}")
    if case.expect_reply_any and not any(frag in reply for frag in case.expect_reply_any):
        errors.append(f"回复未命中任一：{case.expect_reply_any}")
    for frag in case.expect_preview_all:
        if frag not in preview and frag not in json.dumps(tool, ensure_ascii=False):
            errors.append(f"工具预览缺少：{frag}")
    if case.expect_card_type and card_type != case.expect_card_type:
        errors.append(f"卡片类型不符：期望 {case.expect_card_type}，实际 {card_type or '无'}")
    if case.expect_chart_type and chart_type != case.expect_chart_type:
        errors.append(f"图表类型不符：期望 chart_type={case.expect_chart_type}，实际 {chart_type or '无'}")
    if case.expect_report and not (resp.get("report_content") or ""):
        errors.append("期望有 report_content，但实际为空")
    report_content = str(resp.get("report_content") or "")
    if case.expect_report_any and not all(frag in report_content for frag in case.expect_report_any):
        errors.append(f"报表正文未命中任一：{case.expect_report_any}")
    tool_args = tool.get("arguments") or {}
    for key, expected in case.expect_tool_args.items():
        actual = str(tool_args.get(key) or "")
        if actual != expected:
            errors.append(f"工具参数 {key} 不符：期望 {expected}，实际 {actual or '无'}")
    if case.expect_no_card and card:
        errors.append("期望无 data_card，但实际返回了卡片")
    return errors


def main() -> int:
    token = _login()
    failed = 0
    for idx, case in enumerate(CASES, start=1):
        messages = [{"role": m["role"], "content": m["content"]} for m in case.prior_messages]
        messages.append({"role": "user", "content": case.prompt})
        resp = _post_json(
            f"{BASE_URL}/api/chat",
            {"session_id": case.session_id, "messages": messages},
            token,
        )
        errors = _check(case, resp)
        if errors:
            failed += 1
            print(f"[FAIL] {idx}. {case.prompt}")
            for err in errors:
                print(f"  - {err}")
            print(f"  reply={str(resp.get('reply') or '')[:260]}")
            print(f"  debug={json.dumps(resp.get('debug') or {}, ensure_ascii=False)[:500]}")
        else:
            tool = _first_tool(resp).get("name") or "无"
            print(f"[PASS] {idx}. {case.prompt} tool={tool}")
    if failed:
        print(f"\n{failed}/{len(CASES)} failed")
        return 1
    print(f"\n{len(CASES)}/{len(CASES)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
