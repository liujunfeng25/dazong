"""cleanup billing relation rules

Revision ID: 20260511_0023
Revises: 20260511_0022
Create Date: 2026-05-11
"""

from alembic import op


revision = "20260511_0023"
down_revision = "20260511_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(
            """
            DELETE bs FROM billing_statements bs
            INNER JOIN billing_cycles bc ON bc.id = bs.cycle_id
            LEFT JOIN users u ON u.id = bc.owner_user_id
            WHERE bc.scope_type = 'canteen'
               OR u.role IN ('operation', 'monitor')
               OR (bc.scope_type = 'relation_type' AND bc.scope_ref_id NOT IN (1, 2))
            """
        )
        op.execute(
            """
            DELETE bc FROM billing_cycles bc
            LEFT JOIN users u ON u.id = bc.owner_user_id
            WHERE bc.scope_type = 'canteen'
               OR u.role IN ('operation', 'monitor')
               OR (bc.scope_type = 'relation_type' AND bc.scope_ref_id NOT IN (1, 2))
            """
        )
        op.execute("DELETE FROM notifications WHERE event_type LIKE 'billing%'")
        op.execute(
            """
            INSERT INTO billing_cycles (
              cycle_code, role, owner_user_id, scope_type, scope_ref_id, cycle_type,
              start_date, end_date, close_day, confirm_due_days, payment_due_days,
              is_active, is_confirmed, created_at
            )
            SELECT 'CYC-RULE-CLIENT-DELIVERY', 'client', 0, 'relation_type', 1, 'monthly',
              CURDATE(), CURDATE(), 1, 3, 7, 1, 0, NOW()
            WHERE NOT EXISTS (
              SELECT 1 FROM billing_cycles WHERE owner_user_id = 0 AND scope_type = 'relation_type' AND scope_ref_id = 1
            )
            """
        )
        op.execute(
            """
            INSERT INTO billing_cycles (
              cycle_code, role, owner_user_id, scope_type, scope_ref_id, cycle_type,
              start_date, end_date, close_day, confirm_due_days, payment_due_days,
              is_active, is_confirmed, created_at
            )
            SELECT 'CYC-RULE-DELIVERY-SUPPLIER', 'delivery', 0, 'relation_type', 2, 'monthly',
              CURDATE(), CURDATE(), 1, 3, 7, 1, 0, NOW()
            WHERE NOT EXISTS (
              SELECT 1 FROM billing_cycles WHERE owner_user_id = 0 AND scope_type = 'relation_type' AND scope_ref_id = 2
            )
            """
        )


def downgrade() -> None:
    pass
