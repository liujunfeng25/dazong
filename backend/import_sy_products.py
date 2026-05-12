import asyncio
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from database import SessionLocal, engine
from models import Category, Product


def _to_decimal(value, default="0") -> Decimal:
    if value in (None, "", "-"):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal(default)


def _to_int(value, default=None):
    if value in (None, "", "-"):
        return default
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return default


def _to_str(value, default="") -> str:
    if value in (None,):
        return default
    return str(value).strip()


async def _get_or_create_level1(session, name: str) -> Category:
    row = await session.scalar(
        select(Category).where(
            Category.level == 1,
            Category.name == name,
            Category.is_deleted.is_(False),
        )
    )
    if row:
        return row
    row = Category(name=name, level=1, parent_id=None, sort_order=0)
    session.add(row)
    await session.flush()
    return row


async def _get_or_create_level2(session, parent_id: int, name: str) -> Category:
    row = await session.scalar(
        select(Category).where(
            Category.level == 2,
            Category.parent_id == parent_id,
            Category.name == name,
            Category.is_deleted.is_(False),
        )
    )
    if row:
        return row
    row = Category(name=name, level=2, parent_id=parent_id, sort_order=0)
    session.add(row)
    await session.flush()
    return row


async def _find_existing_product(session, row: dict):
    goods_sn = _to_str(row.get("goods_sn"))
    if goods_sn:
        found = await session.scalar(
            select(Product).where(Product.goods_sn == goods_sn, Product.is_deleted.is_(False))
        )
        if found:
            return found
    return await session.scalar(
        select(Product).where(
            Product.name == _to_str(row.get("name")),
            Product.spec == _to_str(row.get("spec")),
            Product.unit == (_to_str(row.get("unit")) or "件"),
            Product.supplier_id == _to_int(row.get("supplier_id")),
            Product.is_deleted.is_(False),
        )
    )


async def import_sy_products(file_path: str):
    src = Path(file_path)
    payload = json.loads(src.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    if not rows:
        raise RuntimeError("未读取到商品数据，请先生成 sy-products-from-site.json")

    stats = {"created": 0, "updated": 0, "failed": 0}

    async with SessionLocal() as session:
        for idx, row in enumerate(rows, start=1):
            try:
                level1_name = _to_str(row.get("cate_name")) or "未分类"
                level2_name = _to_str(row.get("scate_name")) or "未分组"
                level1 = await _get_or_create_level1(session, level1_name)
                level2 = await _get_or_create_level2(session, level1.id, level2_name)

                status = "active" if _to_int(row.get("status"), 0) == 1 else "disabled"
                reference_price = _to_decimal(row.get("sale_price"), "0")
                if reference_price <= 0:
                    reference_price = _to_decimal(row.get("quotation_price"), "0")
                if reference_price <= 0:
                    reference_price = _to_decimal(row.get("limit_price"), "0")

                existing = await _find_existing_product(session, row)
                mapped = {
                    "goods_sn": _to_str(row.get("goods_sn")) or None,
                    "name": _to_str(row.get("name")),
                    "category1_id": level1.id,
                    "category2_id": level2.id,
                    "unit": _to_str(row.get("unit")) or "件",
                    "reference_price": reference_price,
                    "spec": _to_str(row.get("spec")),
                    "origin": _to_str(row.get("origin")),
                    "status": status,
                    "brand": _to_str(row.get("brand")) or None,
                    "expire_date": _to_str(row.get("expire_date")) or None,
                    "manufacturer": _to_str(row.get("manufacturer")) or None,
                    "model": _to_str(row.get("model")) or None,
                    "source": _to_int(row.get("source")),
                    "attr": _to_int(row.get("attr")),
                    "level": _to_int(row.get("level")),
                    "limit_price": _to_decimal(row.get("limit_price"), "0")
                    if row.get("limit_price") not in (None, "", "-")
                    else None,
                    "discount_rate": _to_decimal(row.get("discount_rate"), "0")
                    if row.get("discount_rate") not in (None, "", "-")
                    else None,
                    "float_rate_max": _to_decimal(row.get("float_rate_max"), "0")
                    if row.get("float_rate_max") not in (None, "", "-")
                    else None,
                    "float_rate_min": _to_decimal(row.get("float_rate_min"), "0")
                    if row.get("float_rate_min") not in (None, "", "-")
                    else None,
                    "supplier_id": _to_int(row.get("supplier_id")),
                    "supplier_name": _to_str(row.get("supplier_name")) or None,
                    "goods_channel": _to_int(row.get("goods_channel")),
                    "finance_code": _to_str(row.get("finance_code")) or None,
                    "finance_rate": _to_decimal(row.get("finance_rate"), "0")
                    if row.get("finance_rate") not in (None, "", "-")
                    else None,
                    "number": _to_str(row.get("number")) or None,
                    "weight": _to_decimal(row.get("weight"), "0")
                    if row.get("weight") not in (None, "", "-")
                    else None,
                    "remark": _to_str(row.get("remark")) or None,
                    "logo": _to_str(row.get("logo")) or None,
                    "slogo": _to_str(row.get("slogo")) or None,
                    "detail_images_json": row.get("raw", {}).get("detail_image_list") or [],
                    "image_list_json": row.get("raw", {}).get("image_list") or [],
                    "external_url": _to_str(row.get("url")) or None,
                    "is_deleted": False,
                    "standard_type": "standard",
                }
                if not mapped["name"]:
                    raise ValueError("商品名称为空")

                if existing:
                    for k, v in mapped.items():
                        setattr(existing, k, v)
                    stats["updated"] += 1
                else:
                    session.add(Product(**mapped))
                    stats["created"] += 1

                if idx % 200 == 0:
                    await session.flush()
            except Exception:  # noqa: BLE001
                stats["failed"] += 1

        await session.commit()

    return stats


async def _main():
    import argparse

    parser = argparse.ArgumentParser(description="导入顺义正式服商品到 products 表")
    parser.add_argument(
        "--file",
        default="sy-products-from-site.json",
        help="抓取后的商品JSON文件路径",
    )
    args = parser.parse_args()
    try:
        stats = await import_sy_products(args.file)
        print(json.dumps(stats, ensure_ascii=False))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
