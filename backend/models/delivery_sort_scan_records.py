from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeliverySortScanRecord(Base):
    __tablename__ = "delivery_sort_scan_records"
    __table_args__ = (
        UniqueConstraint("allocation_id", name="uq_delivery_sort_scan_records_allocation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("order_item_allocations.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    barcode_value: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    device_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
