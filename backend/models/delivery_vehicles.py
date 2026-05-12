from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeliveryVehicle(Base):
    __tablename__ = "delivery_vehicles"
    __table_args__ = (
        UniqueConstraint("delivery_id", "vehicle_no", name="uq_delivery_vehicle_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    vehicle_no: Mapped[str] = mapped_column(String(32), nullable=False)
    vehicle_model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    driver_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    capacity_weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))
    capacity_volume_m3: Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
