#!/usr/bin/env python3
"""
按现有商品主数据自动归位标品/非标品，并导出备份与内部审计表。

默认会写库，因为这批商品是测试数据。需要只导出不写库时加 --dry-run。

本机执行：
  cd backend && PYTHONPATH=. python3 scripts/classify_product_standard_type.py

只预览：
  cd backend && PYTHONPATH=. python3 scripts/classify_product_standard_type.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, engine  # noqa: E402
from models import Category, Product  # noqa: E402


WEIGHT_UNITS = {"斤", "公斤", "千克", "kg", "KG"}
FIXED_PACKAGE_UNITS = {
    "袋",
    "箱",
    "桶",
    "盒",
    "瓶",
    "杯",
    "包",
    "提",
    "排",
    "卷",
    "块",
    "只",
    "件",
    "托",
    "组",
}
PACKAGE_SPEC_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|KG|公斤|千克|斤|g|G|克|ml|ML|毫升|L|l|升)"
    r"|(\d+)\s*(袋|箱|桶|盒|瓶|杯|包|提|排|卷|块|只|件|托|组|枚)"
)

FIELDNAMES = [
    "product_id",
    "name",
    "category1",
    "category2",
    "unit",
    "spec",
    "current_standard_type",
    "suggested_standard_type",
    "confidence",
    "reason",
    "needs_review",
    "unit_weight_kg",
    "suggested_unit_weight_kg",
    "weight_reason",
]


@dataclass(frozen=True)
class Classification:
    suggested_standard_type: str
    confidence: str
    reason: str
    needs_review: bool
    suggested_unit_weight_kg: str = ""
    weight_reason: str = ""


def _clean(value: object) -> str:
    return str(value or "").strip()


def classify_product(product: Product, category1: str, category2: str) -> Classification:
    unit = _clean(product.unit)
    name = _clean(product.name)
    spec = _clean(product.spec)
    text = f"{name} {spec} {category1} {category2}"
    has_bulk = "散装" in text
    has_package_spec = bool(PACKAGE_SPEC_RE.search(text))

    if unit in WEIGHT_UNITS:
        if has_bulk:
            return Classification(
                suggested_standard_type="non_standard",
                confidence="high",
                reason=f"单位为{unit}且名称/规格含散装，按重量称重验收",
                needs_review=False,
            )
        return Classification(
            suggested_standard_type="non_standard",
            confidence="high",
            reason=f"单位为{unit}，按重量下单/计价，智能秤按kg读数后换算",
            needs_review=False,
        )

    if has_bulk:
        return Classification(
            suggested_standard_type="non_standard",
            confidence="medium",
            reason="名称/规格含散装，机器定版为按重量称重验收",
            needs_review=False,
        )

    if unit in FIXED_PACKAGE_UNITS:
        if has_package_spec:
            return Classification(
                suggested_standard_type="standard",
                confidence="high",
                reason=f"单位为固定包装单位{unit}，且名称/规格包含包装规格",
                needs_review=False,
            )
        return Classification(
            suggested_standard_type="standard",
            confidence="medium",
            reason=f"单位为固定包装单位{unit}，机器定版为按件数/包装验收",
            needs_review=False,
        )

    return Classification(
        suggested_standard_type="standard",
        confidence="low",
        reason="单位不在重量/固定包装规则内，机器定版暂按标品保留",
        needs_review=False,
    )


def _row(product: Product, category1: str, category2: str, c: Classification | None = None) -> dict[str, object]:
    suggested = c.suggested_standard_type if c else _clean(product.standard_type)
    return {
        "product_id": int(product.id),
        "name": _clean(product.name),
        "category1": category1,
        "category2": category2,
        "unit": _clean(product.unit),
        "spec": _clean(product.spec),
        "current_standard_type": _clean(product.standard_type),
        "suggested_standard_type": suggested,
        "confidence": c.confidence if c else "",
        "reason": c.reason if c else "",
        "needs_review": "true" if c and c.needs_review else "false",
        "unit_weight_kg": "" if product.unit_weight_kg is None else str(product.unit_weight_kg),
        "suggested_unit_weight_kg": c.suggested_unit_weight_kg if c else "",
        "weight_reason": c.weight_reason if c else "",
    }


def _write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


async def _load_products(session: AsyncSession) -> tuple[list[Product], dict[int, str]]:
    products = (
        await session.scalars(
            select(Product)
            .where(Product.is_deleted.is_(False))
            .order_by(Product.id.asc())
        )
    ).all()
    category_ids = sorted(
        {
            int(cid)
            for p in products
            for cid in (p.category1_id, p.category2_id)
            if cid is not None
        }
    )
    if not category_ids:
        return list(products), {}
    categories = (
        await session.execute(select(Category.id, Category.name).where(Category.id.in_(category_ids)))
    ).all()
    category_names = {int(cid): _clean(name) for cid, name in categories}
    return list(products), category_names


def _copy_latest(batch_dir: Path, latest_dir: Path) -> None:
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    latest_dir.mkdir(parents=True, exist_ok=True)
    for src in batch_dir.glob("*.csv"):
        shutil.copy2(src, latest_dir / src.name)


async def run(dry_run: bool) -> dict[str, object]:
    out_root = Path(__file__).resolve().parents[1] / "public_downloads" / "product_standard_type"
    batch_dir = out_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    latest_dir = out_root / "latest"

    async with SessionLocal() as session:
        products, category_names = await _load_products(session)
        before_rows = []
        result_rows = []
        review_rows = []
        changed = 0
        suggested_counts: Counter[str] = Counter()
        review_count = 0

        for product in products:
            category1 = category_names.get(int(product.category1_id), "")
            category2 = category_names.get(int(product.category2_id), "")
            c = classify_product(product, category1, category2)
            before_rows.append(_row(product, category1, category2))
            result_rows.append(_row(product, category1, category2, c))
            suggested_counts[c.suggested_standard_type] += 1
            if c.needs_review:
                review_count += 1
                review_rows.append(_row(product, category1, category2, c))
            if _clean(product.standard_type) != c.suggested_standard_type:
                changed += 1
                product.standard_type = c.suggested_standard_type

        _write_csv(batch_dir / "product_standard_type_before.csv", before_rows)
        _write_csv(batch_dir / "product_standard_type_result.csv", result_rows)
        _write_csv(batch_dir / "product_standard_type_review.csv", review_rows)
        _copy_latest(batch_dir, latest_dir)

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return {
        "dry_run": dry_run,
        "products": len(products),
        "changed": 0 if dry_run else changed,
        "would_change": changed,
        "suggested_counts": dict(sorted(suggested_counts.items())),
        "review_count": review_count,
        "batch_dir": str(batch_dir),
        "latest_dir": str(latest_dir),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自动归位商品标品/非标品并导出CSV")
    parser.add_argument("--dry-run", action="store_true", help="只导出CSV并回滚，不写入 products.standard_type")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    summary = await run(dry_run=bool(args.dry_run))
    print("product standard_type classification finished")
    for key, value in summary.items():
        print(f"{key}: {value}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
