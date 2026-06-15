from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from services.geo_coords import is_usable_geo_coord


class WarehouseCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    address: Optional[str] = Field(default=None, max_length=256)
    lng: Decimal
    lat: Decimal

    @field_validator("name")
    @classmethod
    def _trim_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("仓库名称不能为空")
        return v

    @field_validator("lng")
    @classmethod
    def _check_lng(cls, v: Decimal) -> Decimal:
        if not (Decimal("-180") <= v <= Decimal("180")):
            raise ValueError("经度超出范围")
        return v

    @field_validator("lat")
    @classmethod
    def _check_lat(cls, v: Decimal) -> Decimal:
        if not (Decimal("-90") <= v <= Decimal("90")):
            raise ValueError("纬度超出范围")
        return v

    @model_validator(mode="after")
    def _check_usable_coord(self):
        if not is_usable_geo_coord(self.lng, self.lat):
            raise ValueError("仓库位置无效，请从地址联想选择或点击地图扎针")
        return self


class WarehouseUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    address: Optional[str] = Field(default=None, max_length=256)
    lng: Optional[Decimal] = None
    lat: Optional[Decimal] = None
    status: Optional[str] = Field(default=None, max_length=16)

    @model_validator(mode="after")
    def _check_usable_coord(self):
        if self.lng is None and self.lat is None:
            return self
        if self.lng is None or self.lat is None:
            raise ValueError("请同时提供经度与纬度")
        if not is_usable_geo_coord(self.lng, self.lat):
            raise ValueError("仓库位置无效，请从地址联想选择或点击地图扎针")
        return self


class WarehouseBindingIn(BaseModel):
    device_id: int


class ElitechBindIn(BaseModel):
    sn: str = Field(..., min_length=1, max_length=64)

    @field_validator("sn")
    @classmethod
    def _trim_sn(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("设备 SN 不能为空")
        return v
