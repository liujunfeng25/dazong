"""监管端 AI 意图分类（规则优先，无额外模型依赖）。"""

from __future__ import annotations

import re

HOW_TO_HINTS = (
    "怎么",
    "如何",
    "在哪",
    "哪里",
    "入口",
    "路径",
    "操作",
    "步骤",
    "手册",
    "教程",
    "演示账号",
    "账号是什么",
    "密码",
    "登录",
    "打不开",
    "找不到",
    "功能在哪",
    "什么意思",
    "是什么功能",
    "怎么用",
    "如何使用",
    "稽核链路怎么",
    "广播怎么发",
    "导出",
    "浮窗",
    "AI助手",
    "AI 助手",
)

ANALYTICS_HINTS = (
    "生意",
    "咋样",
    "概况",
    "卖得",
    "几个",
    "排行",
    "排名",
    "GMV",
    "订单数",
    "占比",
    "饼图",
    "柱状",
    "折线",
    "统计",
    "汇总",
    "列表",
    "查询",
    "超期",
    "告警数",
    "今天卖",
    "本月",
    "本周",
)

REPORT_HINTS = ("日报", "周报", "月报", "简报", "报表", "generate_report")

NATIONAL_PRICE_HINTS = (
    "全国农产品",
    "中农价格网",
    "中农价格",
    "农产品价格",
    "菜价",
    "批发价",
    "新发地",
    "多少钱",
    "明天多少",
    "后天多少",
    "未来价格",
    "预测价",
    "行情",
)

# 保留别名
XINFADI_HINTS = NATIONAL_PRICE_HINTS

_NUMERIC_FORCE = re.compile(
    r"(多少|几个|几单|几条|几张|gmv|金额|排行|占比|统计|汇总|今天.*卖|订单数|超期.*张|告警.*条|生意|咋样|概况)",
    re.I,
)

_SIDE_MARKERS = ("顺便", "同时", "还有", "并且", "另外", "再看", "顺带", "以及")


def has_analytics_side_request(text: str) -> bool:
    """混合问法：含操作说明但同时要查数/告警/排行 → 不走纯 RAG。"""
    t = (text or "").strip()
    if not t:
        return False
    if _NUMERIC_FORCE.search(t):
        return True
    if any(m in t for m in _SIDE_MARKERS) and any(
        h in t for h in (*ANALYTICS_HINTS, "告警", "几条", "几张", "开放", "GMV", "订单", "单数")
    ):
        return True
    if any(k in t for k in ("饼图", "排行", "占比", "柱状", "折线")) and any(k in t for k in HOW_TO_HINTS):
        return True
    return False


def _is_business_metric_question(text: str) -> bool:
    t = text or ""
    return any(k in t for k in ("GMV", "订单", "账单", "稽核", "告警", "履约", "生意", "工单"))


def classify_intent(text: str) -> str:
    """返回: how_to | report | national_price | analytics | out_of_scope | general"""
    t = (text or "").strip()
    if not t:
        return "general"
    if any(k in t for k in ("天气", "股票", "比特币", "写诗", "讲笑话")):
        return "out_of_scope"
    if any(k in t for k in ("换成", "改", "再来")) and any(k in t for k in ("昨天", "今天", "昨日", "今日", "呢")):
        return "report"
    if any(k in t for k in NATIONAL_PRICE_HINTS) and any(
        k in t for k in ("明天", "后天", "未来", "预测", "多少钱", "价格", "价钱", "什么价")
    ):
        if not _is_business_metric_question(t):
            return "national_price"
    if any(k in t for k in REPORT_HINTS) and not any(k in t for k in ("怎么", "如何", "在哪")):
        return "report"
    if _NUMERIC_FORCE.search(t) and not (
        any(k in t for k in ("明天", "后天", "菜价", "批发")) and "GMV" not in t and "订单" not in t
    ):
        return "analytics"
    if has_analytics_side_request(t):
        return "analytics"
    if any(k in t for k in HOW_TO_HINTS):
        if not any(k in t for k in ANALYTICS_HINTS):
            return "how_to"
        if any(k in t for k in ("怎么查", "怎么生成", "怎么发", "怎么用", "如何查", "在哪")):
            if not _NUMERIC_FORCE.search(t) and not any(k in t for k in ("饼图", "排行", "占比", "GMV", "告警")):
                return "how_to"
    if any(k in t for k in ANALYTICS_HINTS):
        return "analytics"
    return "general"
