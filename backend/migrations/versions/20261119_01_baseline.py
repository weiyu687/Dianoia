"""Frozen initial schema; existing tables and data are preserved."""
from alembic import op
import sqlalchemy as sa

revision = '20261119_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'courses' not in existing:
        op.create_table('courses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
        )
    if 'students' not in existing:
        op.create_table('students',
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('code')
        )
    if 'users' not in existing:
        op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
        )
    if 'class_groups' not in existing:
        op.create_table('class_groups',
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.PrimaryKeyConstraint('code')
        )
    if 'digital_course_assets' not in existing:
        op.create_table('digital_course_assets',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('transcript', sa.String(length=600), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_digital_course_assets_owner_id'), 'digital_course_assets', ['owner_id'], unique=False)
    if 'digital_courses' not in existing:
        op.create_table('digital_courses',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('slides', sa.JSON(), nullable=False),
        sa.Column('avatar', sa.String(length=64), nullable=False),
        sa.Column('voice', sa.String(length=64), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(length=32), nullable=True),
        sa.Column('video_id', sa.String(length=32), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_digital_courses_course_id'), 'digital_courses', ['course_id'], unique=False)
        op.create_index(op.f('ix_digital_courses_owner_id'), 'digital_courses', ['owner_id'], unique=False)
    if 'exam_templates' not in existing:
        op.create_table('exam_templates',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_exam_templates_owner_id'), 'exam_templates', ['owner_id'], unique=False)
    if 'exams' not in existing:
        op.create_table('exams',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('questions', sa.JSON(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('imported', sa.Boolean(), nullable=False),
        sa.Column('reviewed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_exams_course_id'), 'exams', ['course_id'], unique=False)
        op.create_index(op.f('ix_exams_owner_id'), 'exams', ['owner_id'], unique=False)
    if 'lesson_templates' not in existing:
        op.create_table('lesson_templates',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_lesson_templates_owner_id'), 'lesson_templates', ['owner_id'], unique=False)
    if 'lessons' not in existing:
        op.create_table('lessons',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('sections', sa.JSON(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_lessons_course_id'), 'lessons', ['course_id'], unique=False)
        op.create_index(op.f('ix_lessons_owner_id'), 'lessons', ['owner_id'], unique=False)
    if 'mind_map_templates' not in existing:
        op.create_table('mind_map_templates',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_mind_map_templates_owner_id'), 'mind_map_templates', ['owner_id'], unique=False)
    if 'mind_maps' not in existing:
        op.create_table('mind_maps',
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_mind_maps_course_id'), 'mind_maps', ['course_id'], unique=False)
        op.create_index(op.f('ix_mind_maps_owner_id'), 'mind_maps', ['owner_id'], unique=False)
    if 'presentation_media' not in existing:
        op.create_table('presentation_media',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=160), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_presentation_media_course_id'), 'presentation_media', ['course_id'], unique=False)
        op.create_index(op.f('ix_presentation_media_owner_id'), 'presentation_media', ['owner_id'], unique=False)
    if 'resources' not in existing:
        op.create_table('resources',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('extension', sa.String(length=5), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=False),
        sa.Column('has_preview', sa.Boolean(), nullable=False),
        sa.Column('pages', sa.JSON(), nullable=False),
        sa.Column('outline', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_resources_course_id'), 'resources', ['course_id'], unique=False)
        op.create_index(op.f('ix_resources_owner_id'), 'resources', ['owner_id'], unique=False)
    if 'sessions' not in existing:
        op.create_table('sessions',
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token_hash')
        )
        op.create_index(op.f('ix_sessions_expires_at'), 'sessions', ['expires_at'], unique=False)
        op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    if 'teaching_assignments' not in existing:
        op.create_table('teaching_assignments',
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('teacher_id', 'course_id')
        )
    if 'teaching_presentation_templates' not in existing:
        op.create_table('teaching_presentation_templates',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_teaching_presentation_templates_owner_id'), 'teaching_presentation_templates', ['owner_id'], unique=False)
    if 'teaching_presentations' not in existing:
        op.create_table('teaching_presentations',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_teaching_presentations_course_id'), 'teaching_presentations', ['course_id'], unique=False)
        op.create_index(op.f('ix_teaching_presentations_owner_id'), 'teaching_presentations', ['owner_id'], unique=False)
    if 'digital_course_jobs' not in existing:
        op.create_table('digital_course_jobs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('project_id', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('input', sa.JSON(), nullable=False),
        sa.Column('stage', sa.String(length=80), nullable=False),
        sa.Column('completed', sa.Integer(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('error', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['digital_courses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_digital_course_jobs_project_id'), 'digital_course_jobs', ['project_id'], unique=False)
        op.create_index(op.f('ix_digital_course_jobs_status'), 'digital_course_jobs', ['status'], unique=False)
    if 'digital_course_voice_folders' not in existing:
        op.create_table('digital_course_voice_folders',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('reference_id', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['reference_id'], ['digital_course_assets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_digital_course_voice_folders_owner_id'), 'digital_course_voice_folders', ['owner_id'], unique=False)
    if 'enrollments' not in existing:
        op.create_table('enrollments',
        sa.Column('student_code', sa.String(length=64), nullable=False),
        sa.Column('class_code', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['class_code'], ['class_groups.code'], ),
        sa.ForeignKeyConstraint(['student_code'], ['students.code'], ),
        sa.PrimaryKeyConstraint('student_code', 'class_code')
        )
    if 'exam_answer_documents' not in existing:
        op.create_table('exam_answer_documents',
        sa.Column('exam_id', sa.String(length=32), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('based_on_revision', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('exam_id')
        )
    if 'exam_answer_sheets' not in existing:
        op.create_table('exam_answer_sheets',
        sa.Column('exam_id', sa.String(length=32), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('layout', sa.JSON(), nullable=False),
        sa.Column('question_signature', sa.String(length=64), nullable=False),
        sa.Column('edited', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('exam_id')
        )
    if 'exam_documents' not in existing:
        op.create_table('exam_documents',
        sa.Column('exam_id', sa.String(length=32), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('exam_id')
        )
    if 'lesson_documents' not in existing:
        op.create_table('lesson_documents',
        sa.Column('lesson_id', sa.String(length=32), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('lesson_id')
        )
    if 'presentation_suggestions' not in existing:
        op.create_table('presentation_suggestions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('presentation_id', sa.String(length=32), nullable=False),
        sa.Column('request', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['presentation_id'], ['teaching_presentations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_presentation_suggestions_created_at'), 'presentation_suggestions', ['created_at'], unique=False)
        op.create_index(op.f('ix_presentation_suggestions_presentation_id'), 'presentation_suggestions', ['presentation_id'], unique=False)
    if 'digital_course_voice_samples' not in existing:
        op.create_table('digital_course_voice_samples',
        sa.Column('asset_id', sa.String(length=32), nullable=False),
        sa.Column('folder_id', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['digital_course_assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['folder_id'], ['digital_course_voice_folders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('asset_id')
        )
        op.create_index(op.f('ix_digital_course_voice_samples_folder_id'), 'digital_course_voice_samples', ['folder_id'], unique=False)


def downgrade():
    raise RuntimeError("Restore a verified database backup; historical teaching data is not dropped automatically")
