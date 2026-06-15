"""验证批次质检「存证 + 覆盖率」口径：period_quality_coverage 的 mode 感知判定。

批次模式：分单存在批次报告即覆盖；周期模式：订单 cover_date 落在已通过周期报告有效期内即覆盖。
仅统计「已出库」分单；缺报告分单计入 missing。

helper 只对 DB 做两类查询：product_quality_mode_map（按真实 Product 取 mode）与候选周期报告查询。
因此 orders/allocations/quality_reports 用轻量替身即可，无需插入重 FK 的订单行，避免污染演示库。
"""
import asyncio
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from database import SessionLocal
from models import PeriodicQualityReport, Product, User
from services.order_quality_missing import period_quality_coverage


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _alloc(aid, order_id, product_id, supplier_id, status="已出库"):
    return SimpleNamespace(
        id=aid, order_id=order_id, product_id=product_id,
        supplier_id=supplier_id, status=status,
    )


async def _check():
    async with SessionLocal() as db:
        supplier = await db.scalar(select(User).where(User.role == "supplier"))
        batch_product = await db.scalar(
            select(Product).where(Product.quality_report_mode == "batch")
        )
        periodic_product = await db.scalar(
            select(Product).where(Product.quality_report_mode == "periodic")
        )
        assert supplier and batch_product, "演示库缺少 supplier / batch 商品"

        cover_day = date.today()
        order = SimpleNamespace(id=999001, expected_delivery_date=cover_day)
        sid = int(supplier.id)

        # batch 商品：2 行已出库 + 1 行未出库（不计入分母）；批次报告覆盖 alloc 9001
        allocs = [
            _alloc(9001, order.id, int(batch_product.id), sid),
            _alloc(9002, order.id, int(batch_product.id), sid),
            _alloc(9003, order.id, int(batch_product.id), sid, status="备货中"),
        ]
        quality_reports = [
            SimpleNamespace(allocation_id=9001, product_id=int(batch_product.id), supplier_id=sid),
        ]
        expected_shipped = 2
        expected_covered = 1

        # periodic 商品（若存在）：插一份有效期内已通过周期报告，再加一行该模式已出库分单 → 覆盖
        inserted_pqr = None
        if periodic_product:
            inserted_pqr = PeriodicQualityReport(
                provider_id=sid,
                product_id=int(periodic_product.id),
                version=1,
                valid_from=cover_day - timedelta(days=3),
                valid_to=cover_day + timedelta(days=3),
                file_url="http://example/pqc.pdf",
                report_no="PQC-COV-TEST",
                status="已通过",
            )
            db.add(inserted_pqr)
            await db.flush()
            allocs.append(_alloc(9004, order.id, int(periodic_product.id), sid))
            expected_shipped += 1
            expected_covered += 1

        cov = await period_quality_coverage(
            db, allocs, quality_reports, [order], shipped_only=True
        )
        await db.rollback()  # 不污染演示库
        return cov, expected_shipped, expected_covered


def test_period_quality_coverage_mode_aware():
    cov, expected_shipped, expected_covered = _run(_check())
    assert cov["shipped"] == expected_shipped, cov
    assert cov["covered"] == expected_covered, cov
    assert cov["missing"] == expected_shipped - expected_covered, cov
    assert cov["covered"] + cov["missing"] == cov["shipped"]
    assert cov["coverage_rate"] == round(expected_covered / expected_shipped * 100, 2), cov


def test_period_quality_coverage_empty_is_zero():
    cov = _run(_coverage_empty())
    assert cov == {"shipped": 0, "covered": 0, "missing": 0, "coverage_rate": 0.0,
                   "missing_allocations": []}


async def _coverage_empty():
    async with SessionLocal() as db:
        return await period_quality_coverage(db, [], [], [], shipped_only=True)
