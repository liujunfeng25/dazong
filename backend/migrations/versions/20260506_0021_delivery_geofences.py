"""delivery_geofences 电子围栏

Revision ID: 20260506_0021
Revises: 20260506_0020
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260506_0021"
down_revision = "20260506_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "delivery_geofences" in insp.get_table_names():
        return
    op.create_table(
        "delivery_geofences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("delivery_id", sa.Integer(), nullable=False),
        sa.Column("fence_type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("geometry_json", sa.JSON(), nullable=True),
        sa.Column("center_lng", sa.Numeric(10, 6), nullable=True),
        sa.Column("center_lat", sa.Numeric(10, 6), nullable=True),
        sa.Column("radius_m", sa.Integer(), nullable=True),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["users.id"], name="fk_delivery_geofences_delivery_id_users"),
        sa.ForeignKeyConstraint(["client_id"], ["users.id"], name="fk_delivery_geofences_client_id_users"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_geofences_delivery_id", "delivery_geofences", ["delivery_id"], unique=False)
    op.create_index("ix_delivery_geofences_client_id", "delivery_geofences", ["client_id"], unique=False)


def downgrade() -> None:
    op.drop_table("delivery_geofences")
