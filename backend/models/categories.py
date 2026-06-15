from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 一级分类：配送商投标时每个分类的上浮率不得超过该上限（与投标页 float_rate 同单位，如 0.05 表示 5%）
    max_float_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 分类图片：MinIO 图片 URL 或 "emoji:🥬" token；空则前端按分类名自动映射 emoji（呈现到客户端移动端）
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
