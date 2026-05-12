"""add order item allocation tables

Revision ID: 20260428_0016
Revises: 20260428_0015
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260428_0016"
down_revision = "20260428_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_item_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("allocation_batch_no", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("待确认", "已分配", "备货中", "已送达分拣场", "已出库"),
            nullable=False,
            server_default="已分配",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_item_allocations_order_id", "order_item_allocations", ["order_id"], unique=False)
    op.create_index(
        "ix_order_item_allocations_delivery_id",
        "order_item_allocations",
        ["delivery_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_item_allocations_supplier_id",
        "order_item_allocations",
        ["supplier_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_item_allocations_batch_no",
        "order_item_allocations",
        ["allocation_batch_no"],
        unique=False,
    )

    op.create_table(
        "order_item_status_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("allocation_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("operator_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["allocation_id"], ["order_item_allocations.id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_item_status_logs_allocation_id",
        "order_item_status_logs",
        ["allocation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_order_item_status_logs_allocation_id", table_name="order_item_status_logs")
    op.drop_table("order_item_status_logs")

    op.drop_index("ix_order_item_allocations_batch_no", table_name="order_item_allocations")
    op.drop_index("ix_order_item_allocations_supplier_id", table_name="order_item_allocations")
    op.drop_index("ix_order_item_allocations_delivery_id", table_name="order_item_allocations")
    op.drop_index("ix_order_item_allocations_order_id", table_name="order_item_allocations")
    op.drop_table("order_item_allocations")
