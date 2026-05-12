from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models import Category, Contract, Order, OrderItemAllocation, Product, SupplierProductQuote, User
from services.notification_service import push_notification

router = APIRouter(prefix="/supplier", tags=["supplier"])


def _supplier_view_status(order_status: str, my_alloc_total: int, my_alloc_shipped: int) -> tuple[str, str]:
    if str(order_status) == "取消":
        return "cancelled", "已取消"
    if my_alloc_total > 0:
        if my_alloc_shipped >= my_alloc_total:
            if str(order_status) in {"收货", "收货确认", "已结算"}:
                return "completed", "已完成"
            return "shipped", "已发货"
        return "pending_ship", "待发货"
    # 历史无分单订单兜底
    if str(order_status) in {"下单", "配货"}:
        return "pending_ship", "待发货"
    if str(order_status) == "发货":
        return "shipped", "已发货"
    if str(order_status) in {"收货", "收货确认", "已结算"}:
        return "completed", "已完成"
    return "pending_ship", "待发货"


async def _signed_contract_for_supplier(
    db: AsyncSession, delivery_id: int
) -> Optional[Contract]:
    today = date.today()
    return await db.scalar(
        select(Contract)
        .where(
            Contract.delivery_id == delivery_id,
            Contract.status == "已中标",
            Contract.period_start <= today,
            Contract.period_end >= today,
        )
        .order_by(Contract.id.desc())
    )


def _contract_rate_map_and_fallback(contract: Optional[Contract]) -> tuple[dict[int, float], float]:
    if not contract:
        return {}, 0.0
    rate_map: dict[int, float] = {}
    for item in contract.category_rates_json or []:
        if item.get("category_id") is not None:
            rate_map[int(item["category_id"])] = float(item.get("float_rate", 0))
    return rate_map, float(contract.price_float_rate or 0)


def _unit_price_with_contract_rate(
    reference_price: float, category1_id: Optional[int], rate_map: dict[int, float], fallback_rate: float
) -> Optional[float]:
    if category1_id is None:
        return None
    rate = rate_map.get(int(category1_id), fallback_rate)
    return float(
        round(Decimal(str(reference_price)) * (Decimal("1") + Decimal(str(rate))), 2)
    )


def _product_thumb_url(row: Product) -> Optional[str]:
    if row.logo:
        return row.logo
    imgs = row.image_list_json or []
    if isinstance(imgs, list) and len(imgs) > 0 and isinstance(imgs[0], str):
        return imgs[0]
    return None


@router.get("/home")
async def supplier_home(_=Depends(require_role("supplier"))):
    return {"message": "ok", "module": "supplier"}


