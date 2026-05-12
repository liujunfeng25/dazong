from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Tender(Base, TimestampMixin):
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    delivery_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)
    category_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("招标中", "已中标", "已关闭"), nullable=False, default="招标中"
    )
