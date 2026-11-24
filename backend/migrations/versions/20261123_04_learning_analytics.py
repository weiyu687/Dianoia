"""Learning analytics imports, facts, plans and shared learning resources."""
from alembic import op
import sqlalchemy as sa

revision = "20261123_04"
down_revision = "20261119_03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_import_batches",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_code", sa.String(64)), sa.Column("term_label", sa.String(64), nullable=False),
        sa.Column("title", sa.String(160), nullable=False), sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("extension", sa.String(8), nullable=False), sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("original_path", sa.String(255), nullable=False), sa.Column("parsed_path", sa.String(255), nullable=False),
        sa.Column("sheet_name", sa.String(160), nullable=False), sa.Column("sheet_names", sa.JSON(), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("sample_rows", sa.JSON(), nullable=False), sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False), sa.Column("valid_count", sa.Integer(), nullable=False),
        sa.Column("invalid_count", sa.Integer(), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False), sa.Column("error", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime()),
    )
    for column in ("owner_id", "course_id", "class_code", "file_sha256", "status"):
        op.create_index(f"ix_learning_import_batches_{column}", "learning_import_batches", [column])

    op.create_table(
        "learning_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("batch_id", sa.String(32), sa.ForeignKey("learning_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_code", sa.String(64)), sa.Column("student_code", sa.String(64), nullable=False),
        sa.Column("student_name", sa.String(100), nullable=False), sa.Column("occurred_at", sa.DateTime()),
        sa.Column("activity", sa.String(160), nullable=False), sa.Column("metric_key", sa.String(64), nullable=False),
        sa.Column("metric_label", sa.String(120), nullable=False), sa.Column("metric_type", sa.String(20), nullable=False),
        sa.Column("value_number", sa.Float()), sa.Column("value_text", sa.String(160), nullable=False),
        sa.Column("maximum", sa.Float()), sa.Column("normalized_score", sa.Float()),
        sa.Column("knowledge_tag", sa.String(160), nullable=False), sa.Column("source_row", sa.Integer(), nullable=False),
    )
    for column in ("batch_id", "course_id", "class_code", "student_code", "occurred_at", "metric_key", "metric_type"):
        op.create_index(f"ix_learning_observations_{column}", "learning_observations", [column])
    op.create_index("ix_learning_observations_batch_metric", "learning_observations", ["batch_id", "metric_key"])
    op.create_index("ix_learning_observations_student_metric", "learning_observations", ["student_code", "metric_key"])

    op.create_table(
        "analytics_mapping_templates",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False), sa.Column("category", sa.String(24), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_analytics_mapping_templates_owner_id", "analytics_mapping_templates", ["owner_id"])
    op.create_table(
        "analytics_dashboard_templates",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False), sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_analytics_dashboard_templates_owner_id", "analytics_dashboard_templates", ["owner_id"])

    op.create_table(
        "learning_plans",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_code", sa.String(64)), sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("student_code", sa.String(64), nullable=False), sa.Column("title", sa.String(160), nullable=False),
        sa.Column("focus", sa.String(1000), nullable=False), sa.Column("content", sa.Text(), nullable=False),
        sa.Column("generation_source", sa.String(16), nullable=False),
        sa.Column("resource_ids", sa.JSON(), nullable=False), sa.Column("batch_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for column in ("owner_id", "course_id", "class_code", "student_code", "status"):
        op.create_index(f"ix_learning_plans_{column}", "learning_plans", [column])

    op.create_table(
        "shared_learning_resources",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_id", sa.String(32), nullable=False), sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False), sa.Column("summary", sa.String(1200), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False), sa.Column("academic_level", sa.String(80), nullable=False),
        sa.Column("term_label", sa.String(64), nullable=False), sa.Column("section", sa.String(160), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False), sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_type", "source_id", "version", name="uq_shared_resource_source_version"),
    )
    for column in ("source_type", "source_id", "owner_id", "course_id", "status", "published_at"):
        op.create_index(f"ix_shared_learning_resources_{column}", "shared_learning_resources", [column])


def downgrade():
    for table in ("shared_learning_resources", "learning_plans", "analytics_dashboard_templates",
                  "analytics_mapping_templates", "learning_observations", "learning_import_batches"):
        op.drop_table(table)
