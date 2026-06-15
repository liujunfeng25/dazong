from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeliveryWarehouse(Base):
    __tablename__ = "delivery_warehouses"
    __table_args__ = (
        UniqueConstraint("delivery_id", "name", name="uq_delivery_warehouse_name_per_delivery"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(256))
    lng: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    lat: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DeliveryWarehouseDeviceBinding(Base):
    __tablename__ = "delivery_warehouse_device_bindings"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_delivery_warehouse_binding_device_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("delivery_warehouses.id"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("delivery_devices.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
