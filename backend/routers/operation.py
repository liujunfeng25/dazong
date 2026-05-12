from datetime import date, datetime, time, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, cast, Date, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import _ensure_client_canteens_for_user, get_db
from dependencies import require_role
from models import (
    Category,
    ClientCanteen,
    Contract,
    Order,
    OrderItemAllocation,
    Product,
    Ticket,
    User,
)
from schemas.operation import (
    AccountIn,
    AccountOut,
    CategoryIn,
    ClientCanteenIn,
    ClientCanteenOut,
    ProductDimensionFillIn,
    ProductIn,
    TicketIn,
    TicketResolveIn,
    TicketUpdateIn,
)
from services.audit_service import write_audit_log
from services.order_quality_missing import assert_quality_missing_ticket_can_close
from services.amap_geocode import geocode_address, search_address_tips
from services.notification_service import push_notification
from services.product_dimension_fill import fill_product_dimensions
from services.storage.minio_client import upload_product_image
from services.order_detail_aggregator import build_order_detail_extensions
from services.ticket_service import (
    complaint_phase,
    complaint_ticket_public_dict,
    submit_operation_complaint_resolution,
)
from services.ticket_state_machine import ensure_ticket_transition

from routers.contracts import _serialize_contract_row

router = APIRouter(prefix="/operation", tags=["operation"])


def _audit_meta(request: Request) -> dict:
    return {
        "trace_id": getattr(request.state, "trace_id", ""),
        "source_ip": request.client.host if request.client else "",
    }


def _normalized_name(name: str) -> str:
    return (name or "").strip()


def _normalize_account_payload(payload: AccountIn):
    payload.username = (payload.username or "").strip()
    payload.company_name = (payload.company_name or "").strip()
    payload.contact_phone = (payload.contact_phone or "").strip()
    payload.address = (payload.address or "").strip()
    payload.bind_client_id = None
    if payload.password is not None:
        p = (payload.password or "").strip()
        payload.password = p if p else None


async def _validate_category_payload(
    db: AsyncSession, payload: CategoryIn, exclude_id: Optional[int] = None
):
    payload.name = _normalized_name(payload.name)
    if not payload.name:
        raise HTTPException(400, "分类名称不能为空")
    if payload.level not in {1, 2}:
        raise HTTPException(400, "分类层级仅支持一级或二级")

    parent_id = payload.parent_id
    if payload.level == 1:
        parent_id = None
        cap = payload.max_float_rate
        if cap is None:
            cap = 1.0
        try:
            cap = float(cap)
        except (TypeError, ValueError):
            raise HTTPException(400, "最高浮动率上限格式无效")
        if cap < 0 or cap > 1:
            raise HTTPException(400, "一级分类的最高浮动率上限需在 0～1 之间（与投标上浮率小数形式一致）")
        payload.max_float_rate = cap
    else:
        if not parent_id:
            raise HTTPException(400, "二级分类必须选择所属一级分类")
        parent = await db.scalar(
            select(Category).where(
                Category.id == parent_id, Category.level == 1, Category.is_deleted.is_(False)
            )
        )
        if not parent:
            raise HTTPException(400, "所属一级分类不存在")
        payload.max_float_rate = None
    payload.parent_id = parent_id

    dup_stmt = select(Category).where(
        Category.level == payload.level,
        Category.parent_id == payload.parent_id,
        func.lower(Category.name) == payload.name.lower(),
        Category.is_deleted.is_(False),
    )
    if exclude_id is not None:
        dup_stmt = dup_stmt.where(Category.id != exclude_id)
    duplicated = await db.scalar(dup_stmt)
    if duplicated:
        raise HTTPException(400, "同一所属分类下不能有同名分类")


async def _validate_product_categories(db: AsyncSession, payload: ProductIn):
    category1 = await db.scalar(
        select(Category).where(
            Category.id == payload.category1_id, Category.level == 1, Category.is_deleted.is_(False)
        )
    )
    if not category1:
        raise HTTPException(400, "请选择有效的一级分类")

    category2 = await db.scalar(
        select(Category).where(
            Category.id == payload.category2_id, Category.level == 2, Category.is_deleted.is_(False)
        )
    )
    if not category2:
        raise HTTPException(400, "请选择有效的二级分类")
    if category2.parent_id != category1.id:
        raise HTTPException(400, "二级分类与一级分类不匹配")
    if payload.is_designated_factory:
        if not payload.designated_factory_id:
            raise HTTPException(400, "请选择指定厂家")
        factory = await db.scalar(
            select(User).where(
                User.id == payload.designated_factory_id, User.role == "factory", User.status == "active"
            )
        )
        if not factory:
            raise HTTPException(400, "指定厂家不存在或已禁用")
    else:
        payload.designated_factory_id = None


