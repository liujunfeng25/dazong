"""
百度手写文字识别兜底：
当表格 OCR 未提取到结构化表时，尝试识别手写行文本。
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import httpx

HANDWRITING_API_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/handwriting"
TIMEOUT = 60.0


async def run_baidu_handwriting_ocr(image_path: Path, api_key: str) -> list[str]:
    if not (api_key or "").strip():
        return []
    img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    key = api_key.strip()
    auth = key if key.lower().startswith("bearer ") else f"Bearer {key}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": auth,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(HANDWRITING_API_URL, data={"image": img_b64}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if data.get("error_code"):
        return []
    out: list[str] = []
    for row in data.get("words_result") or []:
        w = str((row or {}).get("words") or "").strip()
        if w:
            out.append(w)
    return out


_TAIL_QTY_RE = re.compile(
    r"^(?P<name>.+?)\s*(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>kg|KG|公斤|斤|两|箱|袋|包|盒|排|件|个|只|瓶|罐)?$"
)


def handwriting_words_to_structured(words: list[str]) -> dict:
    """
    将手写识别行转成与现有解析器兼容的简单表格结构：
    headers=[品名, 数量] rows=[[name, '20斤'], ...]
    """
    rows: list[list[str]] = []
    for line in words:
        s = re.sub(r"\s+", " ", (line or "").strip())
        if not s:
            continue
        m = _TAIL_QTY_RE.match(s)
        if m:
            name = m.group("name").strip()
            qty = m.group("qty").strip()
            unit = (m.group("unit") or "").strip()
            rows.append([name, f"{qty}{unit}".strip()])
        else:
            # 无法拆分数量时，仍保留行，数量后续默认 1
            rows.append([s, ""])
    if not rows:
        return {"tables": [], "key_values": []}
    return {"tables": [{"headers": ["品名", "数量"], "rows": rows}], "key_values": []}

