"""add supplier address and coordinates

Revision ID: 20260428_0014
Revises: 20260427_0013
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260428_0014"
down_revision = "20260427_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("address", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("users", sa.Column("lng", sa.Numeric(10, 6), nullable=True))
    op.add_column("users", sa.Column("lat", sa.Numeric(10, 6), nullable=True))
    op.alter_column("users", "address", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "lat")
    op.drop_column("users", "lng")
    op.drop_column("users", "address")
