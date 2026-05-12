from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SupplierProductQuote(Base, TimestampMixin):
    __tablename__ = "supplier_product_quotes"
    __table_args__ = (
        UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product_quotes_supplier_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quote_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    remark: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
