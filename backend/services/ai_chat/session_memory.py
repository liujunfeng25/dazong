"""会话记忆：跨轮保留主体、日期、单号等，供 LLM 解析代词与续问。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Protocol


@dataclass
class SessionMemory:
    last_subject_name: Optional[str] = None
    last_subject_type: Optional[str] = None
    last_subject_id: Optional[int] = None
    last_start_date: Optional[str] = None
    last_end_date: Optional[str] = None
    last_order_no: Optional[str] = None
    last_statement_no: Optional[str] = None
    turn_summaries: list[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        parts: list[str] = []
        if self.last_subject_name:
            sid = f"{self.last_subject_type}#{self.last_subject_id}" if self.last_subject_id else self.last_subject_type or "?"
            parts.append(f"上次主体={self.last_subject_name}({sid})")
        if self.last_start_date or self.last_end_date:
            parts.append(f"上次日期={self.last_start_date or '?'}~{self.last_end_date or '?'}")
        if self.last_order_no:
            parts.append(f"最近订单号={self.last_order_no}")
        if self.last_statement_no:
            parts.append(f"最近账单号={self.last_statement_no}")
        if self.turn_summaries:
            parts.append("近期对话摘要：" + " | ".join(self.turn_summaries[-3:]))
        if not parts:
            return ""
        return (
            "【会话记忆】" + "；".join(parts) + "。"
            "若用户说「换成昨天/那个配送商/这个单/再来一份/那边」，请据此解析参数；"
            "若与当前问题冲突，以当前问题为准并说明。"
        )

    def to_debug(self) -> dict[str, Any]:
        return {
            "last_subject_name": self.last_subject_name,
            "last_subject_type": self.last_subject_type,
            "last_subject_id": self.last_subject_id,
            "last_start_date": self.last_start_date,
            "last_end_date": self.last_end_date,
            "last_order_no": self.last_order_no,
            "last_statement_no": self.last_statement_no,
            "turn_summaries": self.turn_summaries[-5:],
        }


_STORE: dict[str, SessionMemory] = {}


def load_session(session_id: Optional[str]) -> SessionMemory:
    if not session_id:
        return SessionMemory()
    return _STORE.setdefault(session_id, SessionMemory())


def update_session_from_tool(session_id: Optional[str], tool_name: str, args: dict[str, Any], result: dict[str, Any]) -> None:
    if not session_id:
        return
    mem = load_session(session_id)
    if tool_name == "lookup_entity_by_name":
        rows = result.get("rows") or []
        if rows:
            top = rows[0]
            mem.last_subject_name = str(top.get("name") or args.get("name") or "")
            mem.last_subject_type = str(top.get("type") or "")
            mem.last_subject_id = int(top["id"]) if top.get("id") is not None else None
    if tool_name == "generate_report":
        sname = args.get("subject_name")
        if sname:
            mem.last_subject_name = str(sname)
        if args.get("start_date"):
            mem.last_start_date = str(args["start_date"])
        if args.get("end_date"):
            mem.last_end_date = str(args["end_date"])
    for key in ("start_date", "end_date"):
        if args.get(key):
            if key == "start_date":
                mem.last_start_date = str(args[key])
            else:
                mem.last_end_date = str(args[key])
    if tool_name in ("get_delivery_metrics", "get_client_metrics", "get_supplier_metrics", "get_factory_metrics"):
        for stype, id_key in (
            ("delivery", "delivery_id"),
            ("client", "client_id"),
            ("supplier", "supplier_id"),
            ("factory", "factory_id"),
        ):
            if args.get(id_key) is not None:
                mem.last_subject_type = stype
                mem.last_subject_id = int(args[id_key])
    if tool_name == "get_order_detail":
        order_no = result.get("order_no") or args.get("order_no")
        if order_no:
            mem.last_order_no = str(order_no)
    if tool_name == "get_statement_detail":
        stmt = result.get("statement_no") or args.get("statement_no")
        if stmt:
            mem.last_statement_no = str(stmt)
    rows = result.get("rows") or []
    if isinstance(rows, list):
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            if row.get("order_no") and not mem.last_order_no:
                mem.last_order_no = str(row["order_no"])
            if row.get("statement_no") and not mem.last_statement_no:
                mem.last_statement_no = str(row["statement_no"])


def remember_turn_summary(session_id: Optional[str], user_text: str, reply: str) -> None:
    if not session_id:
        return
    mem = load_session(session_id)
    snippet = (reply or user_text or "")[:200]
    if snippet:
        mem.turn_summaries.append(snippet)
        del mem.turn_summaries[:-8]


def apply_memory_entities(mem: SessionMemory, entities: dict[str, Any]) -> dict[str, Any]:
    out = dict(entities)
    if mem.last_order_no and not out.get("latest_order_no"):
        out["latest_order_no"] = mem.last_order_no
    if mem.last_statement_no and not out.get("latest_statement_no"):
        out["latest_statement_no"] = mem.last_statement_no
    if mem.last_subject_name:
        out["session_subject_name"] = mem.last_subject_name
    if mem.last_subject_type:
        out["session_subject_type"] = mem.last_subject_type
    if mem.last_subject_id is not None:
        out["session_subject_id"] = mem.last_subject_id
    if mem.last_start_date:
        out["session_start_date"] = mem.last_start_date
    if mem.last_end_date:
        out["session_end_date"] = mem.last_end_date
    return out


def resolve_relative_day(text: str, today: date) -> Optional[tuple[str, str]]:
    t = (text or "").strip()
    from datetime import timedelta

    if any(k in t for k in ("换成昨天", "改昨天", "昨天呢", "昨日呢")):
        d = (today - timedelta(days=1)).isoformat()
        return d, d
    if any(k in t for k in ("换成今天", "改今天", "今天呢", "今日呢")):
        d = today.isoformat()
        return d, d
    return None


class _HistoryMsg(Protocol):
    role: str
    content: str


_REPORT_SUBJECT_RE = re.compile(r"^(.{2,20}?)(?:的)?(?:监管)?(?:日|周|月)报")
_SUBJECT_NOISE = frozenset({"生成", "给我", "请", "帮我", "一份", "整", "整份", "监管"})


def seed_memory_from_history(session_id: Optional[str], history: list[_HistoryMsg]) -> None:
    """从同 session 的历史消息推断主体（如「中农食迅的日报」），供续问「换成昨天呢」。"""
    if not session_id:
        return
    mem = load_session(session_id)
    if mem.last_subject_name:
        return
    for msg in reversed(history):
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else "")
        if role != "user":
            continue
        content = str(getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else "") or "").strip()
        m = _REPORT_SUBJECT_RE.match(content)
        if not m:
            continue
        name = m.group(1).strip()
        for noise in _SUBJECT_NOISE:
            name = name.replace(noise, "")
        name = name.strip()
        if len(name) >= 2:
            mem.last_subject_name = name
            return
