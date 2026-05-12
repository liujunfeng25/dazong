import logging
import re
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from dependencies import require_role
from models import Product
from services.ocr_baidu_handwriting import handwriting_words_to_structured, run_baidu_handwriting_ocr
from services.ocr_baidu_table import mock_table_structured, run_baidu_table_ocr
from services.ocr_table_to_order_lines import parse_structured_to_raw_lines

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["ocr"])


def _active_products_stmt():
    return select(Product).where(Product.is_deleted.is_(False), Product.status == "active")


def _norm_name(s: str) -> str:
    t = (s or "").strip().lower()
    # 去掉常见分隔与规格噪声，提升「同商品不同描述」的命中率
    t = re.sub(r"[（）()\[\]【】\s·•,，。:：/\\\-_*+]+", "", t)
    t = re.sub(r"\d+(?:\.\d+)?\s*(kg|g|斤|两|箱|袋|包|盒|排|件|ml|l)?", "", t)
    return t


def _match_products(ocr_name: str, products: list[Product]) -> list[Product]:
    on = (ocr_name or "").strip()
    if not on:
        return []
    on_norm = _norm_name(on)
    if not on_norm:
        return [p for p in products if on in p.name or p.name in on]
    matched: list[Product] = []
    for p in products:
        pn = p.name or ""
        pn_norm = _norm_name(pn)
        if on in pn or pn in on or on_norm in pn_norm or pn_norm in on_norm:
            matched.append(p)
    return matched


def _similarity_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return float(SequenceMatcher(None, a, b).ratio())


def _longest_common_substr_len(a: str, b: str) -> int:
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    dp = [0] * (n + 1)
    best = 0
    for i in range(1, m + 1):
        prev = 0
        for j in range(1, n + 1):
            cur = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev + 1
                if dp[j] > best:
                    best = dp[j]
            else:
                dp[j] = 0
            prev = cur
    return best


def _char_overlap_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    return inter / max(1, min(len(sa), len(sb)))


def _name_match_score(ocr_name: str, product_name: str) -> float:
    a = _norm_name(ocr_name)
    b = _norm_name(product_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    seq = _similarity_score(a, b)
    overlap = _char_overlap_ratio(a, b)
    lcs = _longest_common_substr_len(a, b) / max(1, min(len(a), len(b)))
    contain_boost = 0.22 if (a in b or b in a) else 0.0

    # 对缺字和错别字更友好：重视公共片段与字符重叠
    score = 0.42 * seq + 0.33 * overlap + 0.25 * lcs + contain_boost
    return min(score, 1.0)


def _rank_products(ocr_name: str, products: list[Product], min_score: float = 0.33) -> list[tuple[float, Product]]:
    ranked: list[tuple[float, Product]] = []
    for p in products:
        score = _name_match_score(ocr_name, p.name or "")
        if score >= min_score:
            ranked.append((score, p))
    ranked.sort(key=lambda x: (-x[0], len(x[1].name or ""), x[1].id))
    return ranked


def _strong_deterministic_hit(ocr_name: str, ranked: list[tuple[float, Product]]) -> Optional[Product]:
    """
    给“明显对应”的条目直接自动选中，减少无意义人工操作。
    判定顺序：
    1) 规范化后完全一致，且唯一；
    2) 原文完全包含（或被包含）的候选中，最短且唯一；
    3) 头名显著领先（分差更大）时自动匹配。
    """
    if not ranked:
        return None
    o = (ocr_name or "").strip()
    on = _norm_name(o)
    if not o or not on:
        return None

    exact_norm = [p for _, p in ranked if _norm_name(p.name or "") == on]
    if len(exact_norm) == 1:
        return exact_norm[0]

    contain_hits = [p for _, p in ranked if o in (p.name or "") or (p.name or "") in o]
    if len(contain_hits) == 1:
        return contain_hits[0]
    if len(contain_hits) > 1:
        contain_hits.sort(key=lambda x: (len(x.name or ""), x.id))
        shortest = contain_hits[0]
        if len(contain_hits) == 1 or len((contain_hits[1].name or "")) - len(shortest.name or "") >= 3:
            return shortest

    top_score, top_p = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if top_score >= 0.86 and top_score - second_score >= 0.18:
        return top_p
    return None


def _suggest_products_from_ranked(ranked: list[tuple[float, Product]], limit: int = 5) -> list[dict]:
    out = []
    for score, p in ranked[:limit]:
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "unit": p.unit,
                "reference_price": float(p.reference_price),
                "score": round(score, 4),
            }
        )
    return out


