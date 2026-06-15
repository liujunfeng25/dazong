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


class PrintAllocationLabelsIn(BaseModel):
    allocation_ids: list[int] = Field(default_factory=list, description="为空表示本户全部分单")


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


class ReturnReviewIn(BaseModel):
    action: Literal["approve", "reject"]
    note: Optional[str] = Field(default=None, max_length=1000)


class ReceivingDraftIn(BaseModel):
    net_kg: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    received_quantity: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    received_unit: Optional[str] = Field(default=None, max_length=20)
    sample_kg: Optional[float] = Field(default=None, gt=0, le=1_000_000)


class ShortageReasonIn(BaseModel):
    """少收原因：lack=缺货，quality=质量问题，other=其他（须填 detail）。"""

    code: Literal["lack", "quality", "other"]
    detail: Optional[str] = Field(default=None, max_length=500)
    photo_urls: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_other(self):
        if self.code == "other":
            d = (self.detail or "").strip()
            if len(d) < 2:
                raise ValueError("选择「其他」时请填写原因说明（至少2个字）")
            self.detail = d
        self.photo_urls = [u.strip() for u in (self.photo_urls or []) if u and u.strip()][:8]
        if self.code == "quality" and not self.photo_urls:
            raise ValueError("选择「质量问题」时请至少上传1张退货证据照片")
        return self


class ReceivingConfirmIn(BaseModel):
    net_kg: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    received_quantity: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    received_unit: Optional[str] = Field(default=None, max_length=20)
    sample_kg: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    shortage_reason: Optional[ShortageReasonIn] = Field(
        default=None,
        description="实收少于下单折算 kg 时必填",
    )
    lock_photo_url: Optional[str] = Field(default=None, max_length=1024)
    lock_photo_taken_at: Optional[datetime] = None
    lock_photo_device_id: Optional[str] = Field(default=None, max_length=128)


class ReceivingLineIn(ReceivingConfirmIn):
    line_index: int = Field(..., ge=1)


class ReceiveOrderIn(BaseModel):
    """智能秤整单收货提交；网页端旧流程可不传。存在称重行记录时必填双方签字。"""

    warehouse_signature: Optional[str] = None
    carrier_signature: Optional[str] = None
    warehouse_signature_url: Optional[str] = None
    carrier_signature_url: Optional[str] = None
    receiving_lines: list[ReceivingLineIn] = Field(default_factory=list)


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
