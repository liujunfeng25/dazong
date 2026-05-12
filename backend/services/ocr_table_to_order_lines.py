"""从百度/ mock 返回的 structured 中解析采购行（品名/数量/单位）。"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, TypedDict


class RawOrderLine(TypedDict, total=False):
    ocr_product_name: str
    quantity: int
    unit: str


def _find_col_index(headers: list[str], candidates: list[str]) -> int:
    heads = [str(h or "").strip() for h in headers]
    for cand in candidates:
        for i, h in enumerate(heads):
            if cand == h or cand in h:
                return i
    return -1


def _parse_qty(v: Any) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        d = Decimal(m.group(1))
    except (InvalidOperation, ValueError):
        return None
    n = int(d)
    return n if n > 0 else None


def _parse_qty_unit(v: Any) -> tuple[Optional[int], Optional[str]]:
    """
    从类似「20斤」「6箱」「1kg」「9排」中同时提取数量与单位。
    """
    if v is None:
        return None, None
    s = str(v).strip().replace(",", "")
    if not s:
        return None, None
    m = re.search(r"(\d+(?:\.\d+)?)\s*([^\d\s]+)?", s)
    if not m:
        return None, None
    qty = _parse_qty(m.group(1))
    unit = (m.group(2) or "").strip() or None
    return qty, unit


def _normalize_table_row_cells(row: Any, min_header_cols: int) -> list[str]:
    if not isinstance(row, (list, tuple)):
        return [""] * min_header_cols
    cells = [str(c) if c is not None else "" for c in row]
    if len(cells) < min_header_cols:
        cells = cells + [""] * (min_header_cols - len(cells))
    return cells


def _first_non_empty_table(structured: dict) -> Optional[dict]:
    for tbl in structured.get("tables") or []:
        if not isinstance(tbl, dict):
            continue
        headers = tbl.get("headers") or []
        rows = tbl.get("rows") or []
        if headers or rows:
            return tbl
    return None


def _looks_like_generic_headers(headers: list[str]) -> bool:
    hs = [str(h or "").strip() for h in headers]
    if not hs:
        return True
    return all(re.match(r"^\d+$", h) for h in hs if h != "")


def parse_structured_to_raw_lines(structured: dict) -> tuple[list[RawOrderLine], Optional[str]]:
    """
    返回 (行列表, 警告信息)。
    无品名列时返回空列表与说明性警告。
    """
    tbl = _first_non_empty_table(structured)
    if not tbl:
        return [], "未识别到表格内容，请换更清晰的图片或手录。"

    headers = [str(h or "") for h in (tbl.get("headers") or [])]
    rows = tbl.get("rows") or []
    if not isinstance(rows, list):
        return [], "表格行格式异常。"

    idx_name = _find_col_index(headers, ["品名", "商品名称", "名称", "货品", "商品"])
    idx_qty = _find_col_index(
        headers, ["数量", "订货量", "要货数量", "采购量", "件数", "合计数量"]
    )
    idx_unit = _find_col_index(headers, ["单位", "计量单位"])

    heuristic_mode = False
    if idx_name < 0 and _looks_like_generic_headers(headers):
        # 百度部分票据会仅返回数字表头（0/1/2...），此时按常见双列单据启发式解析：
        # 第 1 列品名，第 2 列数量/单位。
        idx_name = 0
        if idx_qty < 0:
            idx_qty = 1 if len(headers) >= 2 else -1
        heuristic_mode = True
    elif idx_name < 0:
        return [], "未识别到「品名/商品名称」列，无法生成采购行。"

    n_cols = max(len(headers), max((len(r) for r in rows if isinstance(r, (list, tuple))), default=0))
    if n_cols <= 0:
        n_cols = len(headers) or 1

    out: list[RawOrderLine] = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        cells = _normalize_table_row_cells(row, n_cols)
        if idx_name >= len(cells):
            continue
        ocr_name = str(cells[idx_name] or "").strip()
        if not ocr_name or re.match(r"^\d+$", ocr_name):
            continue

        qty: int = 1
        if idx_qty >= 0 and idx_qty < len(cells):
            parsed = _parse_qty(cells[idx_qty])
            if parsed is not None:
                qty = parsed

        unit = "件"
        if idx_unit >= 0 and idx_unit < len(cells):
            u = str(cells[idx_unit] or "").strip()
            if u:
                unit = u
        elif idx_qty >= 0 and idx_qty < len(cells):
            q2, u2 = _parse_qty_unit(cells[idx_qty])
            if q2 is not None:
                qty = q2
            if u2:
                unit = u2

        out.append(
            RawOrderLine(ocr_product_name=ocr_name, quantity=qty, unit=unit)
        )

    if not out:
        return [], "识别到表头但无有效数据行（品名为空或无法解析）。"

    if heuristic_mode:
        return out, "未识别到标准表头，已按「第1列品名、第2列数量」规则自动解析，请核对。"
    return out, None