@router.get("/dashboard")
async def operation_dashboard(
    _=Depends(require_role("operation")), db: AsyncSession = Depends(get_db)
):
    today = datetime.utcnow().date()
    orders = (await db.scalars(select(Order))).all()
    today_orders = [o for o in orders if o.created_at.date() == today]
    today_gmv = sum(float(o.total_amount) for o in today_orders)
    abnormal_count = len([o for o in today_orders if o.has_abnormal])
    ticket_count = len((await db.scalars(select(Ticket))).all())
    return {
        "today_orders": len(today_orders),
        "today_gmv": today_gmv,
        "abnormal_count": abnormal_count,
        "ticket_count": ticket_count,
    }


@router.get("/categories")
async def list_categories(_=Depends(require_role("operation")), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(Category)
            .where(Category.is_deleted.is_(False))
            .order_by(Category.level, Category.sort_order, Category.id)
        )
    ).all()
    return rows


@router.post("/categories")
async def create_category(
    payload: CategoryIn,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    await _validate_category_payload(db, payload)
    row = Category(**payload.model_dump())
    db.add(row)
    await db.flush()
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="category_create",
        category="category",
        object_type="category",
        object_id=row.id,
        detail=f"新建分类 {row.name}",
        after_json={
            "name": row.name,
            "level": row.level,
            "parent_id": row.parent_id,
            "max_float_rate": row.max_float_rate,
        },
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    payload: CategoryIn,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(Category).where(Category.id == category_id, Category.is_deleted.is_(False))
    )
    if not row:
        raise HTTPException(404, "分类不存在")
    await _validate_category_payload(db, payload, exclude_id=category_id)
    before_json = {
        "name": row.name,
        "level": row.level,
        "parent_id": row.parent_id,
        "sort_order": row.sort_order,
        "max_float_rate": row.max_float_rate,
    }
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="category_update",
        category="category",
        object_type="category",
        object_id=row.id,
        detail=f"更新分类 {row.name}",
        before_json=before_json,
        after_json={
            "name": row.name,
            "level": row.level,
            "parent_id": row.parent_id,
            "sort_order": row.sort_order,
            "max_float_rate": row.max_float_rate,
        },
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(Category).where(Category.id == category_id, Category.is_deleted.is_(False))
    )
    if not row:
        raise HTTPException(404, "分类不存在")
    has_children = await db.scalar(
        select(Category.id).where(
            Category.parent_id == category_id, Category.is_deleted.is_(False)
        )
    )
    if has_children:
        raise HTTPException(400, "该分类下还有子分类，无法删除")
    used_in_product = await db.scalar(
        select(Product.id).where(
            and_(
                or_(Product.category1_id == category_id, Product.category2_id == category_id),
                Product.is_deleted.is_(False),
            )
        )
    )
    if used_in_product:
        raise HTTPException(400, "该分类已被商品使用，无法删除")
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="category_delete",
        category="category",
        object_type="category",
        object_id=row.id,
        detail=f"停用分类 {row.name}",
        before_json={
            "name": row.name,
            "level": row.level,
            "parent_id": row.parent_id,
            "is_deleted": row.is_deleted,
        },
        **_audit_meta(request),
    )
    row.is_deleted = True
    row.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "ok"}


@router.get("/products")
async def list_products(
    keyword: Optional[str] = None,
    category1_id: Optional[int] = None,
    category2_id: Optional[int] = None,
    has_factory: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    safe_page = max(1, int(page or 1))
    safe_page_size = min(max(1, int(page_size or 20)), 100)
    stmt = select(Product).where(Product.is_deleted.is_(False))
    if keyword:
        stmt = stmt.where(Product.name.like(f"%{keyword}%"))
    if category1_id:
        stmt = stmt.where(Product.category1_id == category1_id)
    if category2_id:
        stmt = stmt.where(Product.category2_id == category2_id)
    if has_factory == 1:
        stmt = stmt.where(Product.designated_factory_id.is_not(None))
    elif has_factory == 0:
        stmt = stmt.where(Product.designated_factory_id.is_(None))
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await db.scalar(total_stmt)) or 0)
    rows = (
        await db.scalars(
            stmt.order_by(Product.id.desc())
            .offset((safe_page - 1) * safe_page_size)
            .limit(safe_page_size)
        )
    ).all()
    return {
        "items": rows,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
    }


