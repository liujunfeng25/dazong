#!/usr/bin/env python3
"""快麦云打印测试。用法: cd dazong/backend && python scripts/kuaimai_test_print.py"""
from __future__ import annotations

import asyncio
import os
import sys

# 允许从 backend 根目录运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from services.kuaimai_print import (
    build_label_fields,
    print_label_fields_batches,
    resolve_printer_sn,
)
from models import Order, OrderItemAllocation, Product, User


async def main() -> int:
    from types import SimpleNamespace

    sn = (settings.kuaimai_printer_sn or "KM118DW25100096").strip()
    print("快麦云打印测试")
    print(f"  打印机: {sn}")
    print(f"  模板:   {settings.kuaimai_template_id}")
    print()

    order = SimpleNamespace(
        order_no="TEST-PRINT-001",
        expected_delivery_date="2026-05-20",
        expected_delivery_slot="05:00-06:00",
    )
    alloc = SimpleNamespace(id=99999, line_no=1)
    product = SimpleNamespace(name="测试商品-大白菜", spec="一级", unit="斤")
    user = SimpleNamespace(company_name="测试供货商", username="supplier001", kuaimai_printer_sn=sn)
    row = build_label_fields(
        order=order,
        alloc=alloc,
        product=product,
        canteen_name="教师食堂",
        supplier_user=user,
    )
    try:
        job_ids = await print_label_fields_batches(sn, [row])
        print(">>> 提交成功，任务 ID:", ", ".join(job_ids))
        return 0
    except Exception as exc:
        print(">>> 失败:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
