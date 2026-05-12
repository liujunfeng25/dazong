"""one device at most one vehicle binding (unique device_id)

Revision ID: 20260430_0018
Revises: 20260429_0017
Create Date: 2026-04-30

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260430_0018"
down_revision: Union[str, None] = "20260429_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 同一设备仅保留一条绑定（保留 id 最小的一条），再改为 device_id 全局唯一
    op.execute(
        """
        DELETE b1 FROM delivery_vehicle_device_bindings b1
        INNER JOIN delivery_vehicle_device_bindings b2
          ON b1.device_id = b2.device_id AND b1.id > b2.id
        """
    )
    op.drop_constraint("uq_vehicle_device_binding", "delivery_vehicle_device_bindings", type_="unique")
    op.create_unique_constraint(
        "uq_delivery_vehicle_device_binding_device_id",
        "delivery_vehicle_device_bindings",
        ["device_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_delivery_vehicle_device_binding_device_id",
        "delivery_vehicle_device_bindings",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_vehicle_device_binding",
        "delivery_vehicle_device_bindings",
        ["vehicle_id", "device_id"],
    )
