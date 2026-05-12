from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class TenderBidItem(Base, TimestampMixin):
    __tablename__ = "tender_bid_items"
    __table_args__ = (
        UniqueConstraint("tender_bid_id", "product_id", name="uq_tender_bid_item_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tender_bid_id: Mapped[int] = mapped_column(ForeignKey("tender_bids.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    float_rate: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    calc_unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
