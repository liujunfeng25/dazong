from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    driver_name: Mapped[str] = mapped_column(String(64), nullable=False)
    vehicle_no: Mapped[str] = mapped_column(String(32), nullable=False)
    vehicle_capacity_volume_m3: Mapped[Optional[float]] = mapped_column(Float)
    vehicle_capacity_weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    current_lat: Mapped[Optional[float]] = mapped_column(Float)
    current_lng: Mapped[Optional[float]] = mapped_column(Float)
    route_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    departed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="待发车")