def _item_from_raw_line(raw: dict, products: list[Product], handwritten_mode: bool = False) -> dict:
    ocr_name = raw["ocr_product_name"]
    # 机打模式：优先走严格匹配，避免过度“智能”导致可确定项反而进入歧义
    if not handwritten_mode:
        strict_hits = _match_products(ocr_name, products)
        qty = int(raw.get("quantity") or 1)
        ocr_unit = str(raw.get("unit") or "件")
        base: dict = {
            "ocr_product_name": ocr_name,
            "quantity": max(1, qty),
            "unit_ocr": ocr_unit,
        }
        if len(strict_hits) == 1:
            p = strict_hits[0]
            return {
                **base,
                "product_id": p.id,
                "product_name": p.name,
                "unit": p.unit,
                "unit_price": float(p.reference_price),
                "match_status": "matched",
                "match_score": 1.0,
                "match_candidates": [],
            }
        if len(strict_hits) > 1:
            ranked_strict = sorted(strict_hits, key=lambda x: (len(x.name or ""), x.id))[:5]
            return {
                **base,
                "product_name": ocr_name,
                "product_id": None,
                "unit": ocr_unit,
                "unit_price": 0.0,
                "match_status": "ambiguous",
                "match_score": 0.7,
                "match_candidates": _suggest_products_from_ranked([(0.7, p) for p in ranked_strict], limit=5),
            }
        # 机打没命中才回退到容错推荐
        loose_ranked = _rank_products(ocr_name, products, min_score=0.3)
        suggestions = _suggest_products_from_ranked(loose_ranked, limit=5)
        return {
            **base,
            "product_name": ocr_name,
            "product_id": None,
            "unit": ocr_unit,
            "unit_price": 0.0,
            "match_status": "unmatched_suggested" if suggestions else "unmatched",
            "match_candidates": suggestions,
        }

    # 手写模式：走容错强匹配
    ranked = _rank_products(ocr_name, products)
    qty = int(raw.get("quantity") or 1)
    ocr_unit = str(raw.get("unit") or "件")
    base: dict = {
        "ocr_product_name": ocr_name,
        "quantity": max(1, qty),
        "unit_ocr": ocr_unit,
    }
    if ranked:
        deterministic = _strong_deterministic_hit(ocr_name, ranked)
        if deterministic is not None:
            p = deterministic
            top_score = _name_match_score(ocr_name, p.name or "")
            return {
                **base,
                "product_id": p.id,
                "product_name": p.name,
                "unit": p.unit,
                "unit_price": float(p.reference_price),
                "match_status": "matched",
                "match_score": round(top_score, 4),
                "match_candidates": [],
            }

        top_score, top_product = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        # 高置信且显著领先时自动匹配，兼容客户写不全品名或轻微错别字
        if top_score >= 0.78 and (len(ranked) == 1 or top_score - second_score >= 0.12):
            p = top_product
            return {
                **base,
                "product_id": p.id,
                "product_name": p.name,
                "unit": p.unit,
                "unit_price": float(p.reference_price),
                "match_status": "matched",
                "match_score": round(top_score, 4),
                "match_candidates": [],
            }
        # 中等置信则给候选让用户确认
        candidates = _suggest_products_from_ranked(ranked, limit=5)
        return {
            **base,
            "product_name": ocr_name,
            "product_id": None,
            "unit": ocr_unit,
            "unit_price": 0.0,
            "match_status": "ambiguous",
            "match_score": round(top_score, 4),
            "match_candidates": candidates,
        }
    # 极低置信：仍给出候选（若有），避免客户手工全搜
    loose_ranked = _rank_products(ocr_name, products, min_score=0.2)
    suggestions = _suggest_products_from_ranked(loose_ranked, limit=5)
    return {
        **base,
        "product_name": ocr_name,
        "product_id": None,
        "unit": ocr_unit,
        "unit_price": 0.0,
        "match_status": "unmatched_suggested" if suggestions else "unmatched",
        "match_candidates": suggestions,
    }


def _confidence(structured: dict, parse_warn: Optional[str], items: list, engine: str) -> float:
    if parse_warn and not items:
        return 0.25
    if parse_warn:
        return 0.55
    if not items:
        return 0.3
    if engine == "mock":
        return 0.78
    n = len(items)
    matched = sum(1 for i in items if i.get("match_status") == "matched")
    return 0.85 + 0.1 * (matched / n) if n else 0.5


