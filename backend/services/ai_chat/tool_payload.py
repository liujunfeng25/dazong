"""工具结果压缩：回灌 LLM 时截断大 payload，前端仍用完整结果。"""

from __future__ import annotations

from typing import Any

_MAX_ROWS = 20
_MAX_CELL = 200


def _trim_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    return text if len(text) <= _MAX_CELL else text[: _MAX_CELL - 1] + "…"


def compact_tool_result_for_llm(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"type": "error", "summary": str(result)[:500]}
    out: dict[str, Any] = {
        "type": result.get("type"),
        "title": result.get("title"),
        "summary": result.get("summary"),
        "chart_type": result.get("chart_type"),
        "sql": result.get("sql"),
        "error": result.get("error") or result.get("message"),
    }
    rows = result.get("rows")
    if isinstance(rows, list):
        total = len(rows)
        trimmed = []
        for row in rows[:_MAX_ROWS]:
            if isinstance(row, dict):
                trimmed.append({k: _trim_cell(v) for k, v in row.items()})
            elif isinstance(row, list):
                trimmed.append([_trim_cell(v) for v in row])
            else:
                trimmed.append(_trim_cell(row))
        out["rows"] = trimmed
        if total > _MAX_ROWS:
            out["row_count"] = total
            out["rows_truncated"] = True
    columns = result.get("columns")
    if isinstance(columns, list):
        out["columns"] = columns[:20]
    for key in ("kpis", "citations", "top_clients", "by_canteen", "by_category", "by_delivery", "by_direction"):
        val = result.get(key)
        if val is not None:
            if isinstance(val, list) and len(val) > _MAX_ROWS:
                out[key] = val[:_MAX_ROWS]
                out[f"{key}_truncated"] = True
            else:
                out[key] = val
    if result.get("type") == "clarify":
        out["question"] = result.get("question") or result.get("summary")
    return {k: v for k, v in out.items() if v is not None}
