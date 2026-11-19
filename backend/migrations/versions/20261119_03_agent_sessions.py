"""Bring concurrently merged Agent sessions under versioned migrations."""
from alembic import op
import sqlalchemy as sa

revision = "20261119_03"
down_revision = "20261119_02"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "agent_conversations" not in existing:
        op.create_table("agent_conversations",
            sa.Column("id", sa.String(32), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("course_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
            sa.PrimaryKeyConstraint("id"))
        for field in ("owner_id", "course_id", "updated_at"):
            op.create_index("ix_agent_conversations_" + field, "agent_conversations", [field])
    if "agent_messages" not in existing:
        op.create_table("agent_messages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("conversation_id", sa.String(32), nullable=False),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("result", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"))
        for field in ("conversation_id", "status"):
            op.create_index("ix_agent_messages_" + field, "agent_messages", [field])


def downgrade():
    raise RuntimeError("Restore a verified backup; Agent history is not dropped automatically")
