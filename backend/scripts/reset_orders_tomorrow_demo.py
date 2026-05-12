#!/usr/bin/env python3
"""
清空全部订单及依赖行，并为「中农食迅物流 / delivery001」插入一批
「期望配送日 = 北京时间明天」的测试订单（状态均为「下单」）。

特点（用于智能分单 / 排线压测）：
- 多客户：client001～client006（缺则自动创建，密码 demo123）
- 多供货商：supplier001～supplier003 均绑定 delivery001（缺则创建 002/003），经纬度分散便于距离分
- 多品类多 SKU：尽量多拉活跃商品（上限 120），每单 4～7 行明细；单价按合约品类上浮写入（与客户端下单一致）
- 报价矩阵：每个供货商对池内每个商品都有一条 SupplierProductQuote，价格带差异便于比价
- 单配送商：全部订单 delivery_id = delivery001

环境变量（可选）：
  DEMO_ORDER_COUNT   默认 72
  DEMO_MAX_PRODUCTS  默认 120（参与报价与订单行的商品池上限）

在 Docker 内执行：
  docker compose exec backend python scripts/reset_orders_tomorrow_demo.py

本机：
  cd backend && PYTHONPATH=. python3 scripts/reset_orders_tomorrow_demo.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, engine  # noqa: E402
from models import (  # noqa: E402
    AuditLog,
    Bill,
    Category,
    ClientCanteen,
    Contract,
    Delivery,
    IdempotencyKey,
    Notification,
    Order,
    OrderAbnormal,
    OrderItemAllocation,
    OrderItemStatusLog,
    OrderReceivingLine,
    OrderReview,
    OrderStatusLog,
    Product,
    QualityReport,
    SortRecord,
    SupplierProductQuote,
    Ticket,
    User,
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


async def _purge_all_orders(session: AsyncSession) -> int:
    r = await session.execute(select(Order.id))
    ids = [int(row[0]) for row in r.all()]
    if not ids:
        return 0

    await session.execute(delete(OrderReceivingLine).where(OrderReceivingLine.order_id.in_(ids)))

    alloc_ids = (
        await session.scalars(select(OrderItemAllocation.id).where(OrderItemAllocation.order_id.in_(ids)))
    ).all()
    alloc_ids_i = [int(a) for a in alloc_ids]
    if alloc_ids_i:
        await session.execute(delete(OrderItemStatusLog).where(OrderItemStatusLog.allocation_id.in_(alloc_ids_i)))
    await session.execute(delete(OrderItemAllocation).where(OrderItemAllocation.order_id.in_(ids)))

    await session.execute(delete(OrderStatusLog).where(OrderStatusLog.order_id.in_(ids)))
    await session.execute(delete(OrderReview).where(OrderReview.order_id.in_(ids)))
    await session.execute(delete(Ticket).where(Ticket.order_id.in_(ids)))
    await session.execute(delete(SortRecord).where(SortRecord.order_id.in_(ids)))
    await session.execute(delete(QualityReport).where(QualityReport.order_id.in_(ids)))
    await session.execute(delete(Bill).where(Bill.order_id.in_(ids)))
    await session.execute(delete(Delivery).where(Delivery.order_id.in_(ids)))
    await session.execute(delete(OrderAbnormal).where(OrderAbnormal.order_id.in_(ids)))
    await session.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.resource_id.in_(ids),
            IdempotencyKey.scope.in_(["order_receive", "order_settle"]),
        )
    )
    await session.execute(delete(AuditLog).where(AuditLog.object_type == "order", AuditLog.object_id.in_(ids)))
    await session.execute(
        delete(Notification).where(Notification.object_type == "order", Notification.object_id.in_(ids))
    )
    await session.execute(delete(Order).where(Order.id.in_(ids)))
    return len(ids)


async def _default_canteen_id_for_client(session: AsyncSession, client_id: int) -> int:
    row = await session.scalar(
        select(ClientCanteen.id)
        .where(ClientCanteen.school_client_id == client_id, ClientCanteen.status == "active")
        .order_by(ClientCanteen.sort_order.asc(), ClientCanteen.id.asc())
        .limit(1)
    )
    if row is None:
        raise RuntimeError(f"客户 user_id={client_id} 无可用食堂，请先执行数据库种子初始化")
    return int(row)


# (username, company, address, lng, lat)
DEMO_CLIENTS: list[tuple[str, str, str, float, float]] = [
    ("client001", "北京第一实验小学", "北京市朝阳区望京演示点", 116.481181, 39.989410),
    ("client002", "首都师范大学附属中学", "北京市海淀区中关村大街演示点", 116.316833, 39.983960),
    ("client003", "丰台第五小学（演示）", "北京市丰台区丽泽商务区演示点", 116.321, 39.866),
    ("client004", "西城区演示中学", "北京市西城区金融街演示点", 116.363227, 39.914336),
    ("client005", "朝阳区第二演示小学", "北京市朝阳区三里屯演示点", 116.454, 39.937),
    ("client006", "通州区演示幼儿园", "北京市通州区运河东大街演示点", 116.656, 39.902),
]

# (username, company, lng, lat) — supplier_delivery_id 由脚本设为 delivery001
DEMO_SUPPLIERS: list[tuple[str, str, float, float]] = [
    ("supplier001", "新发地蔬菜批发档口", 116.35, 39.81),
    ("supplier002", "天津蔬菜配送站", 117.20, 39.13),
    ("supplier003", "河北蛋品集散中心", 116.72, 39.52),
]


async def _ensure_demo_clients(session: AsyncSession) -> dict[str, User]:
    out: dict[str, User] = {}
    for username, company, address, lng, lat in DEMO_CLIENTS:
        row = await session.scalar(select(User).where(User.username == username))
        if row:
            row.company_name = company
            row.address = address
            row.lng = lng
            row.lat = lat
            out[username] = row
            continue
        u = User(
            username=username,
            password_hash=bcrypt.hashpw(b"demo123", bcrypt.gensalt()).decode("utf-8"),
            role="client",
            company_name=company,
            contact_phone="13800000000",
            address=address,
            lng=lng,
            lat=lat,
            status="active",
        )
        session.add(u)
        await session.flush()
        out[username] = u
    await session.flush()
    for username, *_ in DEMO_CLIENTS:
        if username not in out:
            out[username] = (await session.scalar(select(User).where(User.username == username)))  # type: ignore[assignment]
    return out


async def _ensure_demo_suppliers(session: AsyncSession, delivery_id: int) -> list[User]:
    out: list[User] = []
    for username, company, lng, lat in DEMO_SUPPLIERS:
        row = await session.scalar(select(User).where(User.username == username))
        if row:
            row.company_name = company
            row.lng = lng
            row.lat = lat
            row.supplier_delivery_id = int(delivery_id)
            row.status = "active"
            out.append(row)
            continue
        u = User(
            username=username,
            password_hash=bcrypt.hashpw(b"demo123", bcrypt.gensalt()).decode("utf-8"),
            role="supplier",
            company_name=company,
            contact_phone="13900000000",
            address="",
            lng=lng,
            lat=lat,
            status="active",
            supplier_delivery_id=int(delivery_id),
        )
        session.add(u)
        await session.flush()
        out.append(u)
    return out


def _order_no(prefix: str, i: int) -> str:
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")
    return f"{prefix}{ts}{i:04d}"


_SPOTS: list[tuple[str, float, float]] = [
    ("朝阳区望京街道测试点A", 116.481181, 39.989410),
    ("海淀区中关村大街测试点B", 116.316833, 39.983960),
    ("丰台区丽泽商务区测试点C", 116.321, 39.866),
    ("石景山区鲁谷街道测试点D", 116.222, 39.907),
    ("通州区运河东大街测试点E", 116.656, 39.902),
    ("大兴区亦庄测试点F", 116.506, 39.795),
    ("昌平区回龙观东大街测试点G", 116.336, 40.080),
    ("顺义区新国展附近测试点H", 116.534, 40.070),
    ("房山区长阳镇测试点I", 116.184, 39.763),
    ("门头沟区双峪路测试点J", 116.105, 39.940),
    ("东城王府井测试点K", 116.417854, 39.909946),
    ("西城什刹海测试点L", 116.384, 39.942),
]

# 6:00～20:00 每小时窗
SLOT_POOL = [f"{h:02d}:00-{h+1:02d}:00" for h in range(6, 20)]


async def _load_product_pool(session: AsyncSession, limit: int) -> list[Product]:
    rows = (
        (
            await session.execute(
                select(Product)
                .where(Product.is_deleted.is_(False))
                .order_by(Product.category1_id.asc(), Product.category2_id.asc(), Product.id.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) < 6:
        raise RuntimeError(
            "库中活跃商品不足 6 个，无法生成压测订单；请先导入商品或执行种子分类/商品。"
        )
    return list(rows)


async def _category_name_map(session: AsyncSession, cat_ids: set[int]) -> dict[int, str]:
    if not cat_ids:
        return {}
    rows = (await session.scalars(select(Category).where(Category.id.in_(cat_ids)))).all()
    return {int(c.id): (c.name or "") for c in rows}


async def _ensure_quote_matrix(
    session: AsyncSession,
    supplier_users: list[User],
    products: list[Product],
    updated_by: int,
) -> int:
    """每个供货商 × 每个商品 一条报价，价格随供货商/商品变化。"""
    n = 0
    for si, sup in enumerate(supplier_users):
        sid = int(sup.id)
        for pj, prod in enumerate(products):
            pid = int(prod.id)
            base = float(prod.reference_price or 10.0)
            factor = 0.86 + (si * 0.035) + (pj % 9) * 0.008 + (pid % 5) * 0.004
            quote = round(min(base * factor, base * 1.15), 2)
            quote = max(quote, 0.01)
            existing = await session.scalar(
                select(SupplierProductQuote.id).where(
                    SupplierProductQuote.supplier_id == sid,
                    SupplierProductQuote.product_id == pid,
                )
            )
            if existing:
                row = await session.get(SupplierProductQuote, int(existing))
                if row:
                    row.quote_price = quote
                    row.updated_by = updated_by
                continue
            session.add(
                SupplierProductQuote(
                    supplier_id=sid,
                    product_id=pid,
                    quote_price=quote,
                    remark="压测脚本报价矩阵",
                    updated_by=updated_by,
                )
            )
            n += 1
    return n


def _contract_rate_map_and_fallback(contract: Contract) -> tuple[dict[int, float], float]:
    """与 routers.orders.create_order 一致，用于压测订单写单价。"""
    rate_map: dict[int, float] = {}
    for i in contract.category_rates_json or []:
        if i.get("category_id") is not None:
            try:
                rate_map[int(i["category_id"])] = float(i.get("float_rate", 0))
            except (TypeError, ValueError):
                continue
    return rate_map, float(contract.price_float_rate or 0)


def _unit_price_with_contract_rate(
    reference_price: float,
    category1_id: int,
    rate_map: dict[int, float],
    fallback_rate: float,
) -> float:
    rate = rate_map.get(int(category1_id), fallback_rate)
    return float(
        round(Decimal(str(reference_price)) * (Decimal("1") + Decimal(str(rate))), 2)
    )


def _build_items_for_order(
    order_idx: int,
    products: list[Product],
    cat_names: dict[int, str],
    n_lines: int,
    rate_map: dict[int, float],
    fallback_rate: float,
) -> tuple[list[dict], list[dict], Decimal]:
    n = len(products)
    used: set[int] = set()
    items_json: list[dict] = []
    snap: list[dict] = []
    total = Decimal("0")
    for j in range(n_lines):
        pi = (order_idx * 11 + j * 17 + j * j) % n
        # 尽量避免同单重复 SKU
        for k in range(n):
            cand = (pi + k) % n
            pid = int(products[cand].id)
            if pid not in used or len(used) >= n:
                pi = cand
                break
        used.add(int(products[pi].id))
        p = products[pi]
        qty = 1 + (order_idx + j * 3) % 6
        ref = float(p.reference_price or 10.0)
        c1 = int(p.category1_id) if p.category1_id is not None else 0
        rate = float(rate_map.get(c1, fallback_rate)) if c1 else float(fallback_rate)
        unit_f = _unit_price_with_contract_rate(ref, c1 or 0, rate_map, fallback_rate)
        unit = Decimal(str(unit_f))
        line_total = unit * Decimal(qty)
        total += line_total
        items_json.append(
            {
                "product_id": int(p.id),
                "quantity": qty,
                "unit_price": str(unit),
            }
        )
        snap.append(
            {
                "product_id": int(p.id),
                "product_name": p.name,
                "unit": p.unit or "kg",
                "reference_price": ref,
                "category1_id": p.category1_id,
                "category1_name": cat_names.get(int(p.category1_id), "") if p.category1_id else "",
                "category2_id": p.category2_id,
                "category2_name": cat_names.get(int(p.category2_id), "") if p.category2_id else "",
                "order_quantity": qty,
                "order_unit_price": unit_f,
                "category_float_rate": rate,
                "standard_type": p.standard_type or "standard",
            }
        )
    return items_json, snap, total


async def _seed_tomorrow_orders(
    session: AsyncSession,
    *,
    order_count: int,
    max_products: int,
) -> tuple[int, int, int, int, int]:
    sh = ZoneInfo("Asia/Shanghai")
    tomorrow = (datetime.now(sh) + timedelta(days=1)).date()

    delivery = await session.scalar(select(User).where(User.username == "delivery001"))
    if not delivery:
        raise RuntimeError("缺少 delivery001，请先种子初始化。")

    client_map = await _ensure_demo_clients(session)
    supplier_users = await _ensure_demo_suppliers(session, int(delivery.id))

    products = await _load_product_pool(session, max_products)
    cat_ids: set[int] = set()
    for p in products:
        cat_ids.add(int(p.category1_id))
        cat_ids.add(int(p.category2_id))
    cat_names = await _category_name_map(session, cat_ids)

    quotes_added = await _ensure_quote_matrix(session, supplier_users, products, int(delivery.id))

    client_names = [t[0] for t in DEMO_CLIENTS]
    n_sup = len(supplier_users)

    n = 0
    for idx in range(order_count):
        cuname = client_names[idx % len(client_names)]
        client = client_map[cuname]
        active_contract = await session.scalar(
            select(Contract)
            .where(
                Contract.client_id == int(client.id),
                Contract.delivery_id == int(delivery.id),
                Contract.status == "已中标",
                Contract.period_start <= tomorrow,
                Contract.period_end >= tomorrow,
            )
            .order_by(Contract.id.desc())
        )
        if active_contract:
            rate_map, fallback_rate = _contract_rate_map_and_fallback(active_contract)
        else:
            rate_map, fallback_rate = {}, 0.0
        slot = SLOT_POOL[(idx + (idx // len(client_names))) % len(SLOT_POOL)]
        sub_i = idx % 5
        spot_i = (idx + sub_i * 2) % len(_SPOTS)
        addr, lng, lat = _SPOTS[spot_i]
        n_lines = 4 + (idx % 4)
        items_json, snap, total = _build_items_for_order(
            idx, products, cat_names, n_lines, rate_map, fallback_rate
        )
        vol = round(0.008 * n_lines + (idx % 7) * 0.003, 4)
        wgt = round(2.5 * n_lines + (idx % 5) * 0.9, 3)
        canteen_id = await _default_canteen_id_for_client(session, int(client.id))
        order = Order(
            order_no=_order_no("OD", idx + 1),
            client_id=int(client.id),
            canteen_id=canteen_id,
            delivery_id=int(delivery.id),
            supplier_id=None,
            items_json=items_json,
            items_snapshot_json=snap,
            total_amount=total,
            total_volume_m3=vol,
            total_weight_kg=wgt,
            delivery_address=(
                f"{client.company_name} · {addr}"
                f"（配送日{tomorrow}·#{idx + 1}·{slot}）"
            ),
            delivery_lng=lng + (idx % 5) * 0.0022,
            delivery_lat=lat + (idx % 3) * 0.0018,
            expected_delivery_date=tomorrow,
            expected_delivery_slot=slot,
            service_duration_min=25 + (idx % 4) * 5,
            status="下单",
            has_abnormal=False,
        )
        session.add(order)
        n += 1

    return n, len(client_names), n_sup, len(products), quotes_added


async def main() -> None:
    parser = argparse.ArgumentParser(description="清空订单脚本 / 明日演示订单")
    parser.add_argument(
        "--purge-only",
        action="store_true",
        help="仅删除全部订单及子表数据，不插入演示订单",
    )
    args = parser.parse_args()
    order_count = _env_int("DEMO_ORDER_COUNT", 72)
    max_products = _env_int("DEMO_MAX_PRODUCTS", 120)
    sh = ZoneInfo("Asia/Shanghai")
    tomorrow = (datetime.now(sh) + timedelta(days=1)).date()

    async with SessionLocal() as session:
        removed = await _purge_all_orders(session)
        await session.commit()
        if args.purge_only:
            print(f"已删除订单行数: {removed}（仅清空，未插入新订单）")
            await engine.dispose()
            return
        inserted, n_cli, n_sup, n_prod, n_quote = await _seed_tomorrow_orders(
            session,
            order_count=order_count,
            max_products=max_products,
        )
        await session.commit()

    print(f"已删除订单行数: {removed}")
    print(
        f"已插入明日({tomorrow})订单 {inserted} 条 | 客户 {n_cli} 个 | 挂靠配送商的供货商 {n_sup} 家 | "
        f"商品池 {n_prod} 个 SKU | 新写入报价行约 {n_quote}（另有已存在则已更新）"
    )
    print(f"配送商固定 delivery001；可用环境变量 DEMO_ORDER_COUNT、DEMO_MAX_PRODUCTS 调整规模。")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
