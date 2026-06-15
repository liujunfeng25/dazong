"""add delivery sort scan records

Revision ID: 20260519_0030
Revises: 20260518_0029
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260519_0030"
down_revision = "20260518_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_sort_scan_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("allocation_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("operator_id", sa.Integer(), nullable=False),
        sa.Column("barcode_value", sa.String(length=128), nullable=False),
        sa.Column("device_code", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("scanned_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["allocation_id"], ["order_item_allocations.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("allocation_id", name="uq_delivery_sort_scan_records_allocation_id"),
    )
    op.create_index(
        "ix_delivery_sort_scan_records_allocation_id",
        "delivery_sort_scan_records",
        ["allocation_id"],
        unique=False,
    )
    op.create_index(
        "ix_delivery_sort_scan_records_order_id",
        "delivery_sort_scan_records",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "ix_delivery_sort_scan_records_delivery_id",
        "delivery_sort_scan_records",
        ["delivery_id"],
        unique=False,
    )
    op.create_index(
        "ix_delivery_sort_scan_records_operator_id",
        "delivery_sort_scan_records",
        ["operator_id"],
        unique=False,
    )
    op.create_index(
        "ix_delivery_sort_scan_records_barcode_value",
        "delivery_sort_scan_records",
        ["barcode_value"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_delivery_sort_scan_records_barcode_value", table_name="delivery_sort_scan_records")
    op.drop_index("ix_delivery_sort_scan_records_operator_id", table_name="delivery_sort_scan_records")
    op.drop_index("ix_delivery_sort_scan_records_delivery_id", table_name="delivery_sort_scan_records")
    op.drop_index("ix_delivery_sort_scan_records_order_id", table_name="delivery_sort_scan_records")
    op.drop_index("ix_delivery_sort_scan_records_allocation_id", table_name="delivery_sort_scan_records")
    op.drop_table("delivery_sort_scan_records")
