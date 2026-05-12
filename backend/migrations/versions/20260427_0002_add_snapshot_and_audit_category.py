"""add snapshots and audit category

Revision ID: 20260427_0002
Revises: 20260427_0001
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0002"
down_revision = "20260427_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("items_snapshot_json", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "bills",
        sa.Column("order_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("category", sa.String(length=40), nullable=False, server_default="system"),
    )

    op.create_index("ix_audit_logs_category", "audit_logs", ["category"], unique=False)
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_category", table_name="audit_logs")
    op.drop_column("audit_logs", "category")
    op.drop_column("bills", "order_snapshot_json")
    op.drop_column("orders", "items_snapshot_json")
