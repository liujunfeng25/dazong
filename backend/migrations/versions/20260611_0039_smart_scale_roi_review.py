"""smart scale ROI profiles and sample review workflow

Revision ID: 20260611_0039
Revises: 20260610_0038
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_0039"
down_revision = "20260610_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    def inspector():
        return sa.inspect(conn)

    if "smart_scale_recognition_roi_profiles" not in set(inspector().get_table_names()):
        op.create_table(
            "smart_scale_recognition_roi_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.String(length=128), nullable=False),
            sa.Column("device_name", sa.String(length=120), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("x", sa.Float(), nullable=False),
            sa.Column("y", sa.Float(), nullable=False),
            sa.Column("width", sa.Float(), nullable=False),
            sa.Column("height", sa.Float(), nullable=False),
            sa.Column("rotation", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reference_image_url", sa.String(length=1024), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["created_by"], ["users.id"], name="fk_ssr_roi_profiles_created_by_users"
            ),
            sa.UniqueConstraint("device_id", "version", name="uq_ssr_roi_device_version"),
        )

    roi_indexes = {
        index.get("name")
        for index in inspector().get_indexes("smart_scale_recognition_roi_profiles")
    }
    if "ix_ssr_roi_profiles_device_id" not in roi_indexes and (
        "ix_smart_scale_recognition_roi_profiles_device_id" not in roi_indexes
    ):
        op.create_index(
            "ix_ssr_roi_profiles_device_id",
            "smart_scale_recognition_roi_profiles",
            ["device_id"],
        )
    if "ix_ssr_roi_profiles_status" not in roi_indexes and (
        "ix_smart_scale_recognition_roi_profiles_status" not in roi_indexes
    ):
        op.create_index(
            "ix_ssr_roi_profiles_status",
            "smart_scale_recognition_roi_profiles",
            ["status"],
        )

    category_columns = {
        column["name"] for column in inspector().get_columns("smart_scale_recognition_categories")
    }
    if "source" not in category_columns:
        op.add_column(
            "smart_scale_recognition_categories",
            sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        )

    sample_columns = {
        column["name"] for column in inspector().get_columns("smart_scale_recognition_samples")
    }
    sample_additions = [
        sa.Column("original_image_url", sa.String(length=1024), nullable=True),
        sa.Column("cropped_image_url", sa.String(length=1024), nullable=True),
        sa.Column("device_id", sa.String(length=128), nullable=True),
        sa.Column("roi_profile_id", sa.Integer(), nullable=True),
        sa.Column("roi_version", sa.Integer(), nullable=True),
        sa.Column("roi_override_json", sa.JSON(), nullable=True),
        sa.Column(
            "review_status", sa.String(length=24), nullable=False, server_default="approved"
        ),
        sa.Column(
            "quality_status", sa.String(length=24), nullable=False, server_default="passed"
        ),
        sa.Column("quality_reason", sa.String(length=255), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
    ]
    for column in sample_additions:
        if column.name not in sample_columns:
            op.add_column("smart_scale_recognition_samples", column)

    sample_foreign_key_columns = {
        tuple(foreign_key.get("constrained_columns") or [])
        for foreign_key in inspector().get_foreign_keys("smart_scale_recognition_samples")
    }
    if ("roi_profile_id",) not in sample_foreign_key_columns:
        op.create_foreign_key(
            "fk_ssr_samples_roi_profile_id",
            "smart_scale_recognition_samples",
            "smart_scale_recognition_roi_profiles",
            ["roi_profile_id"],
            ["id"],
        )
    if ("reviewed_by",) not in sample_foreign_key_columns:
        op.create_foreign_key(
            "fk_ssr_samples_reviewed_by_users",
            "smart_scale_recognition_samples",
            "users",
            ["reviewed_by"],
            ["id"],
        )

    sample_indexes = {
        index.get("name") for index in inspector().get_indexes("smart_scale_recognition_samples")
    }
    for index_name, columns in [
        ("ix_ssr_samples_device_id", ["device_id"]),
        ("ix_ssr_samples_review_status", ["review_status"]),
        ("ix_ssr_samples_quality_status", ["quality_status"]),
    ]:
        if index_name not in sample_indexes:
            op.create_index(index_name, "smart_scale_recognition_samples", columns)

    op.execute(
        "UPDATE smart_scale_recognition_samples "
        "SET original_image_url = image_url WHERE original_image_url IS NULL"
    )

    train_columns = {
        column["name"] for column in inspector().get_columns("smart_scale_recognition_train_tasks")
    }
    if "roi_versions_json" not in train_columns:
        op.add_column(
            "smart_scale_recognition_train_tasks",
            sa.Column("roi_versions_json", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("smart_scale_recognition_train_tasks") as batch:
        batch.drop_column("roi_versions_json")

    with op.batch_alter_table("smart_scale_recognition_samples") as batch:
        batch.drop_index("ix_ssr_samples_quality_status")
        batch.drop_index("ix_ssr_samples_review_status")
        batch.drop_index("ix_ssr_samples_device_id")
        batch.drop_constraint("fk_ssr_samples_reviewed_by_users", type_="foreignkey")
        batch.drop_constraint("fk_ssr_samples_roi_profile_id", type_="foreignkey")
        batch.drop_column("rejection_reason")
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewed_by")
        batch.drop_column("quality_reason")
        batch.drop_column("quality_status")
        batch.drop_column("review_status")
        batch.drop_column("roi_override_json")
        batch.drop_column("roi_version")
        batch.drop_column("roi_profile_id")
        batch.drop_column("device_id")
        batch.drop_column("cropped_image_url")
        batch.drop_column("original_image_url")

    with op.batch_alter_table("smart_scale_recognition_categories") as batch:
        batch.drop_column("source")

    op.drop_index(
        "ix_ssr_roi_profiles_status",
        table_name="smart_scale_recognition_roi_profiles",
    )
    op.drop_index(
        "ix_ssr_roi_profiles_device_id",
        table_name="smart_scale_recognition_roi_profiles",
    )
    op.drop_table("smart_scale_recognition_roi_profiles")
