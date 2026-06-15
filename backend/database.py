import asyncio
from datetime import date, timedelta
from decimal import Decimal

import bcrypt
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models import Base, Category, ClientCanteen, Contract, MonitorBroadcast, Order, Product, SupplierProductQuote, User  # noqa: F401
from models.billing_cycles import BillingCycle  # noqa: F401
from models.billing_statements import BillingStatement  # noqa: F401
from models.delivery_geofences import DeliveryGeofence  # noqa: F401 — 注册 metadata 供 create_all

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=40,        # 总上限 60：监管端单页会并发 ~10+ 个聚合请求，原 25 在多页/多 tab 下易被打满
    pool_recycle=1800,      # 30 分钟回收，避免长连接被 MySQL 端 wait_timeout 掐断后残留
    pool_timeout=30,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# 只读引擎：供 AI 的 run_sql 工具使用。配置了只读账号时，DB 层授权即只授 SELECT；
# 未配置则复用主账号 DSN，仅靠应用层 SELECT-only 校验兜底。小连接池，避免 AI 查询挤占主池。
readonly_engine = create_async_engine(
    settings.readonly_database_url,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
)
ReadOnlySession = async_sessionmaker(readonly_engine, class_=AsyncSession, expire_on_commit=False)


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


async def _ensure_billing_statements_reconciliation_id() -> None:
    """对账单（reconciliation_statements）下挂明细：给 billing_statements 补 reconciliation_id 列。
    create_all 不会给已有表补列，旧库需幂等 ALTER。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'billing_statements' "
                "AND COLUMN_NAME = 'reconciliation_id'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE billing_statements "
                "ADD COLUMN reconciliation_id INT NULL COMMENT '所属对账单', "
                "ADD INDEX ix_billing_statements_reconciliation_id (reconciliation_id)"
            )
        )


async def _ensure_billing_cycles_granularity_columns() -> None:
    """billing_cycles 颗粒化两列：canteen_id（client↔delivery 派生规则细到食堂）、
    is_customized（运营定制后不再跟随全局规则）。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'billing_cycles' "
                "AND COLUMN_NAME = 'canteen_id'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE billing_cycles "
                "ADD COLUMN canteen_id INT NULL COMMENT '账期规则所属食堂（client_delivery 腿）', "
                "ADD COLUMN is_customized TINYINT(1) NOT NULL DEFAULT 0 COMMENT '运营已定制，不跟随全局', "
                "ADD INDEX ix_billing_cycles_canteen_id (canteen_id)"
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


async def _ensure_quality_reports_attachments_json() -> None:
    """质检报告多图：有序 URL 列表（除首张外或整表多图扩展）；旧库幂等 ALTER。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'quality_reports' "
                "AND COLUMN_NAME = 'attachments_json'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE quality_reports "
                "ADD COLUMN attachments_json JSON NULL COMMENT '质检多图URL列表（与file_url组合见业务层）'"
            )
        )


async def _ensure_categories_image_url() -> None:
    """分类图片：create_all 不会改已有 categories 表，启动前补列。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'categories' "
                "AND COLUMN_NAME = 'image_url'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE categories "
                "ADD COLUMN image_url VARCHAR(512) NULL COMMENT '分类图片：URL 或 emoji: token'"
            )
        )


