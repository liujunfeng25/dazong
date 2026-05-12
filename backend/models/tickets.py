from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    type: Mapped[str] = mapped_column(
        Enum("异常订单", "售后投诉", "配送异常"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("待处理", "处理中", "已关闭"), nullable=False, default="待处理"
    )
    # 售后投诉支持图片附件（最多 5 张），数组保存 URL；其他工单类型一般为空
    attachments_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # 售后投诉流转：自动派发配送商 → 配送商意见 → 运营结案
    assigned_delivery_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    delivery_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivery_responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    operation_resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    operation_resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    flow_logs_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
