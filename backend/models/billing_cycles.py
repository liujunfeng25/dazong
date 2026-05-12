from datetime import date

from sqlalchemy import Boolean, Date, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class BillingCycle(Base, TimestampMixin):
    __tablename__ = "billing_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(Enum("client", "delivery", "supplier", "factory"), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, default="canteen")
    scope_ref_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cycle_type: Mapped[str] = mapped_column(Enum("daily", "weekly", "monthly"), nullable=False, default="monthly")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confirm_due_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    payment_due_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
