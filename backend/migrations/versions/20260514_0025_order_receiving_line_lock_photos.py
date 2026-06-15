"""add receiving line lock photo fields

Revision ID: 20260514_0025
Revises: 20260513_0024
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260514_0025"
down_revision = "20260513_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "order_receiving_lines" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("order_receiving_lines")}
    if "lock_photo_url" not in cols:
        op.add_column("order_receiving_lines", sa.Column("lock_photo_url", sa.String(length=1024), nullable=True))
    if "lock_photo_taken_at" not in cols:
        op.add_column("order_receiving_lines", sa.Column("lock_photo_taken_at", sa.DateTime(), nullable=True))
    if "lock_photo_device_id" not in cols:
        op.add_column("order_receiving_lines", sa.Column("lock_photo_device_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "order_receiving_lines" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("order_receiving_lines")}
    if "lock_photo_device_id" in cols:
        op.drop_column("order_receiving_lines", "lock_photo_device_id")
    if "lock_photo_taken_at" in cols:
        op.drop_column("order_receiving_lines", "lock_photo_taken_at")
    if "lock_photo_url" in cols:
        op.drop_column("order_receiving_lines", "lock_photo_url")
