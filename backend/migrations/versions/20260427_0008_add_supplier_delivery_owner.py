"""add supplier owner delivery id

Revision ID: 20260427_0008
Revises: 20260427_0007
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0008"
down_revision = "20260427_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("supplier_delivery_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_supplier_delivery_id_users",
        "users",
        "users",
        ["supplier_delivery_id"],
        ["id"],
    )
    op.create_index(
        "ix_users_supplier_delivery_id", "users", ["supplier_delivery_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_users_supplier_delivery_id", table_name="users")
    op.drop_constraint("fk_users_supplier_delivery_id_users", "users", type_="foreignkey")
    op.drop_column("users", "supplier_delivery_id")
