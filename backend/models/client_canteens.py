from typing import Optional

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ClientCanteen(Base, TimestampMixin):
    """学校（users.role=client）下属的履约食堂；合约仍挂在学校账号。"""

    __tablename__ = "client_canteens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_client_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    lng: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    lat: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    status: Mapped[str] = mapped_column(
        Enum("active", "disabled"), nullable=False, default="active"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
