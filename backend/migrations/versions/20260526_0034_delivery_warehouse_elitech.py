"""delivery warehouse elitech bindings

Revision ID: 20260526_0034
Revises: 20260526_0033
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260526_0034"
down_revision = "20260526_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_warehouse_elitech_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("elitech_sn", sa.String(length=64), nullable=False),
        sa.Column("device_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["delivery_warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("warehouse_id", name="uq_delivery_warehouse_elitech_warehouse_id"),
        sa.UniqueConstraint("elitech_sn", name="uq_delivery_warehouse_elitech_sn"),
    )
    op.create_index(
        "ix_delivery_warehouse_elitech_delivery_id",
        "delivery_warehouse_elitech_bindings",
        ["delivery_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_delivery_warehouse_elitech_delivery_id",
        table_name="delivery_warehouse_elitech_bindings",
    )
    op.drop_table("delivery_warehouse_elitech_bindings")
