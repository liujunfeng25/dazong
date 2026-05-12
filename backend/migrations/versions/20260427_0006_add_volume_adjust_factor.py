"""add product volume adjust factor

Revision ID: 20260427_0006
Revises: 20260427_0005
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0006"
down_revision = "20260427_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("volume_adjust_factor", sa.Numeric(6, 3), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "volume_adjust_factor")
