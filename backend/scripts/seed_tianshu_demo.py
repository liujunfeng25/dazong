#!/usr/bin/env python3
"""
幂等生成监管端「天枢大屏」演示数据。

仅清理 order_no 以 TSDEMO 开头的订单及其依赖行，不删除真实业务数据。

用法：
  cd backend && PYTHONPATH=. python3 scripts/seed_tianshu_demo.py
  docker compose exec backend python scripts/seed_tianshu_demo.py
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal, engine  # noqa: E402
from models import (  # noqa: E402
    Alert,
    AuditLog,
    Bill,
    Category,
    ClientCanteen,
    Delivery,
    IdempotencyKey,
    IoTData,
    Notification,
    Order,
    OrderAbnormal,
    OrderItemAllocation,
    OrderItemStatusLog,
    OrderReceivingLine,
    OrderReturn,
    OrderReturnLine,
    OrderReview,
    OrderStatusLog,
    Product,
    QualityReport,
    SortRecord,
    SupplierProductQuote,
    Ticket,
    User,
)


TZ = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc
ORDER_PREFIX = "TSDEMO"

DEMO_DELIVERY_SPOTS = [
    {"district": "东城区", "name": "东华门保障点", "address": "北京市东城区东华门街道天枢演示点01", "lng": 116.4074, "lat": 39.9142},
    {"district": "东城区", "name": "崇文门保障点", "address": "北京市东城区崇文门外街道天枢演示点02", "lng": 116.4213, "lat": 39.9008},
    {"district": "西城区", "name": "金融街保障点", "address": "北京市西城区金融街街道天枢演示点03", "lng": 116.3606, "lat": 39.9155},
    {"district": "西城区", "name": "德胜保障点", "address": "北京市西城区德胜街道天枢演示点04", "lng": 116.3792, "lat": 39.9574},
    {"district": "朝阳区", "name": "望京保障点", "address": "北京市朝阳区望京街道天枢演示点05", "lng": 116.4812, "lat": 39.9894},
    {"district": "朝阳区", "name": "国贸保障点", "address": "北京市朝阳区建外街道天枢演示点06", "lng": 116.4612, "lat": 39.9147},
    {"district": "朝阳区", "name": "亚运村保障点", "address": "北京市朝阳区亚运村街道天枢演示点07", "lng": 116.4078, "lat": 40.0036},
    {"district": "海淀区", "name": "中关村保障点", "address": "北京市海淀区中关村街道天枢演示点08", "lng": 116.3162, "lat": 39.9831},
    {"district": "海淀区", "name": "上地保障点", "address": "北京市海淀区上地街道天枢演示点09", "lng": 116.3082, "lat": 40.0471},
    {"district": "海淀区", "name": "万寿路保障点", "address": "北京市海淀区万寿路街道天枢演示点10", "lng": 116.2944, "lat": 39.9136},
    {"district": "丰台区", "name": "丽泽保障点", "address": "北京市丰台区丽泽商务区天枢演示点11", "lng": 116.3265, "lat": 39.8677},
    {"district": "丰台区", "name": "方庄保障点", "address": "北京市丰台区方庄街道天枢演示点12", "lng": 116.4352, "lat": 39.8617},
    {"district": "丰台区", "name": "科技园保障点", "address": "北京市丰台区科技园区天枢演示点13", "lng": 116.2937, "lat": 39.8312},
    {"district": "石景山区", "name": "古城保障点", "address": "北京市石景山区古城街道天枢演示点14", "lng": 116.1909, "lat": 39.9076},
    {"district": "石景山区", "name": "八角保障点", "address": "北京市石景山区八角街道天枢演示点15", "lng": 116.2127, "lat": 39.9144},
    {"district": "通州区", "name": "运河保障点", "address": "北京市通州区潞城镇天枢演示点16", "lng": 116.7349, "lat": 39.9028},
    {"district": "通州区", "name": "梨园保障点", "address": "北京市通州区梨园镇天枢演示点17", "lng": 116.6621, "lat": 39.8832},
    {"district": "通州区", "name": "宋庄保障点", "address": "北京市通州区宋庄镇天枢演示点18", "lng": 116.7201, "lat": 39.9655},
    {"district": "昌平区", "name": "回龙观保障点", "address": "北京市昌平区回龙观街道天枢演示点19", "lng": 116.3368, "lat": 40.0709},
    {"district": "昌平区", "name": "沙河保障点", "address": "北京市昌平区沙河镇天枢演示点20", "lng": 116.2887, "lat": 40.1481},
    {"district": "昌平区", "name": "南口保障点", "address": "北京市昌平区南口镇天枢演示点21", "lng": 116.1397, "lat": 40.2384},
    {"district": "大兴区", "name": "亦庄保障点", "address": "北京市大兴区亦庄镇天枢演示点22", "lng": 116.5062, "lat": 39.8086},
    {"district": "大兴区", "name": "黄村保障点", "address": "北京市大兴区黄村镇天枢演示点23", "lng": 116.3415, "lat": 39.7269},
    {"district": "大兴区", "name": "庞各庄保障点", "address": "北京市大兴区庞各庄镇天枢演示点24", "lng": 116.3229, "lat": 39.6223},
    {"district": "顺义区", "name": "后沙峪保障点", "address": "北京市顺义区后沙峪镇天枢演示点25", "lng": 116.5467, "lat": 40.1095},
    {"district": "顺义区", "name": "仁和保障点", "address": "北京市顺义区仁和镇天枢演示点26", "lng": 116.6546, "lat": 40.1289},
    {"district": "顺义区", "name": "李桥保障点", "address": "北京市顺义区李桥镇天枢演示点27", "lng": 116.6918, "lat": 40.0516},
    {"district": "房山区", "name": "良乡保障点", "address": "北京市房山区良乡镇天枢演示点28", "lng": 116.1435, "lat": 39.7486},
    {"district": "房山区", "name": "长阳保障点", "address": "北京市房山区长阳镇天枢演示点29", "lng": 116.2129, "lat": 39.7635},
    {"district": "房山区", "name": "窦店保障点", "address": "北京市房山区窦店镇天枢演示点30", "lng": 116.0801, "lat": 39.6475},
    {"district": "门头沟区", "name": "永定保障点", "address": "北京市门头沟区永定镇天枢演示点31", "lng": 116.1082, "lat": 39.9407},
    {"district": "门头沟区", "name": "龙泉保障点", "address": "北京市门头沟区龙泉镇天枢演示点32", "lng": 116.1013, "lat": 39.9982},
    {"district": "怀柔区", "name": "怀柔保障点", "address": "北京市怀柔区龙山街道天枢演示点33", "lng": 116.6386, "lat": 40.3225},
    {"district": "怀柔区", "name": "雁栖保障点", "address": "北京市怀柔区雁栖镇天枢演示点34", "lng": 116.6818, "lat": 40.3788},
    {"district": "平谷区", "name": "平谷保障点", "address": "北京市平谷区滨河街道天枢演示点35", "lng": 117.1213, "lat": 40.1406},
    {"district": "平谷区", "name": "马坊保障点", "address": "北京市平谷区马坊镇天枢演示点36", "lng": 117.0086, "lat": 40.0643},
    {"district": "密云区", "name": "密云保障点", "address": "北京市密云区鼓楼街道天枢演示点37", "lng": 116.8431, "lat": 40.3763},
    {"district": "密云区", "name": "溪翁庄保障点", "address": "北京市密云区溪翁庄镇天枢演示点38", "lng": 116.8045, "lat": 40.4701},
    {"district": "延庆区", "name": "延庆保障点", "address": "北京市延庆区儒林街道天枢演示点39", "lng": 115.9855, "lat": 40.4653},
    {"district": "延庆区", "name": "康庄保障点", "address": "北京市延庆区康庄镇天枢演示点40", "lng": 115.8921, "lat": 40.3716},
    {"district": "朝阳区", "name": "酒仙桥保障点", "address": "北京市朝阳区酒仙桥街道天枢演示点41", "lng": 116.4966, "lat": 39.9731},
    {"district": "海淀区", "name": "学院路保障点", "address": "北京市海淀区学院路街道天枢演示点42", "lng": 116.3531, "lat": 39.9933},
    {"district": "丰台区", "name": "卢沟桥保障点", "address": "北京市丰台区卢沟桥街道天枢演示点43", "lng": 116.2331, "lat": 39.8494},
    {"district": "通州区", "name": "台湖保障点", "address": "北京市通州区台湖镇天枢演示点44", "lng": 116.6426, "lat": 39.8198},
    {"district": "昌平区", "name": "天通苑保障点", "address": "北京市昌平区天通苑北街道天枢演示点45", "lng": 116.4198, "lat": 40.0832},
    {"district": "大兴区", "name": "旧宫保障点", "address": "北京市大兴区旧宫镇天枢演示点46", "lng": 116.4607, "lat": 39.8122},
    {"district": "顺义区", "name": "空港保障点", "address": "北京市顺义区空港街道天枢演示点47", "lng": 116.5694, "lat": 40.0802},
    {"district": "房山区", "name": "燕山保障点", "address": "北京市房山区燕山办事处天枢演示点48", "lng": 115.9622, "lat": 39.7299},
]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _cn_to_utc_naive(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    cn = datetime.combine(day, time(hour, minute, second), tzinfo=TZ)
    return cn.astimezone(UTC).replace(tzinfo=None)


def _order_no(seq: int, day: date) -> str:
    return f"{ORDER_PREFIX}{day.strftime('%Y%m%d')}{seq:05d}"


async def _purge_demo_orders(session: AsyncSession) -> int:
    ids = [
        int(x)
        for x in (
            await session.scalars(select(Order.id).where(Order.order_no.like(f"{ORDER_PREFIX}%")))
        ).all()
    ]
    if not ids:
        await session.execute(delete(Alert).where(Alert.type == "tianshu_demo"))
        await session.execute(delete(IoTData).where(IoTData.device_id.like("TSDEMO%")))
        await session.commit()
        return 0

    return_ids = [
        int(x)
        for x in (
            await session.scalars(select(OrderReturn.id).where(OrderReturn.order_id.in_(ids)))
        ).all()
    ]
    if return_ids:
        await session.execute(delete(OrderReturnLine).where(OrderReturnLine.order_return_id.in_(return_ids)))
    alloc_ids = [
        int(x)
        for x in (
            await session.scalars(select(OrderItemAllocation.id).where(OrderItemAllocation.order_id.in_(ids)))
        ).all()
    ]
    if alloc_ids:
        await session.execute(delete(OrderItemStatusLog).where(OrderItemStatusLog.allocation_id.in_(alloc_ids)))

    await session.execute(delete(OrderReceivingLine).where(OrderReceivingLine.order_id.in_(ids)))
    await session.execute(delete(OrderItemAllocation).where(OrderItemAllocation.order_id.in_(ids)))
    await session.execute(delete(OrderStatusLog).where(OrderStatusLog.order_id.in_(ids)))
    await session.execute(delete(OrderReview).where(OrderReview.order_id.in_(ids)))
    await session.execute(delete(Ticket).where(Ticket.order_id.in_(ids)))
    await session.execute(delete(SortRecord).where(SortRecord.order_id.in_(ids)))
    await session.execute(delete(QualityReport).where(QualityReport.order_id.in_(ids)))
    await session.execute(delete(Bill).where(Bill.order_id.in_(ids)))
    await session.execute(delete(Delivery).where(Delivery.order_id.in_(ids)))
    await session.execute(delete(OrderAbnormal).where(OrderAbnormal.order_id.in_(ids)))
    await session.execute(delete(OrderReturn).where(OrderReturn.order_id.in_(ids)))
    await session.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.resource_id.in_(ids),
            IdempotencyKey.scope.in_(["order_receive", "order_settle"]),
        )
    )
    await session.execute(delete(AuditLog).where(AuditLog.object_type == "order", AuditLog.object_id.in_(ids)))
    await session.execute(delete(Notification).where(Notification.object_type == "order", Notification.object_id.in_(ids)))
    await session.execute(delete(Alert).where(Alert.type == "tianshu_demo"))
    await session.execute(delete(IoTData).where(IoTData.device_id.like("TSDEMO%")))
    await session.execute(delete(Order).where(Order.id.in_(ids)))
    await session.commit()
    return len(ids)


async def _load_inputs(session: AsyncSession):
    canteens = (
        await session.scalars(
            select(ClientCanteen)
            .where(ClientCanteen.status == "active", ClientCanteen.lng.is_not(None), ClientCanteen.lat.is_not(None))
            .order_by(ClientCanteen.id.asc())
        )
    ).all()
    products = (
        await session.scalars(
            select(Product)
            .where(Product.is_deleted.is_(False), Product.status == "active")
            .order_by(Product.category1_id.asc(), Product.category2_id.asc(), Product.id.asc())
            .limit(160)
        )
    ).all()
    delivery = await session.scalar(select(User).where(User.role == "delivery", User.status == "active").order_by(User.id.asc()))
    suppliers = (
        await session.scalars(select(User).where(User.role == "supplier", User.status == "active").order_by(User.id.asc()))
    ).all()
    if len(canteens) < 40:
        raise RuntimeError(f"可用食堂坐标不足 40 个，当前 {len(canteens)}")
    if len(products) < 20:
        raise RuntimeError(f"可用商品不足 20 个，当前 {len(products)}")
    if not delivery:
        raise RuntimeError("缺少 active delivery 用户")
    if not suppliers:
        raise RuntimeError("缺少 active supplier 用户")
    cat_ids = {int(p.category1_id) for p in products} | {int(p.category2_id) for p in products}
    cats = (await session.scalars(select(Category).where(Category.id.in_(cat_ids)))).all()
    cat_name = {int(c.id): c.name for c in cats}
    return list(canteens), list(products), delivery, list(suppliers), cat_name


def _line_payload(product: Product, qty: int, cat_name: dict[int, str], rate: float):
    unit_price = round(float(product.reference_price) * rate, 2)
    item = {"product_id": int(product.id), "quantity": qty, "unit_price": unit_price}
    snap = {
        "product_id": int(product.id),
        "product_name": product.name,
        "unit": product.unit,
        "reference_price": float(product.reference_price),
        "category1_id": int(product.category1_id),
        "category1_name": cat_name.get(int(product.category1_id), ""),
        "category2_id": int(product.category2_id),
        "category2_name": cat_name.get(int(product.category2_id), ""),
        "order_quantity": qty,
        "order_unit_price": unit_price,
        "category_float_rate": round(rate - 1, 4),
        "standard_type": product.standard_type,
        "length_cm": float(product.length_cm) if product.length_cm is not None else None,
        "width_cm": float(product.width_cm) if product.width_cm is not None else None,
        "height_cm": float(product.height_cm) if product.height_cm is not None else None,
        "unit_weight_kg": float(product.unit_weight_kg) if product.unit_weight_kg is not None else None,
        "volume_adjust_factor": float(product.volume_adjust_factor) if product.volume_adjust_factor is not None else None,
        "spec": product.spec or "标准",
    }
    amount = round(qty * unit_price, 2)
    unit_weight = float(product.unit_weight_kg or product.weight or 1.0)
    weight = round(qty * max(unit_weight, 0.2), 3)
    if product.length_cm and product.width_cm and product.height_cm:
        volume = (
            float(product.length_cm)
            * float(product.width_cm)
            * float(product.height_cm)
            / 1_000_000
            * qty
            * float(product.volume_adjust_factor or 1)
        )
    else:
        volume = qty * 0.006
    return item, snap, amount, round(volume, 4), weight


async def _ensure_quote(session: AsyncSession, supplier_id: int, product_id: int, price: float) -> None:
    row = await session.scalar(
        select(SupplierProductQuote).where(
            SupplierProductQuote.supplier_id == supplier_id,
            SupplierProductQuote.product_id == product_id,
        )
    )
    if row:
        return
    session.add(
        SupplierProductQuote(
            supplier_id=supplier_id,
            product_id=product_id,
            quote_price=Decimal(str(round(price, 2))),
            remark="天枢演示报价",
            updated_by=supplier_id,
        )
    )


async def seed() -> dict[str, int]:
    random.seed(20260511)
    today_count = _env_int("TIANSHU_DEMO_TODAY_ORDERS", 240)
    history_days = _env_int("TIANSHU_DEMO_HISTORY_DAYS", 7)
    history_per_day = _env_int("TIANSHU_DEMO_HISTORY_PER_DAY", 36)
    today = datetime.now(TZ).date()

    async with SessionLocal() as session:
        removed = await _purge_demo_orders(session)
        canteens, products, delivery, suppliers, cat_name = await _load_inputs(session)
        canteen_pool = canteens[: max(48, min(len(canteens), 64))]
        delivery_spots = DEMO_DELIVERY_SPOTS
        seq = 1
        inserted = 0
        returns = 0
        allocations = 0
        deliveries = 0
        alerts = 0

        jobs: list[tuple[date, int, bool]] = []
        for d in range(history_days - 1, 0, -1):
            jobs.extend((today - timedelta(days=d), i, False) for i in range(history_per_day))
        jobs.extend((today, i, True) for i in range(today_count))

        for day, idx, is_today in jobs:
            canteen = canteen_pool[(idx + seq) % len(canteen_pool)]
            spot = delivery_spots[(seq - 1) % len(delivery_spots)]
            line_n = 3 + (idx % 4)
            items = []
            snaps = []
            total = 0.0
            total_vol = 0.0
            total_weight = 0.0
            picked_products = []
            for j in range(line_n):
                product = products[(idx * 7 + j * 13 + seq) % len(products)]
                qty = 8 + ((idx + j * 3) % 36)
                rate = 0.92 + ((idx + j) % 11) * 0.025
                item, snap, amount, volume, weight = _line_payload(product, qty, cat_name, rate)
                items.append(item)
                snaps.append(snap)
                picked_products.append((product, item, amount))
                total += amount
                total_vol += volume
                total_weight += weight

            if is_today:
                minute_of_day = min(22 * 60, 10 + int((idx / max(1, today_count)) * 20 * 60))
                created_at = _cn_to_utc_naive(day, minute_of_day // 60, minute_of_day % 60, idx % 60)
            else:
                minute_of_day = 6 * 60 + ((idx * 19) % (14 * 60))
                created_at = _cn_to_utc_naive(day, minute_of_day // 60, minute_of_day % 60, idx % 60)

            status_cycle = ["下单", "配货", "发货", "收货", "收货确认", "已结算"]
            status = status_cycle[(idx + seq) % len(status_cycle)]
            has_abnormal = is_today and idx % 13 == 0
            order = Order(
                order_no=_order_no(seq, day),
                client_id=int(canteen.school_client_id),
                canteen_id=int(canteen.id),
                delivery_id=int(delivery.id),
                supplier_id=None,
                items_json=items,
                items_snapshot_json=snaps,
                total_amount=Decimal(str(round(total, 2))),
                total_volume_m3=Decimal(str(round(total_vol, 4))),
                total_weight_kg=Decimal(str(round(total_weight, 3))),
                delivery_address=spot["address"],
                delivery_lng=spot["lng"],
                delivery_lat=spot["lat"],
                expected_delivery_date=day + timedelta(days=1),
                expected_delivery_slot=f"{6 + (idx % 12):02d}:00-{7 + (idx % 12):02d}:00",
                service_duration_min=20 + (idx % 4) * 10,
                status=status,
                has_abnormal=has_abnormal,
                created_at=created_at,
                updated_at=created_at + timedelta(minutes=15),
            )
            session.add(order)
            await session.flush()
            inserted += 1

            supplier = suppliers[(idx + seq) % len(suppliers)]
            for line_no, (product, item, _amount) in enumerate(picked_products, 1):
                await _ensure_quote(session, int(supplier.id), int(product.id), float(item["unit_price"]))
                session.add(
                    OrderItemAllocation(
                        order_id=int(order.id),
                        delivery_id=int(delivery.id),
                        supplier_id=int(supplier.id),
                        line_no=line_no,
                        product_id=int(product.id),
                        quantity=Decimal(str(item["quantity"])),
                        unit_price=Decimal(str(item["unit_price"])),
                        allocation_batch_no=f"TSDEMO-B{day.strftime('%m%d')}-{seq:05d}",
                        status="已出库" if status in ("发货", "收货", "收货确认", "已结算") else "已分配",
                        created_at=created_at + timedelta(minutes=3),
                        updated_at=created_at + timedelta(minutes=9),
                        created_by=int(delivery.id),
                    )
                )
                allocations += 1

            if status in ("发货", "收货", "收货确认") or (is_today and idx % 9 == 0):
                vehicle_no = f"京T{idx % 10:05d}"
                session.add(
                    Delivery(
                        order_id=int(order.id),
                        driver_name=f"天枢司机{idx % 8 + 1}",
                        vehicle_no=vehicle_no,
                        vehicle_capacity_volume_m3=18.0,
                        vehicle_capacity_weight_kg=3000.0,
                        current_lat=float(spot["lat"]) + random.uniform(-0.006, 0.006),
                        current_lng=float(spot["lng"]) + random.uniform(-0.006, 0.006),
                        route_json=[
                            {"lng": 116.4074, "lat": 39.9042, "name": "监管指挥中心"},
                            {"lng": float(spot["lng"]), "lat": float(spot["lat"]), "name": spot["name"]},
                        ],
                        departed_at=created_at + timedelta(hours=1),
                        arrived_at=created_at + timedelta(hours=2, minutes=20) if status in ("收货", "收货确认", "已结算") else None,
                        status="运输中" if status == "发货" else "已到达",
                    )
                )
                session.add(
                    IoTData(
                        device_type="gps",
                        device_id=f"TSDEMO-{vehicle_no}",
                        payload_json={
                            "lat": float(spot["lat"]) + random.uniform(-0.004, 0.004),
                            "lng": float(spot["lng"]) + random.uniform(-0.004, 0.004),
                            "order_id": int(order.id),
                            "driver": f"天枢司机{idx % 8 + 1}",
                        },
                        recorded_at=created_at + timedelta(hours=1, minutes=10),
                    )
                )
                deliveries += 1

            if has_abnormal:
                p = picked_products[0][0]
                session.add(
                    OrderAbnormal(
                        order_id=int(order.id),
                        product_id=int(p.id),
                        reason="天枢演示：价格或履约波动预警",
                        created_at=created_at + timedelta(minutes=20),
                    )
                )
                session.add(
                    Alert(
                        level="high" if idx % 2 == 0 else "medium",
                        type="tianshu_demo",
                        description=f"天枢演示预警：{canteen.name} 订单 {order.order_no} 存在履约波动",
                        status="open",
                        payload_json={"order_id": int(order.id), "order_no": order.order_no},
                        created_at=created_at + timedelta(minutes=21),
                    )
                )
                alerts += 1

            if (is_today and idx % 17 == 0) or ((not is_today) and idx % 29 == 0):
                ret = OrderReturn(
                    order_id=int(order.id),
                    return_no=f"TSDEMORET{day.strftime('%Y%m%d')}{seq:05d}",
                    source="tianshu_demo",
                    client_id=int(canteen.school_client_id),
                    status="confirmed",
                    created_at=created_at + timedelta(hours=3),
                )
                session.add(ret)
                await session.flush()
                p, item, _amount = picked_products[0]
                ordered = float(item["quantity"])
                received = round(max(0, ordered - 1 - (idx % 3)), 3)
                session.add(
                    OrderReturnLine(
                        order_return_id=int(ret.id),
                        line_index=0,
                        product_id=int(p.id),
                        product_name=p.name,
                        ordered_kg=Decimal(str(ordered)),
                        received_kg=Decimal(str(received)),
                        delta_kg=Decimal(str(round(ordered - received, 3))),
                        reason_code="quality" if idx % 2 else "lack",
                        reason_detail="天枢演示少收/质量退货",
                    )
                )
                session.add(
                    OrderReceivingLine(
                        order_id=int(order.id),
                        line_index=0,
                        status="confirmed",
                        draft_kg=Decimal(str(received)),
                        confirmed_kg=Decimal(str(received)),
                        confirmed_at=created_at + timedelta(hours=2, minutes=40),
                        confirmed_by_user_id=int(canteen.school_client_id),
                        shortage_reason_code="quality" if idx % 2 else "lack",
                        shortage_reason_detail="天枢演示少收/质量退货",
                        shortage_ordered_kg=Decimal(str(ordered)),
                        shortage_delta_kg=Decimal(str(round(ordered - received, 3))),
                    )
                )
                returns += 1

            session.add(
                OrderStatusLog(
                    order_id=int(order.id),
                    old_status="N/A",
                    new_status=status,
                    actor_user_id=0,
                    created_at=created_at,
                )
            )
            seq += 1

        await session.commit()
        return {
            "removed": removed,
            "inserted_orders": inserted,
            "allocations": allocations,
            "deliveries": deliveries,
            "returns": returns,
            "alerts": alerts,
        }


async def main() -> None:
    try:
        result = await seed()
        print(result)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
