from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class TenderItem(Base, TimestampMixin):
    __tablename__ = "tender_items"
    __table_args__ = (
        UniqueConstraint("tender_id", "product_id", name="uq_tender_item_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_price_snapshot: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
