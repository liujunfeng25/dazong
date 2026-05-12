"""orders 表补充 receive_signatures_json（智能秤双签）

Revision ID: 20260506_0020
Revises: 20260430_0019
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260506_0020"
down_revision = "20260430_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "orders" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("orders")}
    if "receive_signatures_json" in cols:
        return
    op.add_column(
        "orders",
        sa.Column("receive_signatures_json", sa.JSON(), nullable=True, comment="智能秤双签"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "orders" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("orders")}
    if "receive_signatures_json" not in cols:
        return
    op.drop_column("orders", "receive_signatures_json")
