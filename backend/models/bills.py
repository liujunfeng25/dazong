from sqlalchemy import Enum, ForeignKey, Integer, JSON, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Bill(Base, TimestampMixin):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("client", "supplier", "delivery"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # 出账时固化订单核心信息，确保后续数据变更不影响账务追溯
    order_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    bill_type: Mapped[str] = mapped_column(Enum("应付", "应收"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("待结算", "已结算"), nullable=False, default="待结算"
    )
