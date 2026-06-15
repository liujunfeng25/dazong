"""add delivery dispatch trips

Revision ID: 20260520_0031
Revises: 20260519_0030
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260520_0031"
down_revision = "20260519_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_dispatch_trips",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_no", sa.String(length=64), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("planning_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("depart_mode", sa.String(length=32), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=True),
        sa.Column("vehicle_no", sa.String(length=32), nullable=False),
        sa.Column("driver_name", sa.String(length=64), nullable=False),
        sa.Column("departure_time", sa.String(length=16), nullable=False),
        sa.Column("total_orders", sa.Integer(), nullable=False),
        sa.Column("total_allocations", sa.Integer(), nullable=False),
        sa.Column("ready_count", sa.Integer(), nullable=False),
        sa.Column("blocked_count", sa.Integer(), nullable=False),
        sa.Column("not_loaded_count", sa.Integer(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("load_weight_kg", sa.Float(), nullable=True),
        sa.Column("load_volume_m3", sa.Float(), nullable=True),
        sa.Column("route_path_json", sa.JSON(), nullable=False),
        sa.Column("risk_alerts_json", sa.JSON(), nullable=False),
        sa.Column("planning_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("exception_summary_json", sa.JSON(), nullable=False),
        sa.Column("departed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["delivery_vehicles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_dispatch_trips_route_no", "delivery_dispatch_trips", ["route_no"], unique=False)
    op.create_index("ix_delivery_dispatch_trips_delivery_id", "delivery_dispatch_trips", ["delivery_id"], unique=False)
    op.create_index("ix_delivery_dispatch_trips_planning_date", "delivery_dispatch_trips", ["planning_date"], unique=False)
    op.create_index("ix_delivery_dispatch_trips_status", "delivery_dispatch_trips", ["status"], unique=False)
    op.create_index("ix_delivery_dispatch_trips_vehicle_id", "delivery_dispatch_trips", ["vehicle_id"], unique=False)

    op.create_table(
        "delivery_dispatch_stops",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("client_name", sa.String(length=128), nullable=False),
        sa.Column("canteen_name", sa.String(length=128), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("expected_delivery_slot", sa.String(length=32), nullable=False),
        sa.Column("planned_arrive_time", sa.String(length=32), nullable=False),
        sa.Column("planned_leave_time", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("affected", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["trip_id"], ["delivery_dispatch_trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_dispatch_stops_trip_id", "delivery_dispatch_stops", ["trip_id"], unique=False)
    op.create_index("ix_delivery_dispatch_stops_order_id", "delivery_dispatch_stops", ["order_id"], unique=False)
    op.create_index("ix_delivery_dispatch_stops_status", "delivery_dispatch_stops", ["status"], unique=False)

    op.create_table(
        "delivery_dispatch_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("stop_id", sa.Integer(), nullable=False),
        sa.Column("allocation_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("spec_unit", sa.String(length=128), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("supplier_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("reason_detail", sa.Text(), nullable=False),
        sa.Column("attachments_json", sa.JSON(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["allocation_id"], ["order_item_allocations.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["stop_id"], ["delivery_dispatch_stops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["trip_id"], ["delivery_dispatch_trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_dispatch_items_trip_id", "delivery_dispatch_items", ["trip_id"], unique=False)
    op.create_index("ix_delivery_dispatch_items_stop_id", "delivery_dispatch_items", ["stop_id"], unique=False)
    op.create_index("ix_delivery_dispatch_items_allocation_id", "delivery_dispatch_items", ["allocation_id"], unique=False)
    op.create_index("ix_delivery_dispatch_items_order_id", "delivery_dispatch_items", ["order_id"], unique=False)
    op.create_index("ix_delivery_dispatch_items_supplier_id", "delivery_dispatch_items", ["supplier_id"], unique=False)
    op.create_index("ix_delivery_dispatch_items_product_id", "delivery_dispatch_items", ["product_id"], unique=False)
    op.create_index("ix_delivery_dispatch_items_status", "delivery_dispatch_items", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_delivery_dispatch_items_status", table_name="delivery_dispatch_items")
    op.drop_index("ix_delivery_dispatch_items_product_id", table_name="delivery_dispatch_items")
    op.drop_index("ix_delivery_dispatch_items_supplier_id", table_name="delivery_dispatch_items")
    op.drop_index("ix_delivery_dispatch_items_order_id", table_name="delivery_dispatch_items")
    op.drop_index("ix_delivery_dispatch_items_allocation_id", table_name="delivery_dispatch_items")
    op.drop_index("ix_delivery_dispatch_items_stop_id", table_name="delivery_dispatch_items")
    op.drop_index("ix_delivery_dispatch_items_trip_id", table_name="delivery_dispatch_items")
    op.drop_table("delivery_dispatch_items")

    op.drop_index("ix_delivery_dispatch_stops_status", table_name="delivery_dispatch_stops")
    op.drop_index("ix_delivery_dispatch_stops_order_id", table_name="delivery_dispatch_stops")
    op.drop_index("ix_delivery_dispatch_stops_trip_id", table_name="delivery_dispatch_stops")
    op.drop_table("delivery_dispatch_stops")

    op.drop_index("ix_delivery_dispatch_trips_vehicle_id", table_name="delivery_dispatch_trips")
    op.drop_index("ix_delivery_dispatch_trips_status", table_name="delivery_dispatch_trips")
    op.drop_index("ix_delivery_dispatch_trips_planning_date", table_name="delivery_dispatch_trips")
    op.drop_index("ix_delivery_dispatch_trips_delivery_id", table_name="delivery_dispatch_trips")
    op.drop_index("ix_delivery_dispatch_trips_route_no", table_name="delivery_dispatch_trips")
    op.drop_table("delivery_dispatch_trips")
