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
    ys7_base_url: str = Field(default="https://open.ys7.com/api/lapp")
    ys7_app_key: str = Field(default="")
    ys7_app_secret: str = Field(default="")
    seniverse_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("SENIVERSE_API_KEY", "DRIVING_RESTRICTION_API_KEY"),
    )

    # AI 业务分析助手：默认使用 DashScope OpenAI 兼容模式；无 key 时后端本地兜底
    ai_api_key: str = Field(default="", validation_alias=AliasChoices("AI_API_KEY", "DASHSCOPE_API_KEY"))
    ai_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    ai_model_planner: str = Field(default="qwen-plus")
    ai_model_answer: str = Field(default="qwen-plus")

    # 新发地行情/预测：同构迁入 dazong 库
    xinfadi_price_api: str = Field(default="http://www.xinfadi.com.cn/getPriceData.html")
    xinfadi_price_table: str = Field(default="xinfadi_price_crawl")
    xinfadi_polite_crawl: bool = Field(default=False)
    xinfadi_models_dir: str = Field(default="data/models/price_forecast")

    # 智能秤 UniApp：启动时拉取，用于内网/外网自更新（不上架商店时可配 apk/wgt 直链）
    smart_scale_app_version_code: int = Field(default=100, description="与 manifest versionCode 对齐，有更新则递增")
    smart_scale_app_version_name: str = Field(default="1.0.0", description="展示用版本名")
    smart_scale_app_apk_url: str = Field(default="", description="整包 APK 下载绝对 URL，空则不下发整包")
    smart_scale_app_wgt_url: str = Field(default="", description="wgt 热更包 URL，空则不下发热更")
    smart_scale_app_force_update: bool = Field(default=False, description="是否强提示更新")
    smart_scale_app_notes: str = Field(default="", description="更新说明")

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


settings = Settings()
