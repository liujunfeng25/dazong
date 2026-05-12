"""add order route planning fields

Revision ID: 20260430_0019
Revises: 20260430_0018
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20260430_0019"
down_revision = "20260430_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_address", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("delivery_lng", sa.Numeric(10, 6), nullable=True))
    op.add_column("orders", sa.Column("delivery_lat", sa.Numeric(10, 6), nullable=True))
    op.add_column("orders", sa.Column("expected_delivery_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("expected_delivery_slot", sa.String(length=32), nullable=True))
    op.add_column(
        "orders",
        sa.Column("service_duration_min", sa.Integer(), nullable=False, server_default="30"),
    )


def downgrade() -> None:
    op.drop_column("orders", "service_duration_min")
    op.drop_column("orders", "expected_delivery_slot")
    op.drop_column("orders", "expected_delivery_date")
    op.drop_column("orders", "delivery_lat")
    op.drop_column("orders", "delivery_lng")
    op.drop_column("orders", "delivery_address")
