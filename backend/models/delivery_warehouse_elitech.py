from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeliveryWarehouseElitechBinding(Base):
    __tablename__ = "delivery_warehouse_elitech_bindings"
    __table_args__ = (
        UniqueConstraint("warehouse_id", name="uq_delivery_warehouse_elitech_warehouse_id"),
        UniqueConstraint("elitech_sn", name="uq_delivery_warehouse_elitech_sn"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("delivery_warehouses.id"), nullable=False)
    elitech_sn: Mapped[str] = mapped_column(String(64), nullable=False)
    device_name: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
