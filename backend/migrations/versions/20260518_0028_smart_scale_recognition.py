"""smart scale recognition training tables

Revision ID: 20260518_0028
Revises: 20260518_0027
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260518_0028"
down_revision = "20260518_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smart_scale_recognition_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_ssr_categories_product_id_products"),
    )
    op.create_table(
        "smart_scale_recognition_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=False),
        sa.Column("angle", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("quality", sa.Float(), nullable=True),
        sa.Column("feature_json", sa.JSON(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["smart_scale_recognition_categories.id"], name="fk_ssr_samples_category_id_categories"),
    )
    op.create_index("ix_smart_scale_recognition_samples_category_id", "smart_scale_recognition_samples", ["category_id"])
    op.create_table(
        "smart_scale_recognition_packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("smart_scale_recognition_packages")
    op.drop_index("ix_smart_scale_recognition_samples_category_id", table_name="smart_scale_recognition_samples")
    op.drop_table("smart_scale_recognition_samples")
    op.drop_table("smart_scale_recognition_categories")
