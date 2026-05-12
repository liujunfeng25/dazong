from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # 订单履约类通知挂食堂；NULL 表示学校级（招标/合约等）全校可见
    canteen_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("client_canteens.id"), nullable=True, index=True
    )
    object_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    object_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    route: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
