from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SortRecord(Base):
    __tablename__ = "sort_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    sorted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    label_printed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
