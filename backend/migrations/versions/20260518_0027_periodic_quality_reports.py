"""add periodic quality reports

Revision ID: 20260518_0027
Revises: 20260518_0026
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260518_0027"
down_revision = "20260518_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "products" in tables:
        cols = {c["name"] for c in insp.get_columns("products")}
        if "quality_report_mode" not in cols:
            op.add_column(
                "products",
                sa.Column(
                    "quality_report_mode",
                    sa.Enum("batch", "periodic"),
                    nullable=False,
                    server_default="batch",
                ),
            )
    if "periodic_quality_reports" not in tables:
        op.create_table(
            "periodic_quality_reports",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("provider_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("valid_from", sa.Date(), nullable=False),
            sa.Column("valid_to", sa.Date(), nullable=False),
            sa.Column("attachments_json", sa.JSON(), nullable=True),
            sa.Column("file_url", sa.String(length=255), nullable=False),
            sa.Column("report_no", sa.String(length=64), nullable=False),
            sa.Column("status", sa.Enum("待审核", "已通过", "已驳回"), nullable=False, server_default="待审核"),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("reject_reason", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["provider_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_periodic_quality_reports_provider_id", "periodic_quality_reports", ["provider_id"])
        op.create_index("ix_periodic_quality_reports_product_id", "periodic_quality_reports", ["product_id"])
        op.create_index("ix_periodic_quality_reports_status", "periodic_quality_reports", ["status"])
        op.create_index("ix_periodic_quality_reports_valid_from", "periodic_quality_reports", ["valid_from"])
        op.create_index("ix_periodic_quality_reports_valid_to", "periodic_quality_reports", ["valid_to"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "periodic_quality_reports" in tables:
        op.drop_index("ix_periodic_quality_reports_valid_to", table_name="periodic_quality_reports")
        op.drop_index("ix_periodic_quality_reports_valid_from", table_name="periodic_quality_reports")
        op.drop_index("ix_periodic_quality_reports_status", table_name="periodic_quality_reports")
        op.drop_index("ix_periodic_quality_reports_product_id", table_name="periodic_quality_reports")
        op.drop_index("ix_periodic_quality_reports_provider_id", table_name="periodic_quality_reports")
        op.drop_table("periodic_quality_reports")
    if "products" in tables:
        cols = {c["name"] for c in insp.get_columns("products")}
        if "quality_report_mode" in cols:
            op.drop_column("products", "quality_report_mode")
