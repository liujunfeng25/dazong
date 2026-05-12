from datetime import date, datetime

from pydantic import BaseModel
from typing import Optional


class TenderCreateIn(BaseModel):
    delivery_ids: list[int]
    category_ids: Optional[list[int]] = None
    period_start: date
    period_end: date


class BidCategoryRateIn(BaseModel):
    category_id: int
    float_rate: float


class BidIn(BaseModel):
    category_rates: list[BidCategoryRateIn]


class AwardIn(BaseModel):
    delivery_id: int


class TenderOut(BaseModel):
    id: int
    client_id: int
    delivery_ids_json: list[int]
    category_ids_json: list[int]
    period_start: date
    period_end: date
    status: str
    created_at: datetime
