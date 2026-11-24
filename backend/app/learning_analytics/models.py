from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import identifier, now


class LearningImportBatch(Base):
    __tablename__ = "learning_import_batches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    class_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    term_label: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(160))
    original_filename: Mapped[str] = mapped_column(String(255))
    extension: Mapped[str] = mapped_column(String(8))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    original_path: Mapped[str] = mapped_column(String(255))
    parsed_path: Mapped[str] = mapped_column(String(255))
    sheet_name: Mapped[str] = mapped_column(String(160), default="")
    sheet_names: Mapped[list] = mapped_column(JSON, default=list)
    columns: Mapped[list] = mapped_column(JSON, default=list)
    sample_rows: Mapped[list] = mapped_column(JSON, default=list)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="mapping", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LearningObservation(Base):
    __tablename__ = "learning_observations"
    __table_args__ = (
        Index("ix_learning_observations_batch_metric", "batch_id", "metric_key"),
        Index("ix_learning_observations_student_metric", "student_code", "metric_key"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("learning_import_batches.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    class_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    student_code: Mapped[str] = mapped_column(String(64), index=True)
    student_name: Mapped[str] = mapped_column(String(100), default="")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    activity: Mapped[str] = mapped_column(String(160), default="")
    metric_key: Mapped[str] = mapped_column(String(64), index=True)
    metric_label: Mapped[str] = mapped_column(String(120))
    metric_type: Mapped[str] = mapped_column(String(20), index=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str] = mapped_column(String(160), default="")
    maximum: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    knowledge_tag: Mapped[str] = mapped_column(String(160), default="")
    source_row: Mapped[int] = mapped_column(Integer)


class AnalyticsMappingTemplate(Base):
    __tablename__ = "analytics_mapping_templates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(24), default="custom")
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class AnalyticsDashboardTemplate(Base):
    __tablename__ = "analytics_dashboard_templates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class LearningPlan(Base):
    __tablename__ = "learning_plans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    class_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), default="class")
    student_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    title: Mapped[str] = mapped_column(String(160))
    focus: Mapped[str] = mapped_column(String(1000), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    generation_source: Mapped[str] = mapped_column(String(16), default="rules")
    resource_ids: Mapped[list] = mapped_column(JSON, default=list)
    batch_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class SharedLearningResource(Base):
    __tablename__ = "shared_learning_resources"
    __table_args__ = (UniqueConstraint("source_type", "source_id", "version", name="uq_shared_resource_source_version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    source_type: Mapped[str] = mapped_column(String(24), index=True)
    source_id: Mapped[str] = mapped_column(String(32), index=True)
    source_revision: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(String(1200), default="")
    subject: Mapped[str] = mapped_column(String(100), default="")
    academic_level: Mapped[str] = mapped_column(String(80), default="")
    term_label: Mapped[str] = mapped_column(String(64), default="")
    section: Mapped[str] = mapped_column(String(160), default="")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="published", index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
