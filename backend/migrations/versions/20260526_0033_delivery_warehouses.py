"""delivery warehouses + warehouse-device bindings

Revision ID: 20260526_0033
Revises: 20260525_0032
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260526_0033"
down_revision = "20260525_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_warehouses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("address", sa.String(length=256), nullable=True),
        sa.Column("lng", sa.Numeric(10, 6), nullable=False),
        sa.Column("lat", sa.Numeric(10, 6), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_id", "name", name="uq_delivery_warehouse_name_per_delivery"),
    )
    op.create_index("ix_delivery_warehouses_delivery_id", "delivery_warehouses", ["delivery_id"], unique=False)

    op.create_table(
        "delivery_warehouse_device_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["delivery_warehouses.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["delivery_devices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", name="uq_delivery_warehouse_binding_device_id"),
    )
    op.create_index(
        "ix_delivery_warehouse_bindings_warehouse_id",
        "delivery_warehouse_device_bindings",
        ["warehouse_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_delivery_warehouse_bindings_warehouse_id", table_name="delivery_warehouse_device_bindings")
    op.drop_table("delivery_warehouse_device_bindings")
    op.drop_index("ix_delivery_warehouses_delivery_id", table_name="delivery_warehouses")
    op.drop_table("delivery_warehouses")
