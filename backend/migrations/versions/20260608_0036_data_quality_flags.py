"""data quality flags for national price analytics

Revision ID: 20260608_0036
Revises: 20260529_0035
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260608_0036"
down_revision = "20260529_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_quality_flags",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("data_date", sa.Date(), nullable=False),
        sa.Column("sku_key", sa.String(length=640), nullable=False),
        sa.Column("district_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("goods_name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("cate_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cate_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("scate_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("anomaly_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("reason", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("corrected_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("review_note", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_quality_day_severity", "data_quality_flags", ["data_date", "severity", "status"])
    op.create_index("idx_quality_sku_day", "data_quality_flags", ["sku_key", "data_date"], mysql_length={"sku_key": 255})
    op.create_index(
        "uq_quality_flag",
        "data_quality_flags",
        ["data_date", "sku_key", "district_name", "anomaly_type"],
        unique=True,
        mysql_length={"sku_key": 255},
    )


def downgrade() -> None:
    op.drop_table("data_quality_flags")
