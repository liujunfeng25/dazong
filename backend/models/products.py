from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goods_sn: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category1_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    category2_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    spec: Mapped[str] = mapped_column(String(120), default="")
    origin: Mapped[str] = mapped_column(String(120), default="")
    standard_type: Mapped[str] = mapped_column(
        Enum("standard", "non_standard"), nullable=False, default="standard"
    )
    length_cm: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    width_cm: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    height_cm: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    unit_weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 3))
    volume_adjust_factor: Mapped[Optional[float]] = mapped_column(Numeric(6, 3))
    is_designated_factory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    designated_factory_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    quality_report_mode: Mapped[str] = mapped_column(
        Enum("batch", "periodic"), nullable=False, default="batch"
    )
    status: Mapped[str] = mapped_column(
        Enum("active", "disabled"), nullable=False, default="active"
    )
    brand: Mapped[Optional[str]] = mapped_column(String(120))
    expire_date: Mapped[Optional[str]] = mapped_column(String(120))
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255))
    model: Mapped[Optional[str]] = mapped_column(String(120))
    source: Mapped[Optional[int]] = mapped_column(Integer)
    attr: Mapped[Optional[int]] = mapped_column(Integer)
    level: Mapped[Optional[int]] = mapped_column(Integer)
    limit_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    discount_rate: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    float_rate_max: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    float_rate_min: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    supplier_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(String(120))
    goods_channel: Mapped[Optional[int]] = mapped_column(Integer)
    finance_code: Mapped[Optional[str]] = mapped_column(String(120))
    finance_rate: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    number: Mapped[Optional[str]] = mapped_column(String(120))
    weight: Mapped[Optional[float]] = mapped_column(Numeric(10, 3))
    remark: Mapped[Optional[str]] = mapped_column(String(500))
    logo: Mapped[Optional[str]] = mapped_column(String(512))
    slogo: Mapped[Optional[str]] = mapped_column(String(512))
    detail_images_json: Mapped[Optional[list]] = mapped_column(JSON)
    image_list_json: Mapped[Optional[list]] = mapped_column(JSON)
    external_url: Mapped[Optional[str]] = mapped_column(String(512))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
