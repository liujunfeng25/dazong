from datetime import date

from sqlalchemy import Date, Enum, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("招标中", "已中标", "已过期"), nullable=False, default="招标中"
    )
    price_float_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    category_rates_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
