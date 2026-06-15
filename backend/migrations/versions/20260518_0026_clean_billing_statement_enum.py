"""clean unused billing_statements.status enum values

Revision ID: 20260518_0026
Revises: 20260514_0025
Create Date: 2026-05-18

去掉「待出账」「已作废」两个从未被代码写入的枚举值，把默认值改为「待确认」。
迁移前若发现历史残留行，统一矫正为「待确认」。
"""

from alembic import op
import sqlalchemy as sa


revision = "20260518_0026"
down_revision = "20260514_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "billing_statements" not in insp.get_table_names():
        return
    # 兜底：若有历史残留的「待出账」/「已作废」记录，先矫正为「待确认」
    conn.execute(sa.text("UPDATE billing_statements SET status='待确认' WHERE status IN ('待出账','已作废')"))
    conn.execute(
        sa.text(
            "ALTER TABLE billing_statements "
            "MODIFY status ENUM('待确认','已确认','部分结清','已结清') "
            "NOT NULL DEFAULT '待确认'"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "billing_statements" not in insp.get_table_names():
        return
    conn.execute(
        sa.text(
            "ALTER TABLE billing_statements "
            "MODIFY status ENUM('待出账','待确认','已确认','部分结清','已结清','已作废') "
            "NOT NULL DEFAULT '待出账'"
        )
    )
