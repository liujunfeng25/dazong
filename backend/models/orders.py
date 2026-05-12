from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    canteen_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("client_canteens.id"), nullable=True, index=True
    )
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # 履约供货商以 order_item_allocations 为准；下单时可为空，待配送商分单后才有分包方
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    items_json: Mapped[list] = mapped_column(JSON, nullable=False)
    # 下单时固化商品/分类快照，避免后续商品或分类变更影响历史订单追溯
    items_snapshot_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_volume_m3: Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    total_weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))
    delivery_address: Mapped[Optional[str]] = mapped_column(String(255))
    delivery_lng: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    delivery_lat: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    expected_delivery_date: Mapped[Optional[date]] = mapped_column(Date)
    expected_delivery_slot: Mapped[Optional[str]] = mapped_column(String(32))
    service_duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[str] = mapped_column(
        Enum("下单", "取消", "配货", "发货", "收货", "收货确认", "已结算"), nullable=False, default="下单"
    )
    has_abnormal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 智能秤双签收货：{ warehouse_signature, carrier_signature, recorded_at }（Base64 或 data URL）
    receive_signatures_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
