from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("client", "supplier", "delivery", "factory", "operation", "monitor"),
        nullable=False,
    )
    bind_client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    supplier_delivery_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    company_name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    lng: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    lat: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    status: Mapped[str] = mapped_column(
        Enum("active", "disabled"), nullable=False, default="active"
    )
    kuaimai_printer_sn: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    return_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
