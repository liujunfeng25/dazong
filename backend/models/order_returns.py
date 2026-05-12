from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OrderReturn(Base):
    """收货少收后生成的退货单头（与订单一对一生成，幂等键防重复）。"""

    __tablename__ = "order_returns"
    __table_args__ = (UniqueConstraint("order_id", "source", name="uq_order_returns_order_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    return_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="receive_shortage")
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    receive_idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class OrderReturnLine(Base):
    """退货单明细：少收数量与原因（与称重行一一对应）。"""

    __tablename__ = "order_return_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_return_id: Mapped[int] = mapped_column(ForeignKey("order_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    line_index: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ordered_kg: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    received_kg: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    delta_kg: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_detail: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
