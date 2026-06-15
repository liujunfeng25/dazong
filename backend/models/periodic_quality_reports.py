from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class PeriodicQualityReport(Base, TimestampMixin):
    __tablename__ = "periodic_quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    revision_of_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("periodic_quality_reports.id", name="fk_pqr_revision_of"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    attachments_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    file_url: Mapped[str] = mapped_column(String(255), nullable=False)
    report_no: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("待审核", "已通过", "已驳回", "已失效"),
        nullable=False,
        default="待审核",
        index=True,
    )
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
