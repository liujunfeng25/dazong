from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Category, Product


@dataclass
class FillSuggestion:
    values: dict[str, float]
    confidence: float
    source: str
    matched_rule: str


# 分类默认模板（单位：cm/kg，体积修正系数无量纲）
CATEGORY_DEFAULTS: dict[str, dict[str, float]] = {
    "肉": {
        "length_cm": 24.0,
        "width_cm": 18.0,
        "height_cm": 5.0,
        "unit_weight_kg": 1.0,
        "volume_adjust_factor": 1.08,
    },
    "米": {
        "length_cm": 36.0,
        "width_cm": 24.0,
        "height_cm": 8.0,
        "unit_weight_kg": 5.0,
        "volume_adjust_factor": 1.02,
    },
    "奶": {
        "length_cm": 25.0,
        "width_cm": 17.0,
        "height_cm": 20.0,
        "unit_weight_kg": 4.0,
        "volume_adjust_factor": 1.03,
    },
    "面": {
        "length_cm": 38.0,
        "width_cm": 24.0,
        "height_cm": 9.0,
        "unit_weight_kg": 5.0,
        "volume_adjust_factor": 1.02,
    },
    "蛋": {
        "length_cm": 30.0,
        "width_cm": 30.0,
        "height_cm": 8.0,
        "unit_weight_kg": 5.0,
        "volume_adjust_factor": 1.06,
    },
    "油": {
        "length_cm": 31.0,
        "width_cm": 25.0,
        "height_cm": 33.0,
        "unit_weight_kg": 17.5,
        "volume_adjust_factor": 1.01,
    },
    "调味品": {
        "length_cm": 30.0,
        "width_cm": 22.0,
        "height_cm": 28.0,
        "unit_weight_kg": 12.0,
        "volume_adjust_factor": 1.05,
    },
}

# 关键词模板：按命中优先于分类模板
KEYWORD_RULES: list[dict[str, Any]] = [
    {
        "name": "肉馅",
        "keywords": ["肉馅"],
        "values": {
            "length_cm": 20.0,
            "width_cm": 14.0,
            "height_cm": 4.0,
            "unit_weight_kg": 1.0,
            "volume_adjust_factor": 1.12,
        },
        "confidence": 0.96,
    },
    {
        "name": "肉丁肉块肉片",
        "keywords": ["肉丁", "肉块", "肉片", "里脊", "牛腩", "羊排", "肋排", "排骨"],
        "values": {
            "length_cm": 24.0,
            "width_cm": 18.0,
            "height_cm": 5.5,
            "unit_weight_kg": 1.0,
            "volume_adjust_factor": 1.1,
        },
        "confidence": 0.93,
    },
    {
        "name": "鸡鸭整只",
        "keywords": ["老母鸡", "三黄鸡", "烤鸭", "鸭坯", "半片鸭", "整鸭"],
        "values": {
            "length_cm": 36.0,
            "width_cm": 24.0,
            "height_cm": 13.0,
            "unit_weight_kg": 2.5,
            "volume_adjust_factor": 1.2,
        },
        "confidence": 0.9,
    },
    {
        "name": "鸡腿鸡翅鸭腿",
        "keywords": ["鸡腿", "鸡翅", "鸭腿", "鸭翅", "鸭脖"],
        "values": {
            "length_cm": 28.0,
            "width_cm": 19.0,
            "height_cm": 8.0,
            "unit_weight_kg": 2.0,
            "volume_adjust_factor": 1.16,
        },
        "confidence": 0.88,
    },
    {
        "name": "牛奶酸奶乳制品",
        "keywords": ["牛奶", "酸奶", "奶酪", "奶"],
        "values": {
            "length_cm": 25.0,
            "width_cm": 17.0,
            "height_cm": 20.0,
            "unit_weight_kg": 4.0,
            "volume_adjust_factor": 1.03,
        },
        "confidence": 0.9,
    },
    {
        "name": "鸡蛋",
        "keywords": ["鸡蛋", "鸭蛋", "鹌鹑蛋", "蛋"],
        "values": {
            "length_cm": 30.0,
            "width_cm": 30.0,
            "height_cm": 8.0,
            "unit_weight_kg": 5.0,
            "volume_adjust_factor": 1.06,
        },
        "confidence": 0.89,
    },
]

