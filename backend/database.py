import asyncio
from datetime import date, timedelta
from decimal import Decimal

import bcrypt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models import Base, Category, ClientCanteen, Contract, Order, Product, SupplierProductQuote, User
from models.billing_cycles import BillingCycle  # noqa: F401
from models.billing_statements import BillingStatement  # noqa: F401
from models.delivery_geofences import DeliveryGeofence  # noqa: F401 — 注册 metadata 供 create_all

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session


async def _ensure_orders_supplier_id_nullable() -> None:
    """订单不再强制主单供货商：supplier_id 改为可空（履约以分单表为准）。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'orders' "
                "AND COLUMN_NAME = 'supplier_id'"
            ),
            {"schema": settings.mysql_db},
        )
        row = r.first()
        if not row or (row[0] or "").upper() == "YES":
            return
        await conn.execute(text("ALTER TABLE orders MODIFY COLUMN supplier_id INT NULL"))


async def _ensure_orders_receive_signatures_json() -> None:
    """SQLAlchemy create_all 不会给已有表补列；旧库缺列会导致任意 Order 查询 500。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'orders' "
                "AND COLUMN_NAME = 'receive_signatures_json'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE orders ADD COLUMN receive_signatures_json JSON NULL "
                "COMMENT '智能秤双签'"
            )
        )


async def _ensure_quality_reports_allocation_id() -> None:
    """质检报告新增按分单维度的 allocation_id；旧库需 ALTER 加列。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'quality_reports' "
                "AND COLUMN_NAME = 'allocation_id'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE quality_reports "
                "ADD COLUMN allocation_id INT NULL COMMENT '关联订单分单行', "
                "ADD INDEX ix_quality_reports_allocation_id (allocation_id)"
            )
        )


async def _ensure_tickets_attachments_json() -> None:
    """工单新增 attachments_json，用于售后投诉图片 URL 数组；旧库需 ALTER 加列。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'tickets' "
                "AND COLUMN_NAME = 'attachments_json'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE tickets "
                "ADD COLUMN attachments_json JSON NULL COMMENT '售后投诉图片URL数组'"
            )
        )


async def _ensure_tickets_complaint_flow_columns() -> None:
    """售后投诉工单流转字段；旧库幂等 ALTER。"""
    if "mysql" not in settings.database_url:
        return
    cols = [
        ("assigned_delivery_id", "INT NULL COMMENT '派发配送商用户ID'"),
        ("delivery_response", "TEXT NULL COMMENT '配送商处理意见'"),
        ("delivery_responded_at", "DATETIME NULL COMMENT '配送商反馈时间'"),
        ("operation_resolution", "TEXT NULL COMMENT '运营结案意见'"),
        ("operation_resolved_at", "DATETIME NULL COMMENT '运营结案时间'"),
        ("flow_logs_json", "JSON NULL COMMENT '售后投诉流转日志'"),
    ]
    async with engine.begin() as conn:
        for col_name, ddl_suffix in cols:
            r = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'tickets' "
                    "AND COLUMN_NAME = :col"
                ),
                {"schema": settings.mysql_db, "col": col_name},
            )
            if (r.scalar_one() or 0) > 0:
                continue
            await conn.execute(
                text(f"ALTER TABLE tickets ADD COLUMN {col_name} {ddl_suffix}")
            )


async def _ensure_notifications_canteen_id_column() -> None:
    """notifications.canteen_id：客户端按 JWT 食堂过滤；NULL 为学校级通知。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'notifications' "
                "AND COLUMN_NAME = 'canteen_id'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE notifications ADD COLUMN canteen_id INT NULL COMMENT '采购端按食堂推送', "
                "ADD INDEX ix_notifications_canteen_id (canteen_id)"
            )
        )


async def _ensure_orders_canteen_id_column() -> None:
    """orders.canteen_id 指向 client_canteens；旧库幂等 ALTER（不设 DB 级 FK，避免历史脏数据阻塞迁移）。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'orders' "
                "AND COLUMN_NAME = 'canteen_id'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE orders ADD COLUMN canteen_id INT NULL COMMENT '客户下属食堂', "
                "ADD INDEX ix_orders_canteen_id (canteen_id)"
            )
        )


