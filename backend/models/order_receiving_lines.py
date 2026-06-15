from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OrderReceivingLine(Base):
    """客户端收货称重：逐行草稿与确认快照（整单收货前可撤销确认）。"""

    __tablename__ = "order_receiving_lines"
    __table_args__ = (UniqueConstraint("order_id", "line_index", name="uq_order_receiving_line_order_line"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    line_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    draft_kg: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    confirmed_kg: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    confirmed_quantity: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    confirmed_unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sample_kg: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    confirmed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    # 实收 < 下单（折算 kg）时必填，整单签字收货后据此生成退货单明细
    shortage_reason_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    shortage_reason_detail: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    shortage_ordered_kg: Mapped[Optional[float]] = mapped_column(Numeric(14, 4), nullable=True)
    shortage_delta_kg: Mapped[Optional[float]] = mapped_column(Numeric(14, 4), nullable=True)
    # 智能收货端锁定读数时的秤盘商品留痕照片；用于历史追溯，不能只依赖 Pad 本机缓存
    lock_photo_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    lock_photo_taken_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lock_photo_device_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    return_photo_urls_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    return_note: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
