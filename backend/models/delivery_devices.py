from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeliveryDevice(Base):
    __tablename__ = "delivery_devices"
    __table_args__ = (
        UniqueConstraint("vendor", "device_code", "channel_no", name="uq_delivery_device_vendor_code_ch"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_type: Mapped[str] = mapped_column(String(16), nullable=False)
    vendor: Mapped[str] = mapped_column(String(16), nullable=False)
    device_code: Mapped[str] = mapped_column(String(128), nullable=False)
    device_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    channel_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_payload_json: Mapped[Optional[Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
