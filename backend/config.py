from pydantic import Field
from pydantic.fields import AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "大宗供应链系统"
    api_prefix: str = "/api"
    jwt_secret_key: str = "please_override_in_env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "please_override_in_env"
    mysql_db: str = "dazong"
    delivery_fee_rate: float = 0.08

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "dazong-quality"
    minio_secure: bool = False
    minio_public_base_url: str = "http://127.0.0.1:9000/dazong-quality"
    # 为 true 时启动后给 MINIO_BUCKET 设置匿名可读（与 MINIO_PUBLIC_BASE_URL 直链预览一致）。生产若走签名 URL 可改为 false。
    minio_anonymous_read: bool = True
    demo_mode: bool = False
    auto_create_schema: bool = True
    seed_on_start: bool = True
    # 含端口：H5 开发（Vite 默认 5173）、UniApp H5 等；生产请在 .env 覆盖 CORS_ORIGINS
    cors_origins: str = (
        "http://localhost,http://127.0.0.1,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8080,http://127.0.0.1:8080,"
        "http://localhost:15175,http://127.0.0.1:15175"
    )

    ws_monitor_kpi_interval_seconds: int = 3
    ws_monitor_vehicle_interval_seconds: int = 5
    ws_reconnect_seconds: int = 3

    simulator_enabled: bool = True
    simulator_gps_interval_seconds: int = 5
    simulator_sensor_interval_seconds: int = 30
    simulator_sensor_alert_cycle_seconds: int = 300

    # OCR：与 ai-agent 票据识别兼容，可用 DOCUMENTS_OCR_ENGINE / DOCUMENTS_BAIDU_TABLE_API_KEY
    ocr_engine: str = Field(
        default="auto",
        validation_alias=AliasChoices("OCR_ENGINE", "DOCUMENTS_OCR_ENGINE"),
        description="auto=有密钥走百度否则 mock；baidu；mock",
    )
    baidu_table_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("BAIDU_TABLE_API_KEY", "DOCUMENTS_BAIDU_TABLE_API_KEY"),
    )
    amap_web_key: str = Field(
        default="",
        validation_alias=AliasChoices("AMAP_WEB_KEY", "GAODE_MAP_KEY"),
    )
    gps18_base_url: str = Field(default="http://openapi.18gps.net")
    gps18_username: str = Field(default="")
    gps18_password: str = Field(default="")
    gps18_history_map_type: str = Field(default="", validation_alias=AliasChoices("GPS18_HISTORY_MAP_TYPE"))
    gps18_map_type: str = Field(default="", validation_alias=AliasChoices("GPS18_MAP_TYPE"))
    gps18_coord_for_amap: str = Field(default="auto", validation_alias=AliasChoices("GPS18_COORD_FOR_AMAP"))
    gps18_history_play_lbs: bool = Field(default=False, validation_alias=AliasChoices("GPS18_HISTORY_PLAY_LBS"))
    gps18_history_method: str = Field(default="", validation_alias=AliasChoices("GPS18_HISTORY_METHOD"))
    gps18_history_method_user: str = Field(default="", validation_alias=AliasChoices("GPS18_HISTORY_METHOD_USER"))
    gps18_history_maptype_fallback: bool = Field(
        default=True,
        validation_alias=AliasChoices("GPS18_HISTORY_MAPTYPE_FALLBACK"),
    )
    beidou_history_max_span_seconds: int = Field(
        default=864000,
        ge=3600,
        le=864000,
        validation_alias=AliasChoices("BEIDOU_HISTORY_MAX_SPAN_SECONDS"),
    )
    beidou_history_max_points: int = Field(
        default=5000,
        ge=200,
        le=20000,
        validation_alias=AliasChoices("BEIDOU_HISTORY_MAX_POINTS"),
    )
    beidou_history_merge_meters: float = Field(
        default=0.0,
        ge=0.0,
        le=5000.0,
        validation_alias=AliasChoices("ELITECH_HISTORY_STATIONARY_MERGE_METERS", "BEIDOU_HISTORY_MERGE_METERS"),
    )
    ys7_base_url: str = Field(default="https://open.ys7.com/api/lapp")
    ys7_app_key: str = Field(default="")
    ys7_app_secret: str = Field(default="")
    ys7_live_use_ezopen: bool = Field(default=True, validation_alias=AliasChoices("YS7_LIVE_USE_EZOPEN"))
    ys7_live_open_before_get: bool = Field(default=True, validation_alias=AliasChoices("YS7_LIVE_OPEN_BEFORE_GET"))
    ys7_live_url_expire: int = Field(default=300, ge=60, le=86400, validation_alias=AliasChoices("YS7_LIVE_URL_EXPIRE"))
    ys7_live_address_include_expire: bool = Field(
        default=False,
        validation_alias=AliasChoices("YS7_LIVE_ADDRESS_INCLUDE_EXPIRE"),
    )
    ys7_live_protocol: int = Field(default=2, ge=1, le=4, validation_alias=AliasChoices("YS7_LIVE_PROTOCOL"))
    ys7_battery_wake_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=15.0,
        validation_alias=AliasChoices("YS7_BATTERY_WAKE_SECONDS"),
    )
    elitech_base_url: str = Field(
        default="https://www.i-elitech.net",
        validation_alias=AliasChoices("ELITECH_BASE_URL"),
    )
    elitech_client_id: str = Field(
        default="19290248",
        validation_alias=AliasChoices("ELITECH_CLIENT_ID", "ELITECH_KEY_ID"),
    )
    elitech_key_secret: str = Field(
        default="xKDSpdRjXzjMHaRsUKkC",
        validation_alias=AliasChoices("ELITECH_KEY_SECRET"),
    )
    elitech_username: str = Field(
        default="",
        validation_alias=AliasChoices("ELITECH_USERNAME"),
    )
    elitech_password: str = Field(
        default="",
        validation_alias=AliasChoices("ELITECH_PASSWORD"),
    )
    elitech_device_guids: str = Field(
        default="90479474340999030026",
        validation_alias=AliasChoices("ELITECH_DEVICE_GUIDS"),
    )
    seniverse_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("SENIVERSE_API_KEY", "DRIVING_RESTRICTION_API_KEY"),
    )

    # AI 业务分析助手：默认使用 DashScope OpenAI 兼容模式；无 key 时后端本地兜底
    ai_api_key: str = Field(default="", validation_alias=AliasChoices("AI_API_KEY", "DASHSCOPE_API_KEY"))
    ai_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    ai_model_planner: str = Field(default="qwen3.7-plus")
    ai_model_answer: str = Field(default="qwen3.7-plus")
    # 智能体工具循环最大轮数；只读 SQL 单次返回行数上限与超时
    ai_agent_max_steps: int = Field(default=6, ge=1, le=12)
    ai_sql_row_limit: int = Field(default=1000, ge=1, le=10000)
    ai_sql_timeout_ms: int = Field(default=8000, ge=500, le=60000)

    # 操作手册 RAG（监管 AI「怎么用」）
    rag_enabled: bool = Field(default=True)
    rag_top_k: int = Field(default=5, ge=1, le=20)
    docs_index_path: str = Field(default="data/rag/chunks.jsonl")
    docs_embedded_index_path: str = Field(default="data/rag/chunks.embedded.jsonl")
    rag_embedding_model: str = Field(default="text-embedding-v3")
    rag_embedding_dimensions: int = Field(default=1024, ge=64, le=4096)
    rag_hybrid_alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    ai_chat_history_limit: int = Field(default=16, ge=4, le=32)
    ai_chat_synthesis_enabled: bool = Field(default=True)
    # 工具调用数低于此值且非 report/clarify、已有回复时跳过 Answer 合成（省延迟与 token）
    ai_chat_synthesis_min_tools: int = Field(default=2, ge=0, le=12)

    # 只读 DB 账号（供 AI 的 run_sql 工具使用；为空则回退主账号但仍强制 SELECT-only 校验）
    mysql_ro_user: str = Field(default="", validation_alias=AliasChoices("MYSQL_RO_USER"))
    mysql_ro_password: str = Field(default="", validation_alias=AliasChoices("MYSQL_RO_PASSWORD"))

    # 新发地行情/预测：同构迁入 dazong 库
    xinfadi_price_api: str = Field(default="http://www.xinfadi.com.cn/getPriceData.html")
    xinfadi_price_table: str = Field(default="xinfadi_price_crawl")
    xinfadi_polite_crawl: bool = Field(default=False)
    # 批量补抓时「每处理完一天」再抓下一天前的随机休眠（秒），减轻新发地 503 限流（默认 3～5 秒）
    xinfadi_backfill_day_pause_min: float = Field(default=3.0, ge=0.0, le=120.0)
    xinfadi_backfill_day_pause_max: float = Field(default=5.0, ge=0.0, le=180.0)
    # 慢速模式下「每处理完一天」的间隔（秒），用于跨年度大范围补抓避免被反爬识别；默认 12~25 秒
    xinfadi_backfill_slow_day_pause_min: float = Field(default=12.0, ge=0.0, le=600.0)
    xinfadi_backfill_slow_day_pause_max: float = Field(default=25.0, ge=0.0, le=900.0)
    # 单页 POST 遇 502/503/504 或网络类错误时的最大尝试次数（含首次）
    xinfadi_http_max_retries: int = Field(default=5, ge=1, le=12)
    xinfadi_http_retry_base_seconds: float = Field(default=1.2, ge=0.2, le=30.0)
    xinfadi_models_dir: str = Field(default="data/models/price_forecast")

    # 农产品价格网 zgncpjgw.com 行情采集（独立表 zgncpjgw_price_crawl，与业务库隔离）
    zgncpjgw_base_url: str = Field(default="https://www.zgncpjgw.com")
    zgncpjgw_username: str = Field(default="", validation_alias=AliasChoices("ZGNCPJGW_USERNAME"))
    zgncpjgw_password: str = Field(default="", validation_alias=AliasChoices("ZGNCPJGW_PASSWORD"))
    zgncpjgw_price_table: str = Field(default="zgncpjgw_price_crawl")
    zgncpjgw_polite_crawl: bool = Field(default=True)
    zgncpjgw_http_max_retries: int = Field(default=5, ge=1, le=12)
    zgncpjgw_http_retry_base_seconds: float = Field(default=1.2, ge=0.2, le=30.0)
    zgncpjgw_page_pause_min: float = Field(default=0.3, ge=0.0, le=120.0)
    zgncpjgw_page_pause_max: float = Field(default=1.0, ge=0.0, le=180.0)
    zgncpjgw_category_pause_min: float = Field(default=0.5, ge=0.0, le=120.0)
    zgncpjgw_category_pause_max: float = Field(default=2.0, ge=0.0, le=180.0)
    zgncpjgw_day_pause_min: float = Field(default=2.0, ge=0.0, le=600.0)
    zgncpjgw_day_pause_max: float = Field(default=5.0, ge=0.0, le=900.0)
    zgncpjgw_expected_districts: int = Field(default=12, ge=1, le=32, description="视为齐全的最少省份数")
    zgncpjgw_expected_categories: int = Field(
        default=12, ge=1, le=32, description="单省视为齐全的最少一级分类数"
    )
    zgncpjgw_crawl_concurrency: int = Field(default=8, ge=1, le=12, description="同日多省并行抓取上限")

    # 智能秤 UniApp：启动时拉取，用于内网/外网自更新（不上架商店时可配 apk/wgt 直链）
    smart_scale_app_version_code: int = Field(default=100, description="与 manifest versionCode 对齐，有更新则递增")
    smart_scale_app_version_name: str = Field(default="1.0.0", description="展示用版本名")
    smart_scale_app_apk_url: str = Field(default="", description="整包 APK 下载绝对 URL，空则不下发整包")
    smart_scale_app_wgt_url: str = Field(default="", description="wgt 热更包 URL，空则不下发热更")
    smart_scale_app_force_update: bool = Field(default=False, description="是否强提示更新")
    smart_scale_app_notes: str = Field(default="", description="更新说明")

    kuaimai_app_id: str = Field(default="", validation_alias=AliasChoices("KUAIMAI_APP_ID"))
    kuaimai_app_secret: str = Field(default="", validation_alias=AliasChoices("KUAIMAI_APP_SECRET"))
    kuaimai_printer_sn: str = Field(default="", validation_alias=AliasChoices("KUAIMAI_PRINTER_SN"))
    kuaimai_template_id: int = Field(default=0, validation_alias=AliasChoices("KUAIMAI_TEMPLATE_ID"))
    kuaimai_bind_table: str = Field(default="FoodLink", validation_alias=AliasChoices("KUAIMAI_BIND_TABLE"))
    kuaimai_device_key: str = Field(default="", validation_alias=AliasChoices("KUAIMAI_DEVICE_KEY"))
    kuaimai_verify_print_result: bool = Field(
        default=True,
        validation_alias=AliasChoices("KUAIMAI_VERIFY_PRINT_RESULT"),
    )

    @property
    def ocr_effective_engine(self) -> str:
        key = (self.baidu_table_api_key or "").strip()
        mode = (self.ocr_engine or "auto").strip().lower()
        if mode == "mock":
            return "mock"
        if mode == "baidu":
            return "baidu" if key else "mock"
        # auto
        return "baidu" if key else "mock"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )

    @property
    def readonly_database_url(self) -> str:
        """AI run_sql 用的只读 DSN：配了只读账号则用之，否则回退主账号（仍由 SELECT-only 校验兜底）。"""
        user = self.mysql_ro_user or self.mysql_user
        pwd = self.mysql_ro_password if self.mysql_ro_user else self.mysql_password
        return (
            f"mysql+aiomysql://{user}:{pwd}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )


settings = Settings()
