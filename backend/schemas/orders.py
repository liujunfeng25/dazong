from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int
    unit_price: Decimal


class OrderCreateIn(BaseModel):
    delivery_id: int
    items: list[OrderItemIn]
    delivery_address: Optional[str] = None
    delivery_lng: Optional[Decimal] = None
    delivery_lat: Optional[Decimal] = None
    expected_delivery_date: Optional[date] = None
    expected_delivery_slot: Optional[str] = Field(
        default=None, description="整点 1 小时区间，如 06:00-07:00 或 23:00-24:00"
    )
    service_duration_min: int = 30
    force: bool = False


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


class ReceivingDraftIn(BaseModel):
    net_kg: float = Field(..., gt=0, le=1_000_000)


class ShortageReasonIn(BaseModel):
    """少收原因：lack=缺货，quality=质量问题，other=其他（须填 detail）。"""

    code: Literal["lack", "quality", "other"]
    detail: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_other(self):
        if self.code == "other":
            d = (self.detail or "").strip()
            if len(d) < 2:
                raise ValueError("选择「其他」时请填写原因说明（至少2个字）")
            self.detail = d
        return self


class ReceivingConfirmIn(BaseModel):
    net_kg: float = Field(..., gt=0, le=1_000_000)
    shortage_reason: Optional[ShortageReasonIn] = Field(
        default=None,
        description="实收少于下单折算 kg 时必填",
    )


class ReceiveOrderIn(BaseModel):
    """智能秤整单收货提交；网页端旧流程可不传。存在称重行记录时必填双方签字。"""

    warehouse_signature: Optional[str] = None
    carrier_signature: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    order_no: str
    client_id: int
    delivery_id: int
    supplier_id: int
    items_json: list
    items_snapshot_json: list
    total_amount: Decimal
    total_volume_m3: Optional[Decimal]
    total_weight_kg: Optional[Decimal]
    delivery_address: Optional[str]
    delivery_lng: Optional[Decimal]
    delivery_lat: Optional[Decimal]
    expected_delivery_date: Optional[date]
    expected_delivery_slot: Optional[str]
    service_duration_min: int
    status: str
    has_abnormal: bool
    created_at: datetime
    updated_at: datetime
