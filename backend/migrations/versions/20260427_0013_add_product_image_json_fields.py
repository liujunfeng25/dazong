"""add product image json fields

Revision ID: 20260427_0013
Revises: 20260427_0012
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0013"
down_revision = "20260427_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("detail_images_json", sa.JSON(), nullable=True))
    op.add_column("products", sa.Column("image_list_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "image_list_json")
    op.drop_column("products", "detail_images_json")
