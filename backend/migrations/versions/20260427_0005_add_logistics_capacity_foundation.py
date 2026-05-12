"""add logistics capacity foundation fields

Revision ID: 20260427_0005
Revises: 20260427_0004
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0005"
down_revision = "20260427_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("length_cm", sa.Numeric(10, 2), nullable=True))
    op.add_column("products", sa.Column("width_cm", sa.Numeric(10, 2), nullable=True))
    op.add_column("products", sa.Column("height_cm", sa.Numeric(10, 2), nullable=True))
    op.add_column("products", sa.Column("unit_weight_kg", sa.Numeric(10, 3), nullable=True))

    op.add_column("orders", sa.Column("total_volume_m3", sa.Numeric(12, 4), nullable=True))
    op.add_column("orders", sa.Column("total_weight_kg", sa.Numeric(12, 3), nullable=True))

    op.add_column(
        "deliveries", sa.Column("vehicle_capacity_volume_m3", sa.Float(), nullable=True)
    )
    op.add_column(
        "deliveries", sa.Column("vehicle_capacity_weight_kg", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("deliveries", "vehicle_capacity_weight_kg")
    op.drop_column("deliveries", "vehicle_capacity_volume_m3")
    op.drop_column("orders", "total_weight_kg")
    op.drop_column("orders", "total_volume_m3")
    op.drop_column("products", "unit_weight_kg")
    op.drop_column("products", "height_cm")
    op.drop_column("products", "width_cm")
    op.drop_column("products", "length_cm")
