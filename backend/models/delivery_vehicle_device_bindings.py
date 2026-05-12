from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeliveryVehicleDeviceBinding(Base):
    __tablename__ = "delivery_vehicle_device_bindings"
    __table_args__ = (
        # 同一设备同一时间只能绑定一辆车（与业务规则一致；旧版仅约束 vehicle+device 组合，无法禁止一车多绑）
        UniqueConstraint("device_id", name="uq_delivery_vehicle_device_binding_device_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("delivery_vehicles.id"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("delivery_devices.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