@router.get("/orders")
async def supplier_orders(
    status: Optional[str] = None,
    order_no: Optional[str] = None,
    created_date_start: Optional[str] = None,
    created_date_end: Optional[str] = None,
    user=Depends(require_role("supplier")),
    db: AsyncSession = Depends(get_db),
):
    """
    配送分包订单：客户向配送商下单后，由配送商将订单行分包给多个供货商履约。
    本接口仅返回「分单表中有行分给本供货商」的订单；未分包到本户的不出现。
    列表不返回整单商品明细（避免看到他户分包行）；详情见 GET /orders/{id}。
    """
    allocated_to_me = Order.id.in_(
        select(OrderItemAllocation.order_id)
        .where(OrderItemAllocation.supplier_id == user.id)
        .distinct()
    )

    today = datetime.utcnow().date()
    try:
        start_date = date.fromisoformat(created_date_start) if created_date_start else today
        end_date = date.fromisoformat(created_date_end) if created_date_end else today
    except ValueError:
        raise HTTPException(400, "时间筛选格式错误，需为 YYYY-MM-DD")
    if end_date < start_date:
        raise HTTPException(400, "结束日期不能早于开始日期")
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min)

    stmt = (
        select(Order)
        .where(allocated_to_me)
        .where(Order.created_at >= start_dt, Order.created_at < end_dt)
        .order_by(Order.id.desc())
    )
    if order_no and order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))
    orders = (await db.scalars(stmt)).all()
    if not orders:
        return []

    order_ids = [o.id for o in orders]
    sum_rows = (
        await db.execute(
            select(
                OrderItemAllocation.order_id,
                func.coalesce(
                    func.sum(OrderItemAllocation.quantity * OrderItemAllocation.unit_price),
                    0,
                ),
            )
            .where(
                OrderItemAllocation.order_id.in_(order_ids),
                OrderItemAllocation.supplier_id == user.id,
            )
            .group_by(OrderItemAllocation.order_id)
        )
    ).all()
    portion_by_order = {int(r[0]): float(r[1] or 0) for r in sum_rows}
    alloc_progress_rows = (
        await db.execute(
            select(
                OrderItemAllocation.order_id,
                func.count(OrderItemAllocation.id),
                func.sum(
                    case((OrderItemAllocation.status == "已出库", 1), else_=0)
                ),
            )
            .where(
                OrderItemAllocation.order_id.in_(order_ids),
                OrderItemAllocation.supplier_id == user.id,
            )
            .group_by(OrderItemAllocation.order_id)
        )
    ).all()
    alloc_progress_map = {
        int(order_id): {
            "total": int(total or 0),
            "shipped": int(shipped or 0),
        }
        for order_id, total, shipped in alloc_progress_rows
    }

    uid_set = {int(o.client_id) for o in orders} | {int(o.delivery_id) for o in orders}
    user_map: dict[int, User] = {}
    if uid_set:
        urows = (await db.scalars(select(User).where(User.id.in_(list(uid_set))))).all()
        user_map = {int(u.id): u for u in urows}

    out = []
    for o in orders:
        portion = float(portion_by_order.get(o.id) or 0)
        supply_amt = round(portion, 2)
        progress = alloc_progress_map.get(int(o.id), {"total": 0, "shipped": 0})
        supplier_status, supplier_status_text = _supplier_view_status(
            str(o.status or ""),
            int(progress["total"]),
            int(progress["shipped"]),
        )
        if status and supplier_status != str(status):
            continue
        cu = user_map.get(int(o.client_id))
        du = user_map.get(int(o.delivery_id))
        out.append(
            {
                "id": o.id,
                "order_no": o.order_no,
                "client_name": (cu.company_name or cu.username if cu else "") or "",
                "delivery_name": (du.company_name or du.username if du else "") or "",
                "total_amount": supply_amt,
                "supply_portion_amount": supply_amt,
                "has_delivery_allocation": True,
                "expected_delivery_date": o.expected_delivery_date.isoformat() if o.expected_delivery_date else None,
                "expected_delivery_slot": o.expected_delivery_slot,
                "delivery_address": o.delivery_address,
                "status": o.status,
                "supplier_status": supplier_status,
                "supplier_status_text": supplier_status_text,
                "has_abnormal": o.has_abnormal,
                "updated_at": o.updated_at,
                "created_at": o.created_at,
            }
        )
    return out


@router.get("/product-quotes")
async def supplier_product_quotes(
    keyword: Optional[str] = None,
    quote_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    user=Depends(require_role("supplier")),
    db: AsyncSession = Depends(get_db),
):
    safe_page = max(int(page or 1), 1)
    safe_size = min(max(int(page_size or 20), 1), 100)
    offset = (safe_page - 1) * safe_size

    qs = (quote_status or "all").strip().lower()
    if qs not in ("all", "quoted", "unquoted"):
        qs = "all"

    where = [
        Product.is_deleted.is_(False),
        Product.status == "active",
        Product.is_designated_factory.is_(False),
    ]
    if keyword and keyword.strip():
        kw = keyword.strip()
        where.append(or_(Product.name.like(f"%{kw}%"), Product.goods_sn.like(f"%{kw}%")))

    quote_exists = exists(
        select(SupplierProductQuote.id).where(
            SupplierProductQuote.supplier_id == user.id,
            SupplierProductQuote.product_id == Product.id,
        )
    )
    if qs == "quoted":
        where.append(quote_exists)
    elif qs == "unquoted":
        where.append(~quote_exists)

    total = int(await db.scalar(select(func.count(Product.id)).where(*where)) or 0)
    products = (
        await db.scalars(
            select(Product).where(*where).order_by(Product.id.desc()).offset(offset).limit(safe_size)
        )
    ).all()

    product_ids = [p.id for p in products]
    quote_map = {}
    if product_ids:
        quotes = (
            await db.scalars(
                select(SupplierProductQuote).where(
                    SupplierProductQuote.supplier_id == user.id,
                    SupplierProductQuote.product_id.in_(product_ids),
                )
            )
        ).all()
        quote_map = {q.product_id: q for q in quotes}

    category_ids = {int(p.category1_id) for p in products if p.category1_id is not None}
    category_map: dict[int, str] = {}
    if category_ids:
        categories = (await db.scalars(select(Category).where(Category.id.in_(category_ids)))).all()
        category_map = {int(c.id): c.name for c in categories}

    pricing_status = "ok"
    signed_contract = None
    rate_map: dict[int, float] = {}
    fallback_rate = 0.0
    if user.supplier_delivery_id:
        signed_contract = await _signed_contract_for_supplier(db, int(user.supplier_delivery_id))
    if signed_contract:
        rate_map, fallback_rate = _contract_rate_map_and_fallback(signed_contract)
    else:
        pricing_status = "no_active_contract"

    items = []
    for row in products:
        ref = float(row.reference_price or 0)
        category1_id = int(row.category1_id) if row.category1_id is not None else None
        q = quote_map.get(row.id)
        category_rate = None if pricing_status != "ok" else rate_map.get(category1_id, fallback_rate)
        floating_price = (
            None
            if pricing_status != "ok"
            else _unit_price_with_contract_rate(ref, category1_id, rate_map, fallback_rate)
        )
        items.append(
            {
                "product_id": row.id,
                "goods_sn": row.goods_sn or "",
                "product_name": row.name,
                "unit": row.unit,
                "logo": row.logo,
                "thumb_url": _product_thumb_url(row),
                "category1_id": row.category1_id,
                "category1_name": category_map.get(category1_id or 0, ""),
                "reference_price": ref,
                "category_float_rate": category_rate,
                "floating_price": floating_price,
                "my_quote_price": float(q.quote_price) if q else None,
                "remark": q.remark if q else "",
            }
        )

    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_size,
        "pricing_status": pricing_status,
        "contract_info": {
            "contract_id": signed_contract.id if signed_contract else None,
            "delivery_id": signed_contract.delivery_id if signed_contract else user.supplier_delivery_id,
            "period_start": str(signed_contract.period_start) if signed_contract else None,
            "period_end": str(signed_contract.period_end) if signed_contract else None,
            "fallback_rate": fallback_rate if signed_contract else None,
        },
    }


