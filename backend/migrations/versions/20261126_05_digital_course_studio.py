"""Store digital course studio settings."""

import sqlalchemy as sa
from alembic import op

revision = "20261126_05"
down_revision = "20261123_04"
branch_labels = None
depends_on = None


def upgrade():
    columns = sa.inspect(op.get_bind()).get_columns("digital_courses")
    if not any(column["name"] == "studio" for column in columns):
        op.add_column("digital_courses", sa.Column("studio", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("digital_courses") as table:
        table.drop_column("studio")
