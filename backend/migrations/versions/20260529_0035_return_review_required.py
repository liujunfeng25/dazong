"""delivery return review switch

Revision ID: 20260529_0035
Revises: 20260526_0034
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_0035"
down_revision = "20260526_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "order_returns",
        "status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default=sa.text("'confirmed'"),
    )
    op.add_column(
        "users",
        sa.Column("return_review_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("order_returns", sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
    op.add_column("order_returns", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("order_returns", sa.Column("review_note", sa.String(length=1000), nullable=True))
    op.create_foreign_key(
        "fk_order_returns_reviewed_by_user",
        "order_returns",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_order_returns_reviewed_by_user", "order_returns", type_="foreignkey")
    op.drop_column("order_returns", "review_note")
    op.drop_column("order_returns", "reviewed_at")
    op.drop_column("order_returns", "reviewed_by_user_id")
    op.drop_column("users", "return_review_required")
    op.alter_column(
        "order_returns",
        "status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default=sa.text("'confirmed'"),
    )