@router.post("/products")
async def create_product(
    payload: ProductIn,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    await _validate_product_categories(db, payload)
    row = Product(**payload.model_dump())
    db.add(row)
    await db.flush()
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="product_create",
        category="product",
        object_type="product",
        object_id=row.id,
        detail=f"新建商品 {row.name}",
        after_json={
            "name": row.name,
            "category1_id": row.category1_id,
            "category2_id": row.category2_id,
            "status": row.status,
        },
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/products/upload-image")
async def upload_product_image_api(
    file: UploadFile = File(...),
    _=Depends(require_role("operation")),
):
    file_url = await upload_product_image(file)
    return {"url": file_url}


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    payload: ProductIn,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    if not row:
        raise HTTPException(404, "商品不存在")
    active_statuses = {"下单", "配货", "发货", "收货"}
    active_order_exists = await db.scalar(
        select(Order.id)
        .join(OrderItemAllocation, OrderItemAllocation.order_id == Order.id)
        .where(
            OrderItemAllocation.product_id == product_id,
            Order.status.in_(active_statuses),
        )
        .limit(1)
    )
    designated_changed = (
        bool(payload.is_designated_factory) != bool(row.is_designated_factory)
        or int(payload.designated_factory_id or 0) != int(row.designated_factory_id or 0)
    )
    if designated_changed and active_order_exists:
        raise HTTPException(400, "商品正在订单流程中，禁止修改指定厂家属性")
    await _validate_product_categories(db, payload)
    before_json = {
        "name": row.name,
        "category1_id": row.category1_id,
        "category2_id": row.category2_id,
        "status": row.status,
    }
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="product_update",
        category="product",
        object_type="product",
        object_id=row.id,
        detail=f"更新商品 {row.name}",
        before_json=before_json,
        after_json={
            "name": row.name,
            "category1_id": row.category1_id,
            "category2_id": row.category2_id,
            "status": row.status,
        },
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_deleted.is_(False))
    )
    if not row:
        raise HTTPException(404, "商品不存在")
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="product_delete",
        category="product",
        object_type="product",
        object_id=row.id,
        detail=f"停用商品 {row.name}",
        before_json={"name": row.name, "is_deleted": row.is_deleted, "status": row.status},
        **_audit_meta(request),
    )
    row.is_deleted = True
    row.deleted_at = datetime.utcnow()
    row.status = "disabled"
    await db.commit()
    return {"message": "ok"}


@router.post("/products/dimensions/fill")
async def fill_product_dimensions_api(
    payload: ProductDimensionFillIn,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    if payload.batch_size < 1 or payload.batch_size > 2000:
        raise HTTPException(400, "batch_size 需在 1~2000 之间")
    result = await fill_product_dimensions(
        db=db,
        dry_run=payload.dry_run,
        only_missing=payload.only_missing,
        batch_size=payload.batch_size,
    )
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="product_dimension_fill_run",
        category="product",
        object_type="product",
        object_id=0,
        detail="商品参数批量补全（预览）" if payload.dry_run else "商品参数批量补全（正式执行）",
        after_json={
            "dry_run": payload.dry_run,
            "only_missing": payload.only_missing,
            "batch_size": payload.batch_size,
            "updated_count": result.get("updated_count", 0),
            "standard_updated_count": result.get("standard_updated_count", 0),
            "non_standard_updated_count": result.get("non_standard_updated_count", 0),
            "skipped_low_confidence_count": result.get("skipped_low_confidence_count", 0),
        },
        **_audit_meta(request),
    )
    await db.commit()
    return result


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    role: Optional[str] = None,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.id.desc())
    if role:
        stmt = stmt.where(User.role == role)
    rows = (await db.scalars(stmt)).all()
    return [AccountOut.model_validate(r) for r in rows]


@router.get("/accounts/address-tips")
async def account_address_tips(
    keywords: str,
    city: Optional[str] = "北京",
    _=Depends(require_role("operation")),
):
    items = await search_address_tips(keywords=keywords, city=city, limit=10)
    return {"items": items}


