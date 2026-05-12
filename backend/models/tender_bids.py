from sqlalchemy import Float, ForeignKey, Integer, JSON, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class TenderBid(Base, TimestampMixin):
    __tablename__ = "tender_bids"
    __table_args__ = (UniqueConstraint("tender_id", "delivery_id", name="uq_tender_bid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"), nullable=False)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    price_float_rate: Mapped[float] = mapped_column(Float, nullable=False)
    category_rates_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