@router.get("/engine")
async def ocr_engine_status(_=Depends(require_role("client"))):
    k = (settings.baidu_table_api_key or "").strip()
    eff = settings.ocr_effective_engine
    return {
        "ocr_engine": eff,
        "baidu_key_configured": bool(k),
        "using_mock_data": eff == "mock",
    }


@router.post("/parse-order")
async def parse_order_by_ocr(
    _=Depends(require_role("client")),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(400, "请上传图片文件")

    suffix = Path(file.filename).suffix.lower() or ".jpg"
    if suffix not in (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"):
        suffix = ".jpg"

    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")

    path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            path = Path(tmp.name)

        eff = settings.ocr_effective_engine
        parse_warn: Optional[str] = None
        if eff == "baidu":
            try:
                structured = await run_baidu_table_ocr(path, settings.baidu_table_api_key)
            except Exception as e:
                logger.exception("百度表格识别失败: %s", e)
                raise HTTPException(502, f"百度表格识别失败：{e!s}") from e
        else:
            structured = mock_table_structured()

        raw_lines, line_err = parse_structured_to_raw_lines(structured)
        if line_err:
            parse_warn = line_err
        handwritten_mode = False

        # 表格模式失败时，自动尝试手写兜底识别
        if eff == "baidu" and not raw_lines:
            handwriting_words = await run_baidu_handwriting_ocr(path, settings.baidu_table_api_key)
            hw_structured = handwriting_words_to_structured(handwriting_words)
            hw_lines, hw_err = parse_structured_to_raw_lines(hw_structured)
            if hw_lines:
                structured = hw_structured
                raw_lines = hw_lines
                handwritten_mode = True
                parse_warn = "已切换手写清单识别模式，请重点核对品名与数量。"
            elif hw_err and not parse_warn:
                parse_warn = hw_err

        products = (await db.scalars(_active_products_stmt())).all()
        recognized: list[dict] = []
        for raw in raw_lines:
            recognized.append(_item_from_raw_line(raw, list(products), handwritten_mode=handwritten_mode))

        summary = {
            "total": len(recognized),
            "matched": sum(1 for r in recognized if r.get("match_status") == "matched"),
            "unmatched": sum(
                1 for r in recognized if r.get("match_status") in {"unmatched", "unmatched_suggested"}
            ),
            "ambiguous": sum(1 for r in recognized if r.get("match_status") == "ambiguous"),
        }
        warnings: list[str] = []
        if parse_warn:
            warnings.append(parse_warn)
        unmatched_items = [
            r for r in recognized if r.get("match_status") in {"unmatched", "unmatched_suggested"}
        ]
        ambiguous_items = [r for r in recognized if r.get("match_status") == "ambiguous"]
        if summary["unmatched"]:
            bad = [r["ocr_product_name"] for r in unmatched_items]
            warnings.append(
                f"以下品名未在商品库中自动匹配，请手动选择：{ '、'.join(bad[:20]) }" + ("…" if len(bad) > 20 else "")
            )
            has_suggest = sum(1 for r in unmatched_items if r.get("match_candidates"))
            if has_suggest:
                warnings.append(f"其中 {has_suggest} 条已给出推荐商品，请优先在候选中确认。")
        if summary["ambiguous"]:
            warnings.append(
                f"有 {summary['ambiguous']} 条品名对应多个商品，请在购物车中点选具体商品。"
            )

        return {
            "success": bool(recognized),
            "ocr_engine": eff,
            "using_mock_data": eff == "mock",
            "structured": structured,
            "recognized_items": recognized,
            "confidence": _confidence(structured, parse_warn, recognized, eff),
            "match_summary": summary,
            "warnings": warnings,
            "match_details": {
                "unmatched": [
                    {
                        "ocr_product_name": r.get("ocr_product_name"),
                        "status": r.get("match_status"),
                        "candidates": r.get("match_candidates") or [],
                    }
                    for r in unmatched_items
                ],
                "ambiguous": [
                    {
                        "ocr_product_name": r.get("ocr_product_name"),
                        "candidates": r.get("match_candidates") or [],
                    }
                    for r in ambiguous_items
                ],
            },
        }
    finally:
        if path and path.exists():
            try:
                path.unlink()
            except OSError:
                pass
