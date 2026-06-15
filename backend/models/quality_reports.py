from typing import Any, Optional

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class QualityReport(Base, TimestampMixin):
    __tablename__ = "quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    # 关联到具体分单行；旧数据可能为空，前端需按 (order_id, product_id, supplier_id) 兜底匹配
    allocation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("order_item_allocations.id"), nullable=True, index=True
    )
    # 多图时存除首张外的 URL 列表；单图时为 NULL，仅用 file_url
    attachments_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    file_url: Mapped[str] = mapped_column(String(255), nullable=False)
    report_no: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("待审核", "已通过"), nullable=False, default="待审核"
    )