async def _ensure_products_quality_report_mode() -> None:
    """商品质检模式：create_all 不会改已有 products 表，启动种子前必须先补列。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'products' "
                "AND COLUMN_NAME = 'quality_report_mode'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(
            text(
                "ALTER TABLE products "
                "ADD COLUMN quality_report_mode ENUM('batch','periodic') "
                "NOT NULL DEFAULT 'batch' COMMENT '质检报告模式：批次/周期'"
            )
        )


async def _ensure_periodic_quality_report_version_columns() -> None:
    """周期报告版本字段与状态枚举；兼容未主动执行 Alembic 的开发库。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'periodic_quality_reports'"
            ),
            {"schema": settings.mysql_db},
        )
        columns = {str(row[0]) for row in result.all()}
        if not columns:
            return
        if "revision_of_id" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE periodic_quality_reports "
                    "ADD COLUMN revision_of_id INT NULL, "
                    "ADD INDEX ix_periodic_quality_reports_revision_of_id (revision_of_id), "
                    "ADD CONSTRAINT fk_pqr_revision_of "
                    "FOREIGN KEY (revision_of_id) REFERENCES periodic_quality_reports(id)"
                )
            )
        if "version" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE periodic_quality_reports "
                    "ADD COLUMN version INT NOT NULL DEFAULT 1"
                )
            )
        await conn.execute(
            text(
                "ALTER TABLE periodic_quality_reports "
                "MODIFY COLUMN status ENUM('待审核','已通过','已驳回','已失效') "
                "NOT NULL DEFAULT '待审核'"
            )
        )
        index_result = await conn.execute(
            text(
                "SELECT INDEX_NAME FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'periodic_quality_reports'"
            ),
            {"schema": settings.mysql_db},
        )
        indexes = {str(row[0]) for row in index_result.all()}
        if "ix_periodic_report_pair_status_period" not in indexes:
            await conn.execute(
                text(
                    "CREATE INDEX ix_periodic_report_pair_status_period "
                    "ON periodic_quality_reports "
                    "(provider_id, product_id, status, valid_from, valid_to)"
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


async def _ensure_tickets_billing_columns() -> None:
    """账务超期工单允许绑定 billing_statement，并兼容历史订单工单。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'tickets' "
                "AND COLUMN_NAME = 'billing_statement_id'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) == 0:
            await conn.execute(
                text(
                    "ALTER TABLE tickets ADD COLUMN billing_statement_id INT NULL, "
                    "ADD INDEX ix_tickets_billing_statement_id (billing_statement_id), "
                    "ADD CONSTRAINT fk_tickets_billing_statement_id "
                    "FOREIGN KEY (billing_statement_id) REFERENCES billing_statements(id)"
                )
            )
        r = await conn.execute(
            text(
                "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'tickets' "
                "AND COLUMN_NAME = 'order_id'"
            ),
            {"schema": settings.mysql_db},
        )
        row = r.first()
        if row and (row[0] or "").upper() != "YES":
            await conn.execute(text("ALTER TABLE tickets MODIFY COLUMN order_id INT NULL"))
        await conn.execute(
            text(
                "ALTER TABLE tickets MODIFY COLUMN type "
                "ENUM('异常订单','售后投诉','配送异常','账务异常') NOT NULL"
            )
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


async def _ensure_notifications_read_at_column() -> None:
    """notifications.read_at：用于监管广播已读回执。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'notifications' "
                "AND COLUMN_NAME = 'read_at'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) > 0:
            return
        await conn.execute(text("ALTER TABLE notifications ADD COLUMN read_at DATETIME NULL COMMENT '已读时间'"))


async def _ensure_billing_notification_routes() -> None:
    """历史账单通知曾写入 /bills 且文案过于笼统；启动时按角色和账单信息回填。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE notifications "
                "SET route = CASE role "
                "WHEN 'client' THEN '/client/bills' "
                "WHEN 'delivery' THEN '/delivery/bills' "
                "WHEN 'supplier' THEN '/supplier/bills' "
                "WHEN 'factory' THEN '/factory/bills' "
                "ELSE '/operation/billing-overview' END "
                "WHERE route = '/bills' "
                "AND event_type IN ("
                "'billing','billing_confirmed','billing_confirmed_by_peer',"
                "'billing_settled','billing_settled_by_peer',"
                "'bill_created','bill_settled','bill_update'"
                ")"
            )
        )
        await conn.execute(
            text(
                "UPDATE notifications n "
                "JOIN billing_statements bs ON n.object_type = 'billing_statement' AND n.object_id = bs.id "
                "SET n.title = CASE "
                "WHEN n.event_type = 'billing' AND bs.direction = '应收' THEN '应收账单生成' "
                "WHEN n.event_type = 'billing' AND bs.direction = '应付' THEN '应付账单生成' "
                "WHEN n.event_type = 'billing' THEN '待确认账单生成' "
                "WHEN n.event_type IN ('billing_confirmed','billing_confirmed_by_peer') THEN '账单已确认' "
                "WHEN n.event_type IN ('billing_settled','billing_settled_by_peer') THEN '账单已结清' "
                "ELSE n.title END, "
                "n.content = CASE "
                "WHEN n.event_type = 'billing' THEN CONCAT("
                "'对方：', COALESCE(JSON_UNQUOTE(JSON_EXTRACT(bs.source_snapshot_json, '$.counterparty_name')), '—'), "
                "'｜金额：¥', CAST(bs.amount AS CHAR), '｜账单号：', bs.statement_no"
                ") "
                "WHEN n.event_type IN ('billing_confirmed','billing_confirmed_by_peer') THEN CONCAT("
                "'账单已确认｜金额：¥', CAST(bs.amount AS CHAR), "
                "'｜对方：', COALESCE(JSON_UNQUOTE(JSON_EXTRACT(bs.source_snapshot_json, '$.counterparty_name')), '—'), "
                "'｜下一步：', CASE WHEN bs.direction = '应收' THEN '等待对方付款' ELSE '安排付款' END"
                ") "
                "WHEN n.event_type IN ('billing_settled','billing_settled_by_peer') THEN CONCAT("
                "'金额：¥', CAST(bs.amount AS CHAR), "
                "'｜对方：', COALESCE(JSON_UNQUOTE(JSON_EXTRACT(bs.source_snapshot_json, '$.counterparty_name')), '—'), "
                "'｜账单号：', bs.statement_no"
                ") "
                "ELSE n.content END "
                "WHERE n.event_type IN ("
                "'billing','billing_confirmed','billing_confirmed_by_peer',"
                "'billing_settled','billing_settled_by_peer'"
                ") "
                "AND (n.title IN ('已生成账单','对方已核对账单','对方已结清账单','对方已部分付款') "
                "OR n.content LIKE '账单 ST-%' "
                "OR n.content LIKE '对方已核对账单%' "
                "OR n.content LIKE '对方已结清账单%')"
            )
        )
        await conn.execute(
            text(
                "DELETE n_old FROM notifications n_old "
                "JOIN notifications n_new ON n_old.id < n_new.id "
                "AND n_old.event_type = n_new.event_type "
                "AND n_old.target_user_id = n_new.target_user_id "
                "AND n_old.object_type = n_new.object_type "
                "AND n_old.object_id = n_new.object_id "
                "AND COALESCE(n_old.title, '') = COALESCE(n_new.title, '') "
                "AND COALESCE(n_old.content, '') = COALESCE(n_new.content, '') "
                "AND COALESCE(n_old.route, '') = COALESCE(n_new.route, '') "
                "WHERE n_old.object_type = 'billing_statement' "
                "AND n_old.event_type IN ("
                "'billing','billing_confirmed','billing_confirmed_by_peer',"
                "'billing_settled','billing_settled_by_peer'"
                ")"
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


async def _ensure_order_receiving_lines_lock_photo_columns() -> None:
    """收货行智能秤留痕照片字段；旧库缺列会导致订单详情查询 order_receiving_lines 500。"""
    if "mysql" not in settings.database_url:
        return
    cols = [
        ("lock_photo_url", "VARCHAR(1024) NULL COMMENT '锁定读数秤盘留痕照片URL'"),
        ("lock_photo_taken_at", "DATETIME NULL COMMENT '留痕拍摄时间'"),
        ("lock_photo_device_id", "VARCHAR(128) NULL COMMENT '智能秤设备ID'"),
        ("return_photo_urls_json", "JSON NULL COMMENT '退货/质量问题证据照片URL数组'"),
        ("return_note", "VARCHAR(1000) NULL COMMENT '退货/少收补充说明'"),
        ("confirmed_quantity", "DECIMAL(14,4) NULL COMMENT '标品实收数量'"),
        ("confirmed_unit", "VARCHAR(20) NULL COMMENT '标品实收单位'"),
        ("sample_kg", "DECIMAL(14,4) NULL COMMENT '标品拍照留痕参考重量kg'"),
    ]
    async with engine.begin() as conn:
        for col_name, ddl_suffix in cols:
            r = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'order_receiving_lines' "
                    "AND COLUMN_NAME = :col"
                ),
                {"schema": settings.mysql_db, "col": col_name},
            )
            if (r.scalar_one() or 0) > 0:
                continue
            await conn.execute(
                text(f"ALTER TABLE order_receiving_lines ADD COLUMN {col_name} {ddl_suffix}")
            )


async def _ensure_order_return_line_evidence_columns() -> None:
    """退货明细证据照片与扣减金额；旧库幂等 ALTER。"""
    if "mysql" not in settings.database_url:
        return
    cols = [
        ("photo_urls_json", "JSON NULL COMMENT '退货证据照片URL数组'"),
        ("deduction_amount", "DECIMAL(12,2) NULL COMMENT '该退货明细扣减金额'"),
    ]
    async with engine.begin() as conn:
        for col_name, ddl_suffix in cols:
            r = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'order_return_lines' "
                    "AND COLUMN_NAME = :col"
                ),
                {"schema": settings.mysql_db, "col": col_name},
            )
            if (r.scalar_one() or 0) > 0:
                continue
            await conn.execute(text(f"ALTER TABLE order_return_lines ADD COLUMN {col_name} {ddl_suffix}"))


async def _ensure_kuaimai_print_columns() -> None:
    """快麦云打印：用户绑定打印机 SN、分单标签打印次数。"""
    if "mysql" not in settings.database_url:
        return
    async with engine.begin() as conn:
        r = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'users' "
                "AND COLUMN_NAME = 'kuaimai_printer_sn'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r.scalar_one() or 0) == 0:
            await conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN kuaimai_printer_sn VARCHAR(64) NULL "
                    "COMMENT '快麦云打印机序列号'"
                )
            )
        r2 = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'order_item_allocations' "
                "AND COLUMN_NAME = 'label_print_count'"
            ),
            {"schema": settings.mysql_db},
        )
        if (r2.scalar_one() or 0) == 0:
            await conn.execute(
                text(
                    "ALTER TABLE order_item_allocations ADD COLUMN label_print_count INT NOT NULL "
                    "DEFAULT 0 COMMENT '云标签累计打印次数'"
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


async def _ensure_zgncpjgw_tables() -> None:
    """农产品价格网行情表；与业务库隔离，仅幂等建表。"""
    if "mysql" not in settings.database_url:
        return
    tbl = settings.zgncpjgw_price_table or "zgncpjgw_price_crawl"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS `{tbl}` (
                    `id` BIGINT NOT NULL AUTO_INCREMENT,
                    `crawl_date` DATE NOT NULL COMMENT '查询日',
                    `district_id` INT NOT NULL,
                    `district_name` VARCHAR(128) NOT NULL DEFAULT '',
                    `cate_id` INT NOT NULL,
                    `cate_name` VARCHAR(128) NOT NULL DEFAULT '',
                    `scate_name` VARCHAR(128) NOT NULL DEFAULT '',
                    `goods_sn` VARCHAR(128) NOT NULL DEFAULT '',
                    `goods_name` VARCHAR(256) NOT NULL DEFAULT '',
                    `spec` VARCHAR(512) NOT NULL DEFAULT '',
                    `unit` VARCHAR(64) NOT NULL DEFAULT '',
                    `place` VARCHAR(256) NOT NULL DEFAULT '',
                    `price` VARCHAR(64) NOT NULL DEFAULT '',
                    `update_date` DATE NULL,
                    `raw_json` LONGTEXT NULL,
                    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (`id`),
                    UNIQUE KEY `uk_zgncpjgw_row` (
                        `crawl_date`, `district_id`, `cate_id`, `goods_sn`(64), `spec`(128), `place`(64), `update_date`
                    ),
                    KEY `idx_crawl_date` (`crawl_date`),
                    KEY `idx_goods_name` (`goods_name`(64)),
                    KEY `idx_district_cate_day` (`district_id`, `cate_id`, `crawl_date`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS `zgncpjgw_account_config` (
                    `id` TINYINT NOT NULL DEFAULT 1,
                    `username` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '中农价格网手机号',
                    `password_enc` TEXT NOT NULL COMMENT 'Fernet 加密密码',
                    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    `updated_by` VARCHAR(64) NOT NULL DEFAULT '',
                    PRIMARY KEY (`id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )


DEMO_SECOND_CANTEEN_NAME = "二食堂（演示）"


async def _ensure_client_canteens_for_user(session: AsyncSession, u: User) -> None:
    """幂等：若该采购方尚无任一食堂，则一次性新增「默认食堂」+「二食堂（演示）」两所启用食堂。"""
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
        session.add(
            ClientCanteen(
                school_client_id=cid,
                name=DEMO_SECOND_CANTEEN_NAME,
                address=addr,
                lng=u.lng,
                lat=u.lat,
                status="active",
                sort_order=1,
            )
        )


async def _ensure_demo_second_canteen_if_single(session: AsyncSession) -> None:
    """幂等：老库仅有「默认食堂」一所时补第二所，便于主站/控制台多食堂联调。"""
    clients = (
        await session.scalars(select(User).where(User.role == "client", User.status == "active"))
    ).all()
    for u in clients:
        cid = int(u.id)
        rows = (
            await session.scalars(
                select(ClientCanteen)
                .where(ClientCanteen.school_client_id == cid)
                .order_by(ClientCanteen.sort_order, ClientCanteen.id)
            )
        ).all()
        names = {r.name for r in rows}
        if DEMO_SECOND_CANTEEN_NAME in names:
            continue
        if len(rows) >= 2:
            continue
        addr = (u.address or "").strip() or "—"
        session.add(
            ClientCanteen(
                school_client_id=cid,
                name=DEMO_SECOND_CANTEEN_NAME,
                address=addr,
                lng=u.lng,
                lat=u.lat,
                status="active",
                sort_order=1,
            )
        )


async def seed_client_canteens_and_backfill_orders(session: AsyncSession) -> None:
    """为尚无食堂的采购方幂等补两所演示食堂，并回填订单 canteen_id（MySQL）。"""
    clients = (
        await session.scalars(select(User).where(User.role == "client", User.status == "active"))
    ).all()
    for u in clients:
        await _ensure_client_canteens_for_user(session, u)
    await _ensure_demo_second_canteen_if_single(session)
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
            await _ensure_billing_statements_reconciliation_id()
            await _ensure_billing_cycles_granularity_columns()
            await _ensure_quality_reports_allocation_id()
            await _ensure_quality_reports_attachments_json()
            await _ensure_products_quality_report_mode()
            await _ensure_categories_image_url()
            await _ensure_periodic_quality_report_version_columns()
            await _ensure_tickets_attachments_json()
            await _ensure_tickets_complaint_flow_columns()
            await _ensure_tickets_billing_columns()
            await _ensure_orders_canteen_id_column()
            await _ensure_order_receiving_lines_lock_photo_columns()
            await _ensure_order_return_line_evidence_columns()
            await _ensure_notifications_canteen_id_column()
            await _ensure_notifications_read_at_column()
            await _ensure_billing_notification_routes()
            await _ensure_kuaimai_print_columns()
            await _ensure_billing_tables()
            await _ensure_xinfadi_tables()
            await _ensure_zgncpjgw_tables()
            from services.zgncpjgw_credentials import refresh_credentials

            await refresh_credentials()
            if settings.seed_on_start:
                async with SessionLocal() as session:
                    await seed_data(session)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(f"数据库初始化失败: {last_error}") from last_error


DEMO_KUAIMAI_PRINTER_SN = "KM118DW25100096"

# 计划内演示账号 + 智能分单 lab 账号（京牧鲜、瀚华等）
DEMO_KUAIMAI_PRINTER_USERNAMES = (
    "supplier001",
    "supplier002",
    "supplier003",
    "factory001",
    "supplier_jingmuxian",
    "supplier_hanhua",
)


async def seed_demo_kuaimai_printers(session: AsyncSession) -> None:
    """演示供货商/厂家共用一台云打印机。"""
    sn = (settings.kuaimai_printer_sn or DEMO_KUAIMAI_PRINTER_SN).strip()
    if not sn:
        return
    for uname in DEMO_KUAIMAI_PRINTER_USERNAMES:
        u = await session.scalar(select(User).where(User.username == uname))
        if u:
            u.kuaimai_printer_sn = sn
    if settings.demo_mode:
        rows = (
            await session.scalars(
                select(User).where(
                    User.role.in_(("supplier", "factory")),
                    User.status == "active",
                    or_(User.kuaimai_printer_sn.is_(None), User.kuaimai_printer_sn == ""),
                )
            )
        ).all()
        for u in rows:
            u.kuaimai_printer_sn = sn
    await session.commit()


async def seed_data(session: AsyncSession):
    await seed_users(session)
    await seed_client_canteens_and_backfill_orders(session)
    await seed_demo_suppliers_bind_delivery(session)
    await seed_demo_kuaimai_printers(session)
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
