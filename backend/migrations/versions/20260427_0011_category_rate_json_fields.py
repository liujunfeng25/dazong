"""add category rate json fields

Revision ID: 20260427_0011
Revises: 20260427_0010
Create Date: 2026-04-27 16:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260427_0011"
down_revision = "20260427_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tender_bids",
        sa.Column("category_rates_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "contracts",
        sa.Column("category_rates_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("tender_bids", "category_rates_json", server_default=None)
    op.alter_column("contracts", "category_rates_json", server_default=None)


def downgrade() -> None:
    op.drop_column("contracts", "category_rates_json")
    op.drop_column("tender_bids", "category_rates_json")
