"""配送商电子围栏：禁行区、分检待命区、收货区（可与合约客户绑定）。"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

FENCE_TYPES = ("no_go", "staging", "receiving")


class DeliveryGeofence(Base):
    __tablename__ = "delivery_geofences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    fence_type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    geometry_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    center_lng: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    center_lat: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    radius_m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