async def _ensure_billing_tables() -> None:
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _ensure_xinfadi_tables() -> None:
    """新发地行情与预测同构表；旧库启动时幂等创建。"""
    if "mysql" not in settings.database_url:
        return
    tbl = settings.xinfadi_price_table or "xinfadi_price_crawl"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS `{tbl}` (
                    `id` BIGINT NOT NULL AUTO_INCREMENT,
                    `crawl_date` DATE NOT NULL COMMENT '抓取日(查询日)',
                    `category1` VARCHAR(128) NOT NULL DEFAULT '',
                    `category2` VARCHAR(128) NOT NULL DEFAULT '',
                    `product_name` VARCHAR(256) NOT NULL DEFAULT '',
                    `min_price` VARCHAR(64) NOT NULL DEFAULT '',
                    `avg_price` VARCHAR(64) NOT NULL DEFAULT '',
                    `max_price` VARCHAR(64) NOT NULL DEFAULT '',
                    `spec` VARCHAR(512) NOT NULL DEFAULT '',
                    `origin` VARCHAR(256) NOT NULL DEFAULT '',
                    `unit` VARCHAR(64) NOT NULL DEFAULT '',
                    `publish_date` DATE NULL,
                    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (`id`),
                    KEY `idx_crawl_date` (`crawl_date`),
                    KEY `idx_crawl_product` (`crawl_date`, `product_name`(64)),
                    KEY `idx_xfd_price_product_day` (`product_name`(128), `crawl_date`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS `xinfadi_forecast_jobs` (
                    `id` BIGINT NOT NULL AUTO_INCREMENT,
                    `product_name` VARCHAR(256) NOT NULL,
                    `status` VARCHAR(24) NOT NULL DEFAULT 'idle',
                    `progress` INT NOT NULL DEFAULT 0,
                    `stage` VARCHAR(255) NOT NULL DEFAULT '',
                    `started_at` DATETIME NULL,
                    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    `finished_at` DATETIME NULL,
                    `error_msg` TEXT NULL,
                    `model_version` VARCHAR(64) NULL,
                    PRIMARY KEY (`id`),
                    UNIQUE KEY `uk_product` (`product_name`(128)),
                    KEY `idx_status` (`status`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS `xinfadi_forecast_models` (
                    `id` BIGINT NOT NULL AUTO_INCREMENT,
                    `product_name` VARCHAR(256) NOT NULL,
                    `model_kind` VARCHAR(32) NOT NULL,
                    `model_path` VARCHAR(512) NOT NULL,
                    `trained_at` DATETIME NOT NULL,
                    `sample_count` INT NOT NULL DEFAULT 0,
                    `meta_json` LONGTEXT NULL,
                    `model_version` VARCHAR(64) NOT NULL,
                    PRIMARY KEY (`id`),
                    UNIQUE KEY `uk_product_kind_version` (`product_name`(128), `model_kind`, `model_version`),
                    KEY `idx_product_kind` (`product_name`(128), `model_kind`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS `xinfadi_forecast_metrics` (
                    `product_name` VARCHAR(256) NOT NULL,
                    `metrics_json` LONGTEXT NULL,
                    `factors_json` LONGTEXT NULL,
                    `decomposition_json` LONGTEXT NULL,
                    `latest_forecast_json` LONGTEXT NULL,
                    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (`product_name`(128))
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )


async def _ensure_client_canteens_for_user(session: AsyncSession, u: User) -> None:
    """幂等：若该采购方尚无任一食堂，则仅新增一条「默认食堂」（不按单位名拆双食堂）。"""
    cid = int(u.id)
    addr = (u.address or "").strip() or "—"
    rows = (
        await session.scalars(select(ClientCanteen).where(ClientCanteen.school_client_id == cid))
    ).all()
    if not rows:
        session.add(
            ClientCanteen(
                school_client_id=cid,
                name="默认食堂",
                address=addr,
                lng=u.lng,
                lat=u.lat,
                status="active",
                sort_order=0,
            )
        )


async def seed_client_canteens_and_backfill_orders(session: AsyncSession) -> None:
    """为尚无食堂的采购方幂等补一条「默认食堂」，并回填订单 canteen_id（MySQL）。"""
    clients = (
        await session.scalars(select(User).where(User.role == "client", User.status == "active"))
    ).all()
    for u in clients:
        await _ensure_client_canteens_for_user(session, u)
    await session.commit()

    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE orders o
                INNER JOIN (
                  SELECT school_client_id, MIN(id) AS mid
                  FROM client_canteens
                  GROUP BY school_client_id
                ) t ON t.school_client_id = o.client_id
                SET o.canteen_id = t.mid
                WHERE o.canteen_id IS NULL
                """
            )
        )


async def init_db_with_retry(retries: int = 20, delay_seconds: int = 2):
    last_error = None
    for _ in range(retries):
        try:
            if settings.auto_create_schema:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            await _ensure_orders_supplier_id_nullable()
            await _ensure_orders_receive_signatures_json()
            await _ensure_quality_reports_allocation_id()
            await _ensure_tickets_attachments_json()
            await _ensure_tickets_complaint_flow_columns()
            await _ensure_orders_canteen_id_column()
            await _ensure_notifications_canteen_id_column()
            await _ensure_billing_tables()
            await _ensure_xinfadi_tables()
            if settings.seed_on_start:
                async with SessionLocal() as session:
                    await seed_data(session)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(f"数据库初始化失败: {last_error}") from last_error


async def seed_data(session: AsyncSession):
    await seed_users(session)
    await seed_client_canteens_and_backfill_orders(session)
    await seed_demo_suppliers_bind_delivery(session)
    await seed_categories_and_products(session)
    await seed_smart_split_lab_suppliers_and_quotes(session)
    await seed_demo_contracts_for_console(session)


async def seed_users(session: AsyncSession):
    # (用户名, 角色, 公司名, 地址, 经度, 纬度)；后三项可为空，便于非客户端账号
    demo_users = [
        ("client001", "client", "北京第一实验小学", "北京市朝阳区望京演示点", 116.481181, 39.989410),
        ("client002", "client", "首都师范大学附属中学", "北京市海淀区中关村大街演示点", 116.316833, 39.983960),
        ("client003", "client", "丰台第五小学（演示）", "北京市丰台区丽泽商务区演示点", 116.321, 39.866),
        ("client004", "client", "西城区演示中学", "北京市西城区金融街演示点", 116.363227, 39.914336),
        ("client005", "client", "朝阳区第二演示小学", "北京市朝阳区三里屯演示点", 116.454, 39.937),
        ("client006", "client", "通州区演示幼儿园", "北京市通州区运河东大街演示点", 116.656, 39.902),
        ("supplier001", "supplier", "新发地蔬菜批发档口", "", None, None),
        ("delivery001", "delivery", "中农食迅物流", "", None, None),
        ("factory001", "factory", "某食品厂", "", None, None),
        ("operation001", "operation", "平台运营", "", None, None),
        ("monitor001", "monitor", "北京教委督察室", "", None, None),
    ]
    for row in demo_users:
        username, role, company = row[0], row[1], row[2]
        address = row[3] if len(row) > 3 else ""
        lng = row[4] if len(row) > 4 else None
        lat = row[5] if len(row) > 5 else None
        exists = await session.scalar(select(User).where(User.username == username))
        if not exists:
            session.add(
                User(
                    username=username,
                    password_hash=bcrypt.hashpw(
                        b"demo123", bcrypt.gensalt()
                    ).decode("utf-8"),
                    role=role,
                    company_name=company,
                    contact_phone="13800000000",
                    address=address or "",
                    lng=lng,
                    lat=lat,
                    status="active",
                )
            )
    await session.commit()


async def seed_demo_suppliers_bind_delivery(session: AsyncSession):
    """多供货商演示：supplier001～003 均绑定同一配送商 delivery001（单配送商模型）。"""
    delivery = await session.scalar(
        select(User).where(User.username == "delivery001", User.role == "delivery")
    )
    if not delivery:
        return
    did = int(delivery.id)
    extras = [
        ("supplier002", "天津蔬菜配送站", 117.2, 39.13),
        ("supplier003", "河北蛋品集散中心", 116.72, 39.52),
    ]
    for username, company, lng, lat in extras:
        row = await session.scalar(select(User).where(User.username == username))
        if not row:
            session.add(
                User(
                    username=username,
                    password_hash=bcrypt.hashpw(b"demo123", bcrypt.gensalt()).decode("utf-8"),
                    role="supplier",
                    company_name=company,
                    contact_phone="13900000001",
                    address="",
                    lng=lng,
                    lat=lat,
                    status="active",
                    supplier_delivery_id=did,
                )
            )
        else:
            row.company_name = company or row.company_name
            row.supplier_delivery_id = did
            row.lng = lng
            row.lat = lat
            row.status = "active"
    for uname in ("supplier001", "supplier002", "supplier003"):
        u = await session.scalar(select(User).where(User.username == uname, User.role == "supplier"))
        if u:
            u.supplier_delivery_id = did
    await session.commit()


async def seed_demo_contracts_for_console(session: AsyncSession):
    """为 client001～client006 与 delivery001 补「已中标」且在约内的合约，便于演示控制台与下单校验。"""
    delivery = await session.scalar(
        select(User).where(User.username == "delivery001", User.role == "delivery")
    )
    if not delivery:
        return
    delivery_id = int(delivery.id)
    today = date.today()
    period_start = today - timedelta(days=60)
    period_end = today + timedelta(days=730)
    cat_rows = (
        await session.scalars(select(Category.id).where(Category.level == 1, Category.is_deleted.is_(False)))
    ).all()
    all_cat1 = [int(x) for x in cat_rows]
    if not all_cat1:
        return

    for uname in (
        "client001",
        "client002",
        "client003",
        "client004",
        "client005",
        "client006",
    ):
        client = await session.scalar(select(User).where(User.username == uname, User.role == "client"))
        if not client:
            continue
        cid = int(client.id)
        has = await session.scalar(
            select(Contract.id).where(
                Contract.client_id == cid,
                Contract.delivery_id == delivery_id,
                Contract.status == "已中标",
                Contract.period_start <= today,
                Contract.period_end >= today,
            )
        )
        if has:
            continue
        cno = f"DEMOCT{cid:05d}{delivery_id:05d}"
        exists_no = await session.scalar(select(Contract.id).where(Contract.contract_no == cno))
        if exists_no:
            continue
        session.add(
            Contract(
                contract_no=cno,
                client_id=cid,
                delivery_id=delivery_id,
                category_ids_json=all_cat1,
                period_start=period_start,
                period_end=period_end,
                status="已中标",
                price_float_rate=0.0,
                category_rates_json=[],
            )
        )
    await session.commit()


async def seed_categories_and_products(session: AsyncSession):
    # 如果已经导入正式商品（带 goods_sn），则不再注入演示分类和演示商品。
    has_official_products = await session.scalar(
        select(Product.id).where(Product.goods_sn.is_not(None), Product.is_deleted.is_(False))
    )
    if has_official_products:
        return

    category_map = {
        "蔬菜": ["叶菜类", "根茎类"],
        "水果": ["柑橘类", "浆果类"],
        "粮油": ["大米", "食用油"],
        "肉禽蛋": ["猪牛羊肉", "禽蛋"],
        "水产": ["淡水鱼", "海产品"],
        "调味品": ["基础调味", "复合调味"],
    }
    products_tpl = [
        ("示例商品A", "kg", Decimal("8.80")),
        ("示例商品B", "kg", Decimal("12.60")),
        ("示例商品C", "kg", Decimal("16.30")),
    ]

    for idx, (l1_name, l2_list) in enumerate(category_map.items(), start=1):
        level1 = await session.scalar(
            select(Category).where(Category.name == l1_name, Category.level == 1)
        )
        if not level1:
            level1 = Category(name=l1_name, level=1, parent_id=None, sort_order=idx, max_float_rate=1.0)
            session.add(level1)
            await session.flush()

        for l2_idx, l2_name in enumerate(l2_list, start=1):
            level2 = await session.scalar(
                select(Category).where(
                    Category.name == l2_name,
                    Category.level == 2,
                    Category.parent_id == level1.id,
                )
            )
            if not level2:
                level2 = Category(
                    name=l2_name, level=2, parent_id=level1.id, sort_order=l2_idx
                )
                session.add(level2)
                await session.flush()

            for p_name, unit, ref_price in products_tpl:
                final_name = f"{l2_name}{p_name[-1]}"
                exists = await session.scalar(
                    select(Product).where(
                        Product.name == final_name, Product.category2_id == level2.id
                    )
                )
                if not exists:
                    session.add(
                        Product(
                            name=final_name,
                            category1_id=level1.id,
                            category2_id=level2.id,
                            unit=unit,
                            reference_price=ref_price,
                            spec="标准",
                            origin="中国",
                            standard_type="standard",
                            status="active",
                        )
                    )
    await session.commit()


async def seed_smart_split_lab_suppliers_and_quotes(session: AsyncSession):
    """
    智能分单演示用假数据（仅测试环境）：
    - 京牧鲜：肉禽蛋域一级类商品报价（小幅波动）。
      兼容演示库「肉禽蛋」与正式库拆分的「肉」「禽」「蛋」等一级类。
    - 瀚华：排除上述肉禽蛋域及「蔬菜」「水果」一级类后的商品报价；
      偶数商品 id 极低价、奇数极高价。若无蔬菜/水果一级类，则仅排除肉禽蛋域。
    """
    delivery = await session.scalar(
        select(User).where(User.username == "delivery001", User.role == "delivery")
    )
    if not delivery:
        return
    did = int(delivery.id)
    updated_by = did

    lab_accounts: list[tuple[str, str, float, float]] = [
        ("supplier_jingmuxian", "京牧鲜冷鲜牛羊肉有限公司", 116.402, 39.918),
        ("supplier_hanhua", "瀚华副食商贸中心", 116.498, 39.872),
    ]
    for username, company, lng, lat in lab_accounts:
        row = await session.scalar(select(User).where(User.username == username))
        if not row:
            session.add(
                User(
                    username=username,
                    password_hash=bcrypt.hashpw(b"demo123", bcrypt.gensalt()).decode("utf-8"),
                    role="supplier",
                    company_name=company + "（演示）",
                    contact_phone="13900000077",
                    address="",
                    lng=lng,
                    lat=lat,
                    status="active",
                    supplier_delivery_id=did,
                )
            )
        else:
            row.role = "supplier"
            row.company_name = company + "（演示）"
            row.supplier_delivery_id = did
            row.lng = lng
            row.lat = lat
            row.status = "active"
            if not row.password_hash:
                row.password_hash = bcrypt.hashpw(b"demo123", bcrypt.gensalt()).decode("utf-8")
    await session.commit()

    meat_user = await session.scalar(select(User).where(User.username == "supplier_jingmuxian"))
    pole_user = await session.scalar(select(User).where(User.username == "supplier_hanhua"))
    if not meat_user or not pole_user:
        return

    meat_l1_names = frozenset({"肉禽蛋", "肉", "禽", "蛋"})
    veg_l1_names = frozenset({"蔬菜", "水果"})

    async def _l1_category_ids(names: frozenset[str]) -> set[int]:
        if not names:
            return set()
        rows = (
            await session.scalars(
                select(Category.id).where(
                    Category.level == 1,
                    Category.is_deleted.is_(False),
                    Category.name.in_(list(names)),
                )
            )
        ).all()
        return {int(x) for x in rows}

    meat_cat_ids = await _l1_category_ids(meat_l1_names)
    veg_cat_ids = await _l1_category_ids(veg_l1_names)

    async def upsert_quote(supplier_id: int, product_id: int, quote: float, remark: str) -> None:
        q = max(round(float(quote), 2), 0.01)
        existing = await session.scalar(
            select(SupplierProductQuote.id).where(
                SupplierProductQuote.supplier_id == supplier_id,
                SupplierProductQuote.product_id == product_id,
            )
        )
        if existing:
            ent = await session.get(SupplierProductQuote, int(existing))
            if ent:
                ent.quote_price = q
                ent.updated_by = updated_by
                ent.remark = remark
        else:
            session.add(
                SupplierProductQuote(
                    supplier_id=supplier_id,
                    product_id=product_id,
                    quote_price=q,
                    remark=remark,
                    updated_by=updated_by,
                )
            )

    if meat_cat_ids:
        meat_rows = (
            await session.scalars(
                select(Product).where(
                    Product.category1_id.in_(list(meat_cat_ids)),
                    Product.is_deleted.is_(False),
                    Product.status == "active",
                )
            )
        ).all()
        sid = int(meat_user.id)
        for p in meat_rows:
            ref = float(p.reference_price or 0) or 10.0
            quote = ref * (0.90 + (int(p.id) % 7) * 0.01)
            await upsert_quote(sid, int(p.id), quote, "演示种子：肉禽蛋专供")

    exclude_for_pole = meat_cat_ids | veg_cat_ids
    if exclude_for_pole:
        pole_rows = (
            await session.scalars(
                select(Product).where(
                    Product.is_deleted.is_(False),
                    Product.status == "active",
                    Product.category1_id.notin_(list(exclude_for_pole)),
                )
            )
        ).all()
        sid = int(pole_user.id)
        for p in pole_rows:
            ref = float(p.reference_price or 0) or 10.0
            quote = ref * 0.52 if int(p.id) % 2 == 0 else ref * 1.55
            await upsert_quote(sid, int(p.id), quote, "演示种子：非肉非菜极价交替")

    await session.commit()