@router.post("/accounts", response_model=AccountOut)
async def create_account(
    payload: AccountIn,
    request: Request,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    _normalize_account_payload(payload)
    if not payload.username:
        raise HTTPException(400, "用户名不能为空")
    if not payload.company_name:
        raise HTTPException(400, "企业名称不能为空")
    if payload.role == "supplier":
        raise HTTPException(403, "供货商账号请在配送商端维护")
    coord = None
    if payload.role in {"delivery", "client", "factory"}:
        if not payload.address:
            role_label = "配送方" if payload.role == "delivery" else ("采购方" if payload.role == "client" else "生产方")
            raise HTTPException(400, f"{role_label}地址不能为空")
        coord = await geocode_address(payload.address)
        if not coord:
            role_label = "配送方" if payload.role == "delivery" else ("采购方" if payload.role == "client" else "生产方")
            raise HTTPException(400, f"{role_label}地址无法解析，请填写更准确地址")
    exists = await db.scalar(select(User).where(User.username == payload.username))
    if exists:
        raise HTTPException(400, "用户名已存在")
    pwd = payload.password or "demo123"
    row = User(
        username=payload.username,
        password_hash=bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        role=payload.role,
        bind_client_id=None,
        company_name=payload.company_name,
        contact_phone=payload.contact_phone,
        address=payload.address,
        lng=coord[0] if coord else None,
        lat=coord[1] if coord else None,
        status=payload.status,
    )
    db.add(row)
    await db.flush()
    if row.role == "client":
        await _ensure_client_canteens_for_user(db, row)
    await write_audit_log(
        db=db,
        actor_user_id=_.id,
        action="account_create",
        category="account",
        object_type="account",
        object_id=row.id,
        detail=f"新建账号 {row.username}",
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return AccountOut.model_validate(row)


@router.put("/accounts/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: int,
    payload: AccountIn,
    request: Request,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    _normalize_account_payload(payload)
    if not payload.company_name:
        raise HTTPException(400, "企业名称不能为空")
    row = await db.scalar(select(User).where(User.id == account_id))
    if not row:
        raise HTTPException(404, "账号不存在")
    if row.role == "supplier" or payload.role == "supplier":
        raise HTTPException(403, "供货商账号请在配送商端维护")
    coord = None
    if payload.role in {"delivery", "client", "factory"}:
        if not payload.address:
            role_label = "配送方" if payload.role == "delivery" else ("采购方" if payload.role == "client" else "生产方")
            raise HTTPException(400, f"{role_label}地址不能为空")
        coord = await geocode_address(payload.address)
        if not coord:
            role_label = "配送方" if payload.role == "delivery" else ("采购方" if payload.role == "client" else "生产方")
            raise HTTPException(400, f"{role_label}地址无法解析，请填写更准确地址")
    row.role = payload.role
    row.bind_client_id = None
    row.company_name = payload.company_name
    row.contact_phone = payload.contact_phone
    row.address = payload.address
    row.lng = coord[0] if coord else None
    row.lat = coord[1] if coord else None
    row.status = payload.status
    if payload.password:
        row.password_hash = bcrypt.hashpw(
            payload.password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
    if row.role == "client":
        await _ensure_client_canteens_for_user(db, row)
    await write_audit_log(
        db=db,
        actor_user_id=_.id,
        action="account_update",
        category="account",
        object_type="account",
        object_id=row.id,
        detail=f"更新账号 {row.username}",
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return AccountOut.model_validate(row)


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    request: Request,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(User).where(User.id == account_id))
    if not row:
        raise HTTPException(404, "账号不存在")
    if row.role == "supplier":
        raise HTTPException(403, "供货商账号请在配送商端维护")
    await write_audit_log(
        db=db,
        actor_user_id=_.id,
        action="account_delete",
        category="account",
        object_type="account",
        object_id=row.id,
        detail=f"删除账号 {row.username}",
        **_audit_meta(request),
    )
    await db.delete(row)
    await db.commit()
    return {"message": "deleted"}


@router.get("/client-canteens", response_model=list[ClientCanteenOut])
async def list_client_canteens_operation(
    school_client_id: Optional[int] = Query(None, description="采购方账号 users.id（role=client）"),
    keyword: Optional[str] = Query(
        None,
        description="模糊匹配：食堂名称、采购方单位名、登录名",
    ),
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ClientCanteen).order_by(
        ClientCanteen.school_client_id.asc(),
        ClientCanteen.sort_order.asc(),
        ClientCanteen.id.asc(),
    )
    if school_client_id is not None:
        stmt = stmt.where(ClientCanteen.school_client_id == int(school_client_id))
    kw = (keyword or "").strip()
    if kw:
        pattern = f"%{kw}%"
        stmt = stmt.join(User, User.id == ClientCanteen.school_client_id).where(
            or_(
                ClientCanteen.name.like(pattern),
                User.company_name.like(pattern),
                User.username.like(pattern),
            )
        )
    rows = (await db.scalars(stmt)).all()
    client_ids = sorted({int(r.school_client_id) for r in rows})
    clients = (
        await db.scalars(select(User).where(User.id.in_(client_ids)))
    ).all() if client_ids else []
    client_map = {int(c.id): c for c in clients}
    out = []
    for row in rows:
        client = client_map.get(int(row.school_client_id))
        client_name = (client.company_name or client.username) if client else ""
        client_username = client.username if client else ""
        address = (row.address or "").strip()
        suffix = f" - {address}" if address else ""
        out.append(
            {
                "id": row.id,
                "school_client_id": row.school_client_id,
                "name": row.name,
                "address": row.address,
                "lng": row.lng,
                "lat": row.lat,
                "status": row.status,
                "sort_order": row.sort_order,
                "created_at": row.created_at,
                "client_name": client_name,
                "client_username": client_username,
                "display_label": f"{client_name}（{client_username}） - {row.name}{suffix}",
            }
        )
    return out


@router.post("/client-canteens", response_model=ClientCanteenOut)
async def create_client_canteen_operation(
    payload: ClientCanteenIn,
    request: Request,
    op_user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    sch = await db.scalar(
        select(User).where(User.id == payload.school_client_id, User.role == "client")
    )
    if not sch:
        raise HTTPException(400, "school_client_id 须为有效的采购方账号（role=client）")
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(400, "食堂名称不能为空")
    st = (payload.status or "active").strip()
    if st not in {"active", "disabled"}:
        raise HTTPException(400, "状态仅支持 active 或 disabled")
    row = ClientCanteen(
        school_client_id=int(payload.school_client_id),
        name=name,
        address=(payload.address or "").strip(),
        lng=payload.lng,
        lat=payload.lat,
        status=st,
        sort_order=int(payload.sort_order or 0),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await write_audit_log(
        db=db,
        actor_user_id=op_user.id,
        action="client_canteen_create",
        category="account",
        object_type="client_canteen",
        object_id=row.id,
        detail=f"新建食堂 {name} school_client_id={payload.school_client_id}",
        **_audit_meta(request),
    )
    await db.commit()
    return ClientCanteenOut.model_validate(row)


@router.put("/client-canteens/{canteen_id}", response_model=ClientCanteenOut)
async def update_client_canteen_operation(
    canteen_id: int,
    payload: ClientCanteenIn,
    request: Request,
    op_user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(ClientCanteen).where(ClientCanteen.id == canteen_id))
    if not row:
        raise HTTPException(404, "食堂不存在")
    sch = await db.scalar(
        select(User).where(User.id == payload.school_client_id, User.role == "client")
    )
    if not sch:
        raise HTTPException(400, "school_client_id 须为有效的采购方账号（role=client）")
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(400, "食堂名称不能为空")
    st = (payload.status or "active").strip()
    if st not in {"active", "disabled"}:
        raise HTTPException(400, "状态仅支持 active 或 disabled")
    row.school_client_id = int(payload.school_client_id)
    row.name = name
    row.address = (payload.address or "").strip()
    row.lng = payload.lng
    row.lat = payload.lat
    row.status = st
    row.sort_order = int(payload.sort_order or 0)
    await write_audit_log(
        db=db,
        actor_user_id=op_user.id,
        action="client_canteen_update",
        category="account",
        object_type="client_canteen",
        object_id=row.id,
        detail=f"更新食堂 {name}",
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return ClientCanteenOut.model_validate(row)


@router.delete("/client-canteens/{canteen_id}")
async def delete_client_canteen_operation(
    canteen_id: int,
    request: Request,
    op_user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(ClientCanteen).where(ClientCanteen.id == canteen_id))
    if not row:
        raise HTTPException(404, "食堂不存在")
    cnt = int(await db.scalar(select(func.count(Order.id)).where(Order.canteen_id == canteen_id)) or 0)
    if cnt > 0:
        raise HTTPException(400, "该食堂已有订单记录，请改为停用（disabled）而非删除")
    nm = row.name
    await write_audit_log(
        db=db,
        actor_user_id=op_user.id,
        action="client_canteen_delete",
        category="account",
        object_type="client_canteen",
        object_id=canteen_id,
        detail=f"删除食堂 {nm}",
        **_audit_meta(request),
    )
    await db.delete(row)
    await db.commit()
    return {"message": "deleted"}


def _order_effective_delivery_date():
    """与下单校验一致：有期望配送日用语义日；否则用创建日 UTC 日期回退。"""
    return func.coalesce(Order.expected_delivery_date, cast(Order.created_at, Date))


@router.get("/contracts")
async def list_operation_contracts(
    lifecycle: Optional[str] = Query(None, description="待生效|生效中|已过期|招标中|已中标，空为全部"),
    keyword: Optional[str] = Query(None, description="合约号/客户名/地址/配送方名模糊"),
    db_status: Optional[str] = Query(None, description="定标状态（Contract.status）：招标中|已中标|已过期"),
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    stmt = select(Contract).order_by(Contract.id.desc())
    if db_status and db_status.strip():
        stmt = stmt.where(Contract.status == db_status.strip())
    rows = (await db.scalars(stmt)).all()
    for row in rows:
        if row.period_end < today and row.status != "已过期":
            row.status = "已过期"
    await db.commit()

    eff = _order_effective_delivery_date()
    join_cond = and_(
        Order.client_id == Contract.client_id,
        Order.delivery_id == Contract.delivery_id,
        eff >= Contract.period_start,
        eff <= Contract.period_end,
    )
    agg_stmt = (
        select(
            Contract.id.label("cid"),
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_amount), 0).label("order_total_amount"),
        )
        .select_from(Contract)
        .outerjoin(Order, join_cond)
        .group_by(Contract.id)
    )
    agg_rows = (await db.execute(agg_stmt)).all()
    agg_map: dict[int, tuple[int, float]] = {
        int(r[0]): (int(r[1] or 0), float(r[2] or 0)) for r in agg_rows
    }

    client_ids = sorted({int(r.client_id) for r in rows})
    delivery_ids = sorted({int(r.delivery_id) for r in rows})
    client_map: dict[int, User] = {}
    if client_ids:
        client_rows = (await db.scalars(select(User).where(User.id.in_(client_ids)))).all()
        client_map = {int(u.id): u for u in client_rows}
    delivery_map: dict[int, User] = {}
    if delivery_ids:
        delivery_rows = (await db.scalars(select(User).where(User.id.in_(delivery_ids)))).all()
        delivery_map = {int(u.id): u for u in delivery_rows}

    out: list[dict] = []
    for row in rows:
        client = client_map.get(int(row.client_id))
        delivery = delivery_map.get(int(row.delivery_id))
        item = _serialize_contract_row(row, client, today, delivery)
        oc, ot = agg_map.get(int(row.id), (0, 0.0))
        item["order_count"] = oc
        item["order_total_amount"] = ot
        out.append(item)

    if lifecycle and lifecycle.strip():
        want = lifecycle.strip()
        out = [i for i in out if i.get("lifecycle_status") == want or i.get("status") == want]

    if keyword and keyword.strip():
        k = keyword.strip().lower()
        out = [
            i
            for i in out
            if k in (i.get("contract_no") or "").lower()
            or k in (i.get("client_name") or "").lower()
            or k in (i.get("client_address") or "").lower()
            or k in (i.get("delivery_name") or "").lower()
        ]

    return out


@router.get("/contracts/{contract_id}")
async def get_operation_contract(
    contract_id: int,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(Contract).where(Contract.id == contract_id))
    if not row:
        raise HTTPException(404, "合约不存在")
    today = date.today()
    if row.period_end < today and row.status != "已过期":
        row.status = "已过期"
        await db.commit()
    client = await db.scalar(select(User).where(User.id == row.client_id))
    delivery = await db.scalar(select(User).where(User.id == row.delivery_id))
    base = _serialize_contract_row(row, client, today, delivery)
    oc, ot = (0, 0.0)
    eff = _order_effective_delivery_date()
    r = await db.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
        .select_from(Order)
        .where(
            Order.client_id == row.client_id,
            Order.delivery_id == row.delivery_id,
            eff >= row.period_start,
            eff <= row.period_end,
        )
    )
    one = r.first()
    if one:
        oc, ot = int(one[0] or 0), float(one[1] or 0)
    base["order_count"] = oc
    base["order_total_amount"] = ot
    return base


@router.get("/contracts/{contract_id}/orders")
async def list_operation_contract_orders(
    contract_id: int,
    status: Optional[str] = None,
    order_no: Optional[str] = None,
    expected_date_start: Optional[str] = None,
    expected_date_end: Optional[str] = None,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    c = await db.scalar(select(Contract).where(Contract.id == contract_id))
    if not c:
        raise HTTPException(404, "合约不存在")
    eff = _order_effective_delivery_date()
    stmt = (
        select(Order)
        .where(
            Order.client_id == c.client_id,
            Order.delivery_id == c.delivery_id,
            eff >= c.period_start,
            eff <= c.period_end,
        )
        .order_by(Order.id.desc())
    )
    if status:
        stmt = stmt.where(Order.status == status)
    if order_no and order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))
    if expected_date_start and expected_date_start.strip():
        try:
            ds = date.fromisoformat(expected_date_start.strip())
        except ValueError:
            raise HTTPException(400, "expected_date_start 格式须为 YYYY-MM-DD")
        stmt = stmt.where(eff >= ds)
    if expected_date_end and expected_date_end.strip():
        try:
            de = date.fromisoformat(expected_date_end.strip())
        except ValueError:
            raise HTTPException(400, "expected_date_end 格式须为 YYYY-MM-DD")
        stmt = stmt.where(eff <= de)
    orders = (await db.scalars(stmt)).all()
    return [
        {
            "id": o.id,
            "order_no": o.order_no,
            "status": o.status,
            "total_amount": float(o.total_amount or 0),
            "expected_delivery_date": o.expected_delivery_date,
            "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            "client_id": o.client_id,
            "delivery_id": o.delivery_id,
            "has_abnormal": bool(o.has_abnormal),
        }
        for o in orders
    ]


@router.get("/orders")
async def list_operation_orders(
    status: Optional[str] = None,
    order_no: Optional[str] = None,
    created_date_start: Optional[str] = None,
    created_date_end: Optional[str] = None,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
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

    stmt = select(Order).order_by(Order.id.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    if order_no and order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))
    stmt = stmt.where(Order.created_at >= start_dt, Order.created_at < end_dt)
    return (await db.scalars(stmt)).all()


@router.get("/orders/{order_id}")
async def operation_order_detail(
    order_id: int,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    """运营端订单详情聚合：主体 + 合约 + 上浮 + 明细 + 分单 + 质检 + 收货 + 时间线 + 异常旗标。"""
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(404, "订单不存在")

    payload = jsonable_encoder(order)
    ext = await build_order_detail_extensions(db, order, viewer_role="operation")
    payload.update(ext)
    return payload


@router.get("/tickets")
async def list_tickets(
    status: Optional[str] = None,
    type: Optional[str] = None,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Ticket).order_by(Ticket.id.desc())
    if status:
        stmt = stmt.where(Ticket.status == status)
    if type:
        stmt = stmt.where(Ticket.type == type)
    rows = (await db.scalars(stmt)).all()
    if not rows:
        return []
    order_ids = sorted({int(r.order_id) for r in rows})
    user_ids = sorted({int(r.created_by) for r in rows})
    order_map: dict[int, str] = {}
    if order_ids:
        order_rows = (
            await db.execute(select(Order.id, Order.order_no).where(Order.id.in_(order_ids)))
        ).all()
        order_map = {int(o[0]): o[1] for o in order_rows}
    user_map: dict[int, str] = {}
    if user_ids:
        urows = (
            await db.execute(
                select(User.id, User.company_name, User.username).where(User.id.in_(user_ids))
            )
        ).all()
        user_map = {int(u[0]): (u[1] or u[2] or f"#{u[0]}") for u in urows}
    assign_ids = sorted(
        {
            int(getattr(r, "assigned_delivery_id") or 0)
            for r in rows
            if getattr(r, "assigned_delivery_id", None) is not None
        }
    )
    assign_name_map: dict[int, str] = {}
    if assign_ids:
        arows = (
            await db.execute(
                select(User.id, User.company_name, User.username).where(User.id.in_(assign_ids))
            )
        ).all()
        assign_name_map = {int(a[0]): (a[1] or a[2] or f"#{a[0]}") for a in arows}
    payload = []
    for r in rows:
        entry = {
            "id": int(r.id),
            "order_id": int(r.order_id),
            "order_no": order_map.get(int(r.order_id), ""),
            "type": r.type,
            "description": r.description,
            "status": r.status,
            "attachments_json": list(r.attachments_json or []),
            "created_by": int(r.created_by),
            "created_by_name": user_map.get(int(r.created_by), ""),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        if r.type == "售后投诉":
            aid = getattr(r, "assigned_delivery_id", None)
            logs = getattr(r, "flow_logs_json", None)
            entry["phase"] = complaint_phase(r)
            entry["assigned_delivery_id"] = int(aid) if aid is not None else None
            entry["assigned_delivery_name"] = assign_name_map.get(int(aid), "") if aid is not None else ""
            entry["delivery_response"] = getattr(r, "delivery_response", None)
            entry["delivery_responded_at"] = (
                r.delivery_responded_at.isoformat() if getattr(r, "delivery_responded_at", None) else None
            )
            entry["operation_resolution"] = getattr(r, "operation_resolution", None)
            entry["operation_resolved_at"] = (
                r.operation_resolved_at.isoformat() if getattr(r, "operation_resolved_at", None) else None
            )
            entry["flow_logs_json"] = list(logs) if isinstance(logs, list) else []
        payload.append(entry)
    return payload


@router.post("/tickets")
async def create_ticket(
    payload: TicketIn,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == payload.order_id))
    if not order:
        raise HTTPException(404, "订单不存在")
    row = Ticket(
        order_id=payload.order_id,
        type=payload.type,
        description=payload.description,
        status="待处理",
        created_by=user.id,
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="ticket_create",
        category="ticket",
        object_type="ticket",
        object_id=0,
        detail=f"order_id={payload.order_id}",
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: int,
    payload: TicketUpdateIn,
    request: Request,
    _=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(Ticket).where(Ticket.id == ticket_id))
    if not row:
        raise HTTPException(404, "工单不存在")
    if row.type == "售后投诉" and payload.status == "已关闭":
        raise HTTPException(
            400,
            "售后投诉工单请使用审核结案接口 POST /operation/tickets/{id}/resolve，并填写运营结案意见",
        )
    await assert_quality_missing_ticket_can_close(db, row, payload.status)
    ensure_ticket_transition(row.status, payload.status)
    old_status = row.status
    row.status = payload.status
    row.updated_at = datetime.utcnow()
    await write_audit_log(
        db=db,
        actor_user_id=_.id,
        action="ticket_status_change",
        category="ticket",
        object_type="ticket",
        object_id=row.id,
        detail=f"{old_status}->{payload.status}",
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/tickets/{ticket_id}/resolve")
async def resolve_complaint_ticket(
    ticket_id: int,
    payload: TicketResolveIn,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    """售后投诉：运营在配送商反馈后填写结案意见并关闭工单。"""
    row = await db.scalar(select(Ticket).where(Ticket.id == ticket_id))
    if not row:
        raise HTTPException(404, "工单不存在")
    if row.type != "售后投诉":
        raise HTTPException(400, "仅售后投诉工单可使用本接口结案")
    await submit_operation_complaint_resolution(db, row, user, payload.resolution)
    order = await db.scalar(select(Order).where(Order.id == row.order_id))
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="ticket_complaint_resolve",
        category="ticket",
        object_type="ticket",
        object_id=row.id,
        detail="运营结案售后投诉",
        **_audit_meta(request),
    )
    if order:
        await push_notification(
            db=db,
            role="client",
            event_type="ticket_complaint",
            title=f"售后投诉已结案：{order.order_no}",
            content=(payload.resolution or "")[:300],
            route=f"/client/orders/{order.id}",
            object_type="ticket",
            object_id=int(row.id),
            target_user_ids=[int(order.client_id)],
            canteen_id=int(order.canteen_id) if order.canteen_id is not None else None,
        )
        await push_notification(
            db=db,
            role="delivery",
            event_type="ticket_complaint",
            title=f"售后投诉已结案：{order.order_no}",
            content=(payload.resolution or "")[:300],
            route=f"/delivery/orders/{order.id}",
            object_type="ticket",
            object_id=int(row.id),
            target_user_ids=[int(order.delivery_id)],
        )
    await db.commit()
    await db.refresh(row)
    return complaint_ticket_public_dict(row)


@router.delete("/tickets/{ticket_id}")
async def delete_ticket(
    ticket_id: int,
    request: Request,
    user=Depends(require_role("operation")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(Ticket).where(Ticket.id == ticket_id))
    if not row:
        raise HTTPException(404, "工单不存在")
    await db.delete(row)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="ticket_delete",
        category="ticket",
        object_type="ticket",
        object_id=ticket_id,
        detail="deleted",
        **_audit_meta(request),
    )
    await db.commit()
    return {"message": "deleted"}
