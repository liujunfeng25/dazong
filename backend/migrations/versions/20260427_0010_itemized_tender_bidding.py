"""itemized tender bidding

Revision ID: 20260427_0010
Revises: 20260427_0009
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0010"
down_revision = "20260427_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tender_bids", sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.create_table(
        "tender_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tender_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name_snapshot", sa.String(length=120), nullable=False),
        sa.Column("unit_snapshot", sa.String(length=20), nullable=False),
        sa.Column("reference_price_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["tender_id"], ["tenders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tender_id", "product_id", name="uq_tender_item_product"),
    )
    op.create_table(
        "tender_bid_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tender_bid_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("float_rate", sa.Numeric(8, 4), nullable=False),
        sa.Column("calc_unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["tender_bid_id"], ["tender_bids.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tender_bid_id", "product_id", name="uq_tender_bid_item_product"),
    )


def downgrade() -> None:
    op.drop_table("tender_bid_items")
    op.drop_table("tender_items")
    op.drop_column("tender_bids", "total_amount")
