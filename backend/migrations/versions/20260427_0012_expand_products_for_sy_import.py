"""expand products fields for sy import

Revision ID: 20260427_0012
Revises: 20260427_0011
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0012"
down_revision = "20260427_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("goods_sn", sa.String(length=64), nullable=True))
    op.add_column("products", sa.Column("brand", sa.String(length=120), nullable=True))
    op.add_column("products", sa.Column("expire_date", sa.String(length=120), nullable=True))
    op.add_column("products", sa.Column("manufacturer", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("model", sa.String(length=120), nullable=True))
    op.add_column("products", sa.Column("source", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("attr", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("level", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("limit_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("products", sa.Column("discount_rate", sa.Numeric(8, 4), nullable=True))
    op.add_column("products", sa.Column("float_rate_max", sa.Numeric(8, 4), nullable=True))
    op.add_column("products", sa.Column("float_rate_min", sa.Numeric(8, 4), nullable=True))
    op.add_column("products", sa.Column("supplier_id", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("supplier_name", sa.String(length=120), nullable=True))
    op.add_column("products", sa.Column("goods_channel", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("finance_code", sa.String(length=120), nullable=True))
    op.add_column("products", sa.Column("finance_rate", sa.Numeric(8, 4), nullable=True))
    op.add_column("products", sa.Column("number", sa.String(length=120), nullable=True))
    op.add_column("products", sa.Column("weight", sa.Numeric(10, 3), nullable=True))
    op.add_column("products", sa.Column("remark", sa.String(length=500), nullable=True))
    op.add_column("products", sa.Column("logo", sa.String(length=512), nullable=True))
    op.add_column("products", sa.Column("slogo", sa.String(length=512), nullable=True))
    op.add_column("products", sa.Column("external_url", sa.String(length=512), nullable=True))

    op.create_index("ix_products_goods_sn", "products", ["goods_sn"], unique=False)
    op.create_index("ix_products_supplier_id", "products", ["supplier_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_products_supplier_id", table_name="products")
    op.drop_index("ix_products_goods_sn", table_name="products")
    op.drop_column("products", "external_url")
    op.drop_column("products", "slogo")
    op.drop_column("products", "logo")
    op.drop_column("products", "remark")
    op.drop_column("products", "weight")
    op.drop_column("products", "number")
    op.drop_column("products", "finance_rate")
    op.drop_column("products", "finance_code")
    op.drop_column("products", "goods_channel")
    op.drop_column("products", "supplier_name")
    op.drop_column("products", "supplier_id")
    op.drop_column("products", "float_rate_min")
    op.drop_column("products", "float_rate_max")
    op.drop_column("products", "discount_rate")
    op.drop_column("products", "limit_price")
    op.drop_column("products", "level")
    op.drop_column("products", "attr")
    op.drop_column("products", "source")
    op.drop_column("products", "model")
    op.drop_column("products", "manufacturer")
    op.drop_column("products", "expire_date")
    op.drop_column("products", "brand")
    op.drop_column("products", "goods_sn")
