from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ReconciliationStatement(Base, TimestampMixin):
    """对账单：按「我方 × 对手方 × 账期」聚合一张，是确认/结清的单元。
    下挂多条 billing_statements（明细行，按订单×对手方）。一张对账单与对方的镜像
    对账单（应付↔应收）通过 mirror_id 关联。"""

    __tablename__ = "reconciliation_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    relation_type: Mapped[str] = mapped_column(
        Enum("client_delivery", "delivery_supplier"), nullable=False, index=True
    )
    cycle_id: Mapped[int] = mapped_column(ForeignKey("billing_cycles.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(Enum("client", "delivery", "supplier", "factory"), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    counterparty_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    canteen_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    direction: Mapped[str] = mapped_column(Enum("应付", "应收"), nullable=False)
    period_label: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    status: Mapped[str] = mapped_column(
        Enum("进行中", "待确认", "已确认", "部分结清", "已结清"),
        nullable=False,
        default="进行中",
    )
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    adjust_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    settled_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    close_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    confirm_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    payment_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    mirror_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
