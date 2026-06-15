"""smart scale recognition: real PyTorch training infra (sample provenance + train task)

Revision ID: 20260525_0032
Revises: 20260520_0031
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260525_0032"
down_revision = "20260520_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Sample 表新增来源/回溯字段 + (category, order, line) 幂等导入唯一约束
    with op.batch_alter_table("smart_scale_recognition_samples") as batch:
        batch.add_column(sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"))
        batch.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("order_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("line_index", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_ssr_samples_product_id_products",
            "products",
            ["product_id"],
            ["id"],
        )
        batch.create_unique_constraint(
            "uq_ssr_samples_cat_order_line",
            ["category_id", "order_id", "line_index"],
        )

    # 2) 真训练任务表（任务 + 模型产物合一）
    op.create_table(
        "smart_scale_recognition_train_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("epochs", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="16"),
        sa.Column("classes_json", sa.JSON(), nullable=True),
        sa.Column("class_mapping_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("model_path", sa.String(length=512), nullable=True),
        sa.Column("is_deployed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_ssr_train_tasks_created_by_users"
        ),
    )
    op.create_index(
        "ix_ssr_train_tasks_is_deployed",
        "smart_scale_recognition_train_tasks",
        ["is_deployed"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ssr_train_tasks_is_deployed",
        table_name="smart_scale_recognition_train_tasks",
    )
    op.drop_table("smart_scale_recognition_train_tasks")
    with op.batch_alter_table("smart_scale_recognition_samples") as batch:
        batch.drop_constraint("uq_ssr_samples_cat_order_line", type_="unique")
        batch.drop_constraint("fk_ssr_samples_product_id_products", type_="foreignkey")
        batch.drop_column("line_index")
        batch.drop_column("order_id")
        batch.drop_column("product_id")
        batch.drop_column("source")
