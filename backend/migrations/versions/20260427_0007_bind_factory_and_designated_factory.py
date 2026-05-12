"""bind factory to client and designated factory fields

Revision ID: 20260427_0007
Revises: 20260427_0006
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0007"
down_revision = "20260427_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bind_client_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_bind_client_id_users", "users", "users", ["bind_client_id"], ["id"]
    )
    op.create_index("ix_users_bind_client_id", "users", ["bind_client_id"], unique=False)

    op.add_column(
        "products",
        sa.Column(
            "is_designated_factory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("products", sa.Column("designated_factory_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_products_designated_factory_id_users",
        "products",
        "users",
        ["designated_factory_id"],
        ["id"],
    )
    op.create_index(
        "ix_products_designated_factory_id", "products", ["designated_factory_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_products_designated_factory_id", table_name="products")
    op.drop_constraint("fk_products_designated_factory_id_users", "products", type_="foreignkey")
    op.drop_column("products", "designated_factory_id")
    op.drop_column("products", "is_designated_factory")

    op.drop_index("ix_users_bind_client_id", table_name="users")
    op.drop_constraint("fk_users_bind_client_id_users", "users", type_="foreignkey")
    op.drop_column("users", "bind_client_id")
