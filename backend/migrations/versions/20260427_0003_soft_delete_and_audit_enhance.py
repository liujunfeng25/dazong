"""soft delete and audit enhancement

Revision ID: 20260427_0003
Revises: 20260427_0002
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0003"
down_revision = "20260427_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("categories", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_categories_is_deleted", "categories", ["is_deleted"], unique=False)

    op.add_column(
        "products",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("products", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_products_is_deleted", "products", ["is_deleted"], unique=False)

    op.add_column(
        "audit_logs",
        sa.Column("source_ip", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "audit_logs",
        sa.Column("before_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("after_json", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "after_json")
    op.drop_column("audit_logs", "before_json")
    op.drop_column("audit_logs", "source_ip")

    op.drop_index("ix_products_is_deleted", table_name="products")
    op.drop_column("products", "deleted_at")
    op.drop_column("products", "is_deleted")

    op.drop_index("ix_categories_is_deleted", table_name="categories")
    op.drop_column("categories", "deleted_at")
    op.drop_column("categories", "is_deleted")
