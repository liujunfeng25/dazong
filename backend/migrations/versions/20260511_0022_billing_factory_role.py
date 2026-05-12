"""billing factory role

Revision ID: 20260511_0022
Revises: 20260506_0021
Create Date: 2026-05-11
"""

from alembic import op


revision = "20260511_0022"
down_revision = "20260506_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute("ALTER TABLE billing_cycles MODIFY role ENUM('client','delivery','supplier','factory') NOT NULL")
        op.execute("ALTER TABLE billing_statements MODIFY role ENUM('client','delivery','supplier','factory') NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute("ALTER TABLE billing_cycles MODIFY role ENUM('client','delivery','supplier') NOT NULL")
        op.execute("ALTER TABLE billing_statements MODIFY role ENUM('client','delivery','supplier') NOT NULL")
