"""add vehicle_model to delivery_vehicles

Revision ID: 20260429_0017
Revises: 20260428_0016
Create Date: 2026-04-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260429_0017"
down_revision: Union[str, None] = "20260428_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "delivery_vehicles",
        sa.Column("vehicle_model", sa.String(length=64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("delivery_vehicles", "vehicle_model")
