from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Category, Contract, Order, OrderAbnormal, Product, Ticket


async def detect_abnormal_items(
    db: AsyncSession, client_id: int, delivery_id: int, items: list[dict]
) -> list[dict]:
    abnormal_items: list[dict] = []
    today = date.today()
    for item in items:
        product = await db.scalar(select(Product).where(Product.id == item["product_id"]))
        if not product:
            abnormal_items.append(
                {
                    "product_id": item["product_id"],
                    "product_name": "未知商品",
                    "reason": "商品不存在",
                }
            )
            continue
        contract = await db.scalar(
            select(Contract).where(
                and_(
                    Contract.client_id == client_id,
                    Contract.delivery_id == delivery_id,
                    Contract.status == "已中标",
                    Contract.period_start <= today,
                    Contract.period_end >= today,
                )
            )
        )
        valid = bool(contract and product.category1_id in (contract.category_ids_json or []))
        if not valid:
            abnormal_items.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "reason": "商品一级分类不在有效合约范围内",
                }
            )
    return abnormal_items


def calc_total_amount(items: list[dict]) -> Decimal:
    total = Decimal("0")
    for item in items:
        total += Decimal(str(item["unit_price"])) * Decimal(str(item["quantity"]))
    return total


async def create_abnormal_records_and_ticket(
    db: AsyncSession, order: Order, abnormal_items: list[dict], created_by: int
):
    for abnormal in abnormal_items:
        db.add(
            OrderAbnormal(
                order_id=order.id,
                product_id=abnormal["product_id"],
                reason=abnormal["reason"],
            )
        )
    db.add(
        Ticket(
            order_id=order.id,
            type="异常订单",
            description=f"订单 {order.order_no} 存在合约范围异常商品",
            status="待处理",
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
