"""add product standard_type

Revision ID: 20260427_0004
Revises: 20260427_0003
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0004"
down_revision = "20260427_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "standard_type",
            sa.Enum("standard", "non_standard", name="products_standard_type_enum"),
            nullable=False,
            server_default="standard",
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "standard_type")
