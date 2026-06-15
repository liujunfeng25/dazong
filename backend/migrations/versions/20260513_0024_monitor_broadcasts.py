"""add monitor broadcasts and notification read_at

Revision ID: 20260513_0024
Revises: 20260511_0023
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260513_0024"
down_revision = "20260511_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitor_broadcasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=24), nullable=False),
        sa.Column("target_type", sa.String(length=24), nullable=False),
        sa.Column("target_summary", sa.String(length=255), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitor_broadcasts_id", "monitor_broadcasts", ["id"], unique=False)
    op.create_index("ix_monitor_broadcasts_sender_user_id", "monitor_broadcasts", ["sender_user_id"], unique=False)
    op.add_column("notifications", sa.Column("read_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "read_at")
    op.drop_index("ix_monitor_broadcasts_sender_user_id", table_name="monitor_broadcasts")
    op.drop_index("ix_monitor_broadcasts_id", table_name="monitor_broadcasts")
    op.drop_table("monitor_broadcasts")