NON_STANDARD_CONFIDENCE_THRESHOLD = 0.9
STANDARD_AUTO_WRITE_THRESHOLD = 0.86
TRACK_FIELDS = [
    "length_cm",
    "width_cm",
    "height_cm",
    "unit_weight_kg",
    "volume_adjust_factor",
]
WEIGHT_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|公斤|千克|克|斤|ml|l|升|毫升)", re.IGNORECASE)
MULTIPLIER_RE = re.compile(r"(?:\*|x|×)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def _normalize_text(v: Optional[str]) -> str:
    return (v or "").strip().lower()


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _infer_suggestion(
    product_name: str,
    category1_name: str,
    category2_name: str,
) -> Optional[FillSuggestion]:
    name_norm = _normalize_text(product_name)
    c1_norm = _normalize_text(category1_name)
    c2_norm = _normalize_text(category2_name)

    spec_suggestion = _infer_from_spec(name_norm=name_norm, c1_norm=c1_norm, c2_norm=c2_norm)
    if spec_suggestion:
        return spec_suggestion

    for rule in KEYWORD_RULES:
        hits = [kw for kw in rule["keywords"] if kw in name_norm]
        if not hits:
            continue
        score = min(0.99, float(rule["confidence"]) + 0.01 * min(len(hits), 3))
        return FillSuggestion(
            values=rule["values"],
            confidence=score,
            source="keyword",
            matched_rule=f"{rule['name']}:{'|'.join(hits)}",
        )

    for key, values in CATEGORY_DEFAULTS.items():
        if key in c2_norm or key in c1_norm:
            return FillSuggestion(
                values=values,
                confidence=0.78,
                source="category_default",
                matched_rule=f"category:{key}",
            )
    return None


def _unit_to_kg(value: float, unit: str) -> Optional[float]:
    u = unit.lower()
    if u in {"kg", "公斤", "千克"}:
        return value
    if u in {"g", "克"}:
        return value / 1000
    if u in {"斤"}:
        return value / 2
    if u in {"ml", "毫升"}:
        return value / 1000
    if u in {"l", "升"}:
        return value
    return None


def _extract_weight_kg(name_norm: str) -> tuple[Optional[float], str]:
    m = WEIGHT_TOKEN_RE.search(name_norm)
    if not m:
        return None, ""
    base_value = float(m.group(1))
    base_kg = _unit_to_kg(base_value, m.group(2))
    if base_kg is None:
        return None, ""
    multiplier = 1.0
    mult_match = MULTIPLIER_RE.search(name_norm)
    if mult_match:
        multiplier = float(mult_match.group(1))
    total_kg = max(0.01, base_kg * multiplier)
    return total_kg, f"{m.group(1)}{m.group(2)}*{multiplier:g}"


def _estimate_dims_from_weight(weight_kg: float, c1_norm: str, c2_norm: str) -> dict[str, float]:
    # 经验密度（kg/m3）+ 包装松散系数
    density = 950.0
    adjust = 1.05
    if "肉" in c1_norm or "猪" in c2_norm or "牛" in c2_norm or "羊" in c2_norm:
        density = 1020.0
        adjust = 1.12
    elif "米" in c1_norm or "面" in c1_norm:
        density = 850.0
        adjust = 1.02
    elif "奶" in c1_norm or "油" in c1_norm:
        density = 980.0
        adjust = 1.01
    elif "蛋" in c1_norm:
        density = 900.0
        adjust = 1.08
    volume_cm3 = weight_kg / density * 1_000_000 * adjust
    side = max(10.0, volume_cm3 ** (1 / 3))
    length = side * 1.35
    width = side * 1.0
    height = side * 0.7
    return {
        "length_cm": round(length, 2),
        "width_cm": round(width, 2),
        "height_cm": round(height, 2),
        "unit_weight_kg": round(weight_kg, 3),
        "volume_adjust_factor": round(adjust, 3),
    }


def _infer_from_spec(name_norm: str, c1_norm: str, c2_norm: str) -> Optional[FillSuggestion]:
    weight_kg, token = _extract_weight_kg(name_norm)
    if weight_kg is None:
        return None
    dims = _estimate_dims_from_weight(weight_kg=weight_kg, c1_norm=c1_norm, c2_norm=c2_norm)
    confidence = 0.94
    if "*" not in token and weight_kg < 0.4:
        confidence = 0.9
    if math.isnan(dims["length_cm"]) or dims["length_cm"] <= 0:
        return None
    return FillSuggestion(
        values=dims,
        confidence=confidence,
        source="spec_parser",
        matched_rule=f"spec:{token}",
    )


async def fill_product_dimensions(
    db: AsyncSession,
    dry_run: bool = True,
    only_missing: bool = True,
    batch_size: int = 300,
) -> dict[str, Any]:
    categories = (
        await db.scalars(select(Category).where(Category.is_deleted.is_(False)))
    ).all()
    category_name_by_id = {int(c.id): c.name for c in categories}

    products = (
        await db.scalars(select(Product).where(Product.is_deleted.is_(False)).order_by(Product.id.asc()))
    ).all()
    category1_metrics: dict[str, dict[str, list[float]]] = {}
    category2_metrics: dict[str, dict[str, list[float]]] = {}
    signature_metrics: dict[str, dict[str, list[float]]] = {}
    for p in products:
        metric_values = {f: _to_float(getattr(p, f, None)) for f in TRACK_FIELDS}
        if any(metric_values[f] is None for f in TRACK_FIELDS):
            continue
        c1_name = category_name_by_id.get(int(p.category1_id), "")
        c2_name = category_name_by_id.get(int(p.category2_id), "")
        sig = _name_signature(_normalize_text(p.name))
        _push_metrics(category1_metrics, c1_name, metric_values)
        _push_metrics(category2_metrics, c2_name, metric_values)
        _push_metrics(signature_metrics, f"{c2_name}::{sig}", metric_values)

    result_preview: list[dict[str, Any]] = []
    skipped_low_confidence = 0
    skipped_no_rule = 0
    updated = 0
    standard_updated = 0
    non_standard_updated = 0
    by_category: dict[str, int] = {}
    by_source: dict[str, int] = {}

    touched_since_commit = 0
    for p in products:
        current_values = {f: _to_float(getattr(p, f, None)) for f in TRACK_FIELDS}
        if only_missing and all(current_values[f] is not None for f in TRACK_FIELDS):
            continue

        c1_name = category_name_by_id.get(int(p.category1_id), "")
        c2_name = category_name_by_id.get(int(p.category2_id), "")
        suggestion = _infer_suggestion(product_name=p.name, category1_name=c1_name, category2_name=c2_name)
        if not suggestion:
            skipped_no_rule += 1
            continue

        is_non_standard = str(p.standard_type or "standard") == "non_standard"
        is_standard = not is_non_standard

        # 第二阶段：对低置信度结果做“同类目中位数”拟合补全，提升真实性
        if suggestion.confidence < STANDARD_AUTO_WRITE_THRESHOLD and is_standard:
            fit = _impute_from_medians(
                name_norm=_normalize_text(p.name),
                category1_name=c1_name,
                category2_name=c2_name,
                signature_metrics=signature_metrics,
                category2_metrics=category2_metrics,
                category1_metrics=category1_metrics,
            )
            if fit:
                suggestion = fit
            else:
                skipped_low_confidence += 1
                continue
        if is_non_standard and suggestion.confidence < NON_STANDARD_CONFIDENCE_THRESHOLD:
            skipped_low_confidence += 1
            continue

        write_values: dict[str, float] = {}
        for field in TRACK_FIELDS:
            if only_missing and current_values[field] is not None:
                continue
            val = suggestion.values.get(field)
            if val is not None:
                write_values[field] = float(val)

        if not write_values:
            continue

        updated += 1
        by_category[c1_name or "未知分类"] = by_category.get(c1_name or "未知分类", 0) + 1
        by_source[suggestion.source] = by_source.get(suggestion.source, 0) + 1
        if is_non_standard:
            non_standard_updated += 1
        else:
            standard_updated += 1

        result_preview.append(
            {
                "product_id": int(p.id),
                "product_name": p.name,
                "standard_type": p.standard_type,
                "category1_name": c1_name,
                "category2_name": c2_name,
                "fill_values": write_values,
                "source": suggestion.source,
                "confidence": round(suggestion.confidence, 4),
                "matched_rule": suggestion.matched_rule,
            }
        )

        if not dry_run:
            for field, value in write_values.items():
                setattr(p, field, value)
            _push_metrics(category1_metrics, c1_name, write_values)
            _push_metrics(category2_metrics, c2_name, write_values)
            _push_metrics(signature_metrics, f"{c2_name}::{_name_signature(_normalize_text(p.name))}", write_values)
            touched_since_commit += 1
            if touched_since_commit >= batch_size:
                await db.commit()
                touched_since_commit = 0

    if not dry_run and touched_since_commit > 0:
        await db.commit()

    top_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:20]
    return {
        "dry_run": dry_run,
        "only_missing": only_missing,
        "total_products": len(products),
        "updated_count": updated,
        "standard_updated_count": standard_updated,
        "non_standard_updated_count": non_standard_updated,
        "skipped_low_confidence_count": skipped_low_confidence,
        "skipped_no_rule_count": skipped_no_rule,
        "non_standard_confidence_threshold": NON_STANDARD_CONFIDENCE_THRESHOLD,
        "by_category_top20": [{"category": k, "count": v} for k, v in top_categories],
        "by_source": by_source,
        "preview_items": result_preview[:300],
    }


