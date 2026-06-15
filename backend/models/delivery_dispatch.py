from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeliveryDispatchTrip(Base):
    __tablename__ = "delivery_dispatch_trips"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id",
            "planning_date",
            "route_no",
            name="uq_dispatch_trip_route_no",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    planning_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="smart_route")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="待发车", index=True)
    depart_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    vehicle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("delivery_vehicles.id"), nullable=True, index=True)
    vehicle_no: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    driver_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    departure_time: Mapped[str] = mapped_column(String(16), nullable=False, default="")

    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_allocations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_loaded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    distance_km: Mapped[Optional[float]] = mapped_column(Float)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    load_weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    load_volume_m3: Mapped[Optional[float]] = mapped_column(Float)
    route_path_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    risk_alerts_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    planning_snapshot_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    exception_summary_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)

    departed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DeliveryDispatchStop(Base):
    __tablename__ = "delivery_dispatch_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("delivery_dispatch_trips.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    client_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    canteen_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    expected_delivery_date: Mapped[Optional[date]] = mapped_column(Date)
    expected_delivery_slot: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    planned_arrive_time: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    planned_leave_time: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="待发车", index=True)
    affected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DeliveryDispatchItem(Base):
    __tablename__ = "delivery_dispatch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("delivery_dispatch_trips.id"), nullable=False, index=True)
    stop_id: Mapped[int] = mapped_column(ForeignKey("delivery_dispatch_stops.id"), nullable=False, index=True)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("order_item_allocations.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    spec_unit: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    supplier_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="待装车", index=True)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    reason_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attachments_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    loaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
