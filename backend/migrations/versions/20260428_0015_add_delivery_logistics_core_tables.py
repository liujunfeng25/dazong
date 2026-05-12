"""add delivery logistics core tables

Revision ID: 20260428_0015
Revises: 20260428_0014
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260428_0015"
down_revision = "20260428_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_vehicles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_no", sa.String(length=32), nullable=False),
        sa.Column("driver_name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("capacity_weight_kg", sa.Numeric(12, 3), nullable=True),
        sa.Column("capacity_volume_m3", sa.Numeric(12, 4), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_id", "vehicle_no", name="uq_delivery_vehicle_no"),
    )
    op.create_index("ix_delivery_vehicles_delivery_id", "delivery_vehicles", ["delivery_id"], unique=False)

    op.create_table(
        "delivery_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("device_type", sa.String(length=16), nullable=False),
        sa.Column("vendor", sa.String(length=16), nullable=False),
        sa.Column("device_code", sa.String(length=128), nullable=False),
        sa.Column("device_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("channel_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_payload_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vendor",
            "device_code",
            "channel_no",
            name="uq_delivery_device_vendor_code_ch",
        ),
    )
    op.create_index("ix_delivery_devices_delivery_id", "delivery_devices", ["delivery_id"], unique=False)
    op.create_index("ix_delivery_devices_vendor_type", "delivery_devices", ["vendor", "device_type"], unique=False)

    op.create_table(
        "delivery_vehicle_device_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["delivery_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["delivery_vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "device_id", name="uq_vehicle_device_binding"),
    )
    op.create_index(
        "ix_delivery_vehicle_device_bindings_vehicle_id",
        "delivery_vehicle_device_bindings",
        ["vehicle_id"],
        unique=False,
    )
    op.create_index(
        "ix_delivery_vehicle_device_bindings_device_id",
        "delivery_vehicle_device_bindings",
        ["device_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_delivery_vehicle_device_bindings_device_id", table_name="delivery_vehicle_device_bindings")
    op.drop_index("ix_delivery_vehicle_device_bindings_vehicle_id", table_name="delivery_vehicle_device_bindings")
    op.drop_table("delivery_vehicle_device_bindings")

    op.drop_index("ix_delivery_devices_vendor_type", table_name="delivery_devices")
    op.drop_index("ix_delivery_devices_delivery_id", table_name="delivery_devices")
    op.drop_table("delivery_devices")

    op.drop_index("ix_delivery_vehicles_delivery_id", table_name="delivery_vehicles")
    op.drop_table("delivery_vehicles")