def _name_signature(name_norm: str) -> str:
    for token in ("肉馅", "肉丁", "肉块", "肉片", "肉丝", "排骨", "肋排", "牛腩", "牛腱", "鸡腿", "鸡翅", "鸭腿", "鸭翅", "鸡蛋"):
        if token in name_norm:
            return token
    return "generic"


def _push_metrics(target: dict[str, dict[str, list[float]]], key: str, values: dict[str, float]) -> None:
    if not key:
        return
    bucket = target.setdefault(key, {f: [] for f in TRACK_FIELDS})
    for field in TRACK_FIELDS:
        val = values.get(field)
        if val is not None:
            bucket[field].append(float(val))


def _median_values(values_map: dict[str, list[float]]) -> Optional[dict[str, float]]:
    out: dict[str, float] = {}
    for field in TRACK_FIELDS:
        arr = values_map.get(field, [])
        if not arr:
            return None
        out[field] = round(float(median(arr)), 3)
    return out


def _impute_from_medians(
    name_norm: str,
    category1_name: str,
    category2_name: str,
    signature_metrics: dict[str, dict[str, list[float]]],
    category2_metrics: dict[str, dict[str, list[float]]],
    category1_metrics: dict[str, dict[str, list[float]]],
) -> Optional[FillSuggestion]:
    sig_key = f"{category2_name}::{_name_signature(name_norm)}"
    if sig_key in signature_metrics:
        vals = _median_values(signature_metrics[sig_key])
        if vals:
            return FillSuggestion(
                values=vals,
                confidence=0.91,
                source="median_signature",
                matched_rule=f"median:{sig_key}",
            )
    if category2_name in category2_metrics:
        vals = _median_values(category2_metrics[category2_name])
        if vals:
            return FillSuggestion(
                values=vals,
                confidence=0.88,
                source="median_category2",
                matched_rule=f"median:{category2_name}",
            )
    if category1_name in category1_metrics:
        vals = _median_values(category1_metrics[category1_name])
        if vals:
            return FillSuggestion(
                values=vals,
                confidence=0.86,
                source="median_category1",
                matched_rule=f"median:{category1_name}",
            )
    return None
