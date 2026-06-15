from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from services.units import COUNT_UNITS, WEIGHT_UNITS


class CategoryIn(BaseModel):
    name: str
    level: int
    parent_id: Optional[int] = None
    sort_order: int = 0
    # 仅一级分类有效；未传时后端默认 1.0（与历史投标页面上限一致）
    max_float_rate: Optional[float] = None
    # 分类图片：图片 URL 或 "emoji:🥬" token；空则前端按名称自动映射
    image_url: Optional[str] = None


class CategoryOut(CategoryIn):
    id: int
    created_at: datetime


class ProductIn(BaseModel):
    goods_sn: Optional[str] = None
    name: str
    category1_id: int
    category2_id: int
    unit: str
    reference_price: Decimal
    spec: str = ""
    origin: str = ""
    standard_type: str = "standard"
    length_cm: Optional[Decimal] = None
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None
    unit_weight_kg: Optional[Decimal] = None
    volume_adjust_factor: Optional[Decimal] = None
    is_designated_factory: bool = False
    designated_factory_id: Optional[int] = None
    quality_report_mode: str = "batch"
    status: str = "active"
    brand: Optional[str] = None
    expire_date: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    source: Optional[int] = None
    attr: Optional[int] = None
    level: Optional[int] = None
    limit_price: Optional[Decimal] = None
    discount_rate: Optional[Decimal] = None
    float_rate_max: Optional[Decimal] = None
    float_rate_min: Optional[Decimal] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    goods_channel: Optional[int] = None
    finance_code: Optional[str] = None
    finance_rate: Optional[Decimal] = None
    number: Optional[str] = None
    weight: Optional[Decimal] = None
    remark: Optional[str] = None
    logo: Optional[str] = None
    slogo: Optional[str] = None
    detail_images_json: Optional[list[str]] = None
    image_list_json: Optional[list[str]] = None
    external_url: Optional[str] = None

    @model_validator(mode="after")
    def _validate_unit_matches_type(self):
        unit = (self.unit or "").strip()
        if self.standard_type == "non_standard":
            if unit not in WEIGHT_UNITS:
                raise ValueError(
                    f"非标品（按重量收货）的单位必须为计量单位 {WEIGHT_UNITS}，当前为「{unit}」"
                )
        else:  # standard
            if unit not in COUNT_UNITS:
                raise ValueError(
                    f"标品（按件清点）的单位必须为计数单位（如 {COUNT_UNITS[:6]} 等），当前为「{unit}」"
                )
        return self


class ProductOut(ProductIn):
    id: int
    created_at: datetime


class AccountIn(BaseModel):
    username: str
    # 新建默认 demo123；更新账号时可不传，表示不修改密码
    password: Optional[str] = None
    role: str
    bind_client_id: Optional[int] = None
    company_name: str
    contact_phone: str = ""
    address: str = ""
    # 前端通过地图扎针/拖动 marker 给出的精确坐标；若提供则优先使用，不再走 geocode 回退
    lng: Optional[Decimal] = None
    lat: Optional[Decimal] = None
    status: str = "active"
    return_review_required: bool = False


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    company_name: str
    contact_phone: str = ""
    address: str = ""
    lng: Optional[float] = None
    lat: Optional[float] = None
    supplier_delivery_id: Optional[int] = None
    return_review_required: bool = False
    status: str
    created_at: datetime


class ClientCanteenIn(BaseModel):
    school_client_id: int
    name: str
    address: str = ""
    lng: Optional[float] = None
    lat: Optional[float] = None
    status: str = "active"
    sort_order: int = 0


class ClientCanteenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_client_id: int
    name: str
    address: str
    lng: Optional[float] = None
    lat: Optional[float] = None
    status: str
    sort_order: int
    created_at: datetime
    client_name: Optional[str] = None
    client_username: Optional[str] = None
    display_label: Optional[str] = None


class TicketUpdateIn(BaseModel):
    status: str


class TicketResolveIn(BaseModel):
    resolution: str


class TicketIn(BaseModel):
    order_id: int
    type: str
    description: str


class ProductDimensionFillIn(BaseModel):
    dry_run: bool = True
    only_missing: bool = True
    batch_size: int = 300
