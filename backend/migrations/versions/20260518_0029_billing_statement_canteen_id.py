"""add billing_statements.canteen_id for canteen-level billing

Revision ID: 20260518_0029
Revises: 20260518_0028
Create Date: 2026-05-18

把账单的对账粒度从「学校（client user）级」改为「食堂级」。
- 在 billing_statements 加 canteen_id（nullable，索引）
- 历史数据可选回填：从 source_snapshot_json.order_ids 的首个 order 反查 orders.canteen_id
- 业务规则：一份订单只送一个食堂（用户确认）
"""

from alembic import op
import sqlalchemy as sa


revision = "20260518_0029"
down_revision = "20260518_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "billing_statements" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("billing_statements")}
    if "canteen_id" not in cols:
        op.add_column("billing_statements", sa.Column("canteen_id", sa.Integer(), nullable=True))
        op.create_index("idx_billing_statements_canteen_id", "billing_statements", ["canteen_id"])
        op.create_foreign_key(
            "fk_billing_statements_canteen",
            "billing_statements",
            "client_canteens",
            ["canteen_id"],
            ["id"],
        )
    # 历史数据回填：从 source_snapshot_json.order_ids[0] 反查订单的 canteen_id
    conn.execute(
        sa.text(
            "UPDATE billing_statements bs "
            "JOIN orders o ON o.id = CAST(JSON_UNQUOTE(JSON_EXTRACT(bs.source_snapshot_json, '$.order_ids[0]')) AS UNSIGNED) "
            "SET bs.canteen_id = o.canteen_id "
            "WHERE bs.canteen_id IS NULL AND o.canteen_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "billing_statements" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("billing_statements")}
    if "canteen_id" in cols:
        try:
            op.drop_constraint("fk_billing_statements_canteen", "billing_statements", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_index("idx_billing_statements_canteen_id", "billing_statements")
        except Exception:
            pass
        op.drop_column("billing_statements", "canteen_id")
