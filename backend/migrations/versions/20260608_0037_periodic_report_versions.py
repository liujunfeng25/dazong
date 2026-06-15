"""periodic quality report versions

Revision ID: 20260608_0037
Revises: 20260608_0036
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260608_0037"
down_revision = "20260608_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "periodic_quality_reports" not in set(insp.get_table_names()):
        return
    columns = {c["name"] for c in insp.get_columns("periodic_quality_reports")}
    if "revision_of_id" not in columns:
        op.add_column(
            "periodic_quality_reports",
            sa.Column("revision_of_id", sa.Integer(), nullable=True),
        )
    foreign_keys = {
        fk.get("name")
        for fk in insp.get_foreign_keys("periodic_quality_reports")
        if fk.get("constrained_columns") == ["revision_of_id"]
    }
    if not foreign_keys:
        op.create_foreign_key(
            "fk_pqr_revision_of",
            "periodic_quality_reports",
            "periodic_quality_reports",
            ["revision_of_id"],
            ["id"],
        )
    if "version" not in columns:
        op.add_column(
            "periodic_quality_reports",
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
    op.execute(
        "ALTER TABLE periodic_quality_reports "
        "MODIFY COLUMN status ENUM('待审核','已通过','已驳回','已失效') "
        "NOT NULL DEFAULT '待审核'"
    )
    indexes = {i["name"] for i in insp.get_indexes("periodic_quality_reports")}
    if "ix_periodic_quality_reports_revision_of_id" not in indexes:
        op.create_index(
            "ix_periodic_quality_reports_revision_of_id",
            "periodic_quality_reports",
            ["revision_of_id"],
        )
    if "ix_periodic_report_pair_status_period" not in indexes:
        op.create_index(
            "ix_periodic_report_pair_status_period",
            "periodic_quality_reports",
            ["provider_id", "product_id", "status", "valid_from", "valid_to"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "periodic_quality_reports" not in set(insp.get_table_names()):
        return
    indexes = {i["name"] for i in insp.get_indexes("periodic_quality_reports")}
    if "ix_periodic_report_pair_status_period" in indexes:
        op.drop_index(
            "ix_periodic_report_pair_status_period",
            table_name="periodic_quality_reports",
        )
    op.execute(
        "UPDATE periodic_quality_reports SET status='已驳回' WHERE status='已失效'"
    )
    op.execute(
        "ALTER TABLE periodic_quality_reports "
        "MODIFY COLUMN status ENUM('待审核','已通过','已驳回') "
        "NOT NULL DEFAULT '待审核'"
    )
    columns = {c["name"] for c in insp.get_columns("periodic_quality_reports")}
    if "version" in columns:
        op.drop_column("periodic_quality_reports", "version")
    if "revision_of_id" in columns:
        if "ix_periodic_quality_reports_revision_of_id" in indexes:
            op.drop_index(
                "ix_periodic_quality_reports_revision_of_id",
                table_name="periodic_quality_reports",
            )
        foreign_keys = {
            fk.get("name")
            for fk in insp.get_foreign_keys("periodic_quality_reports")
            if fk.get("constrained_columns") == ["revision_of_id"]
        }
        for name in foreign_keys:
            if name:
                op.drop_constraint(
                    name,
                    "periodic_quality_reports",
                    type_="foreignkey",
                )
        op.drop_column("periodic_quality_reports", "revision_of_id")
