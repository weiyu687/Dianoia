"""Frozen initial schema; existing tables and data are preserved."""
from alembic import op
import sqlalchemy as sa

revision = '20261119_02'
down_revision = '20261119_01'
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'qbank_banks' not in existing:
        op.create_table('qbank_banks',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('description', sa.String(length=3000), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('cover', sa.JSON(), nullable=False),
        sa.Column('sections', sa.JSON(), nullable=False),
        sa.Column('materials', sa.JSON(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('release_id', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_qbank_banks_course_id'), 'qbank_banks', ['course_id'], unique=False)
        op.create_index(op.f('ix_qbank_banks_owner_id'), 'qbank_banks', ['owner_id'], unique=False)
    if 'qbank_assets' not in existing:
        op.create_table('qbank_assets',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('bank_id', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bank_id'], ['qbank_banks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_qbank_assets_bank_id'), 'qbank_assets', ['bank_id'], unique=False)
    if 'qbank_jobs' not in existing:
        op.create_table('qbank_jobs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('bank_id', sa.String(length=32), nullable=False),
        sa.Column('request_key', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('completed', sa.Integer(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(length=160), nullable=False),
        sa.Column('error', sa.String(length=500), nullable=False),
        sa.Column('lease', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bank_id'], ['qbank_banks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bank_id', 'request_key', name='uq_qbank_generation_request')
        )
        op.create_index(op.f('ix_qbank_jobs_bank_id'), 'qbank_jobs', ['bank_id'], unique=False)
        op.create_index(op.f('ix_qbank_jobs_status'), 'qbank_jobs', ['status'], unique=False)
    if 'qbank_questions' not in existing:
        op.create_table('qbank_questions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('bank_id', sa.String(length=32), nullable=False),
        sa.Column('version_id', sa.String(length=32), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('search_text', sa.String(length=6000), nullable=False),
        sa.Column('job_id', sa.String(length=32), nullable=True),
        sa.Column('slot', sa.Integer(), nullable=True),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['bank_id'], ['qbank_banks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'slot', name='uq_qbank_job_slot')
        )
        op.create_index(op.f('ix_qbank_questions_bank_id'), 'qbank_questions', ['bank_id'], unique=False)
    if 'qbank_releases' not in existing:
        op.create_table('qbank_releases',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('bank_id', sa.String(length=32), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('draft_revision', sa.Integer(), nullable=False),
        sa.Column('request_key', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('class_codes', sa.JSON(), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bank_id'], ['qbank_banks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bank_id', 'number', name='uq_qbank_release_number'),
        sa.UniqueConstraint('bank_id', 'request_key', name='uq_qbank_publish_request')
        )
        op.create_index(op.f('ix_qbank_releases_bank_id'), 'qbank_releases', ['bank_id'], unique=False)
    if 'qbank_versions' not in existing:
        op.create_table('qbank_versions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('question_id', sa.String(length=32), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['question_id'], ['qbank_questions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('question_id', 'number', name='uq_qbank_question_version')
        )
        op.create_index(op.f('ix_qbank_versions_question_id'), 'qbank_versions', ['question_id'], unique=False)
    if 'qbank_answers' not in existing:
        op.create_table('qbank_answers',
        sa.Column('version_id', sa.String(length=32), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['version_id'], ['qbank_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('version_id')
        )
    if 'qbank_release_questions' not in existing:
        op.create_table('qbank_release_questions',
        sa.Column('release_id', sa.String(length=32), nullable=False),
        sa.Column('version_id', sa.String(length=32), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['release_id'], ['qbank_releases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['version_id'], ['qbank_versions.id'], ),
        sa.PrimaryKeyConstraint('release_id', 'version_id')
        )


def downgrade():
    raise RuntimeError("Restore a verified database backup; historical teaching data is not dropped automatically")
