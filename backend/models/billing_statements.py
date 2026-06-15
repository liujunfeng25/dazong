from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class BillingStatement(Base, TimestampMixin):
    __tablename__ = "billing_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("billing_cycles.id"), nullable=False, index=True)
    reconciliation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    role: Mapped[str] = mapped_column(Enum("client", "delivery", "supplier", "factory"), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    counterparty_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    canteen_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("client_canteens.id"), nullable=True, index=True
    )
    direction: Mapped[str] = mapped_column(Enum("应付", "应收"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("待确认", "已确认", "部分结清", "已结清"),
        nullable=False,
        default="待确认",
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    confirmed_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    settled_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cycle_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