@router.put("/product-quotes")
async def save_supplier_product_quotes(
    payload: dict,
    user=Depends(require_role("supplier")),
    db: AsyncSession = Depends(get_db),
):
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) == 0:
        raise HTTPException(400, "请提供要保存的报价项")

    product_ids: list[int] = []
    normalized = []
    for row in items:
        if not isinstance(row, dict):
            raise HTTPException(400, "报价项格式错误")
        product_id = int(row.get("product_id") or 0)
        quote_price = row.get("quote_price")
        if product_id <= 0:
            raise HTTPException(400, "商品ID非法")
        if quote_price is None:
            raise HTTPException(400, "报价不能为空")
        try:
            quote_price_num = round(float(quote_price), 2)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, "报价必须为数字") from exc
        if quote_price_num <= 0:
            raise HTTPException(400, "报价必须大于0")
        normalized.append(
            {
                "product_id": product_id,
                "quote_price": quote_price_num,
                "remark": str(row.get("remark") or "").strip()[:500],
            }
        )
        product_ids.append(product_id)

    valid_rows = (
        await db.execute(
            select(Product.id, Product.is_designated_factory).where(
                Product.id.in_(product_ids),
                Product.is_deleted.is_(False),
                Product.status == "active",
            )
        )
    ).all()
    valid_map = {int(pid): bool(is_designated) for pid, is_designated in valid_rows}
    if len(valid_map) != len(set(product_ids)):
        raise HTTPException(400, "存在无效或已下架商品")
    designated_ids = [pid for pid, is_designated in valid_map.items() if is_designated]
    if designated_ids:
        raise HTTPException(400, f"指定厂家商品不允许供货商报价：{', '.join(str(i) for i in designated_ids)}")

    exists = (
        await db.scalars(
            select(SupplierProductQuote).where(
                SupplierProductQuote.supplier_id == user.id,
                SupplierProductQuote.product_id.in_(list(set(product_ids))),
            )
        )
    ).all()
    exists_map = {row.product_id: row for row in exists}

    created = 0
    updated = 0
    for row in normalized:
        target = exists_map.get(row["product_id"])
        if target:
            target.quote_price = row["quote_price"]
            target.remark = row["remark"]
            target.updated_by = user.id
            updated += 1
        else:
            db.add(
                SupplierProductQuote(
                    supplier_id=user.id,
                    product_id=row["product_id"],
                    quote_price=row["quote_price"],
                    remark=row["remark"],
                    updated_by=user.id,
                )
            )
            created += 1

    changed_count = created + updated
    if changed_count > 0 and user.supplier_delivery_id:
        delivery_user = await db.scalar(
            select(User).where(
                User.id == int(user.supplier_delivery_id),
                User.role == "delivery",
                User.status == "active",
            )
        )
        if delivery_user:
            supplier_name = user.company_name or user.username or f"供货商#{user.id}"
            await push_notification(
                db=db,
                role="delivery",
                event_type="supplier_quote_updated",
                title="供货商报价已更新",
                content=f"{supplier_name} 更新了 {changed_count} 条商品报价，请及时查看。",
                route="/delivery/suppliers",
                object_type="supplier",
                object_id=user.id,
                target_user_ids=[delivery_user.id],
            )
    await db.commit()
    return {"message": "保存成功", "created": created, "updated": updated}
