from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import identifier, now


class DigitalCourse(Base):
    __tablename__ = "digital_courses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    filename: Mapped[str] = mapped_column(String(255))
    slides: Mapped[list] = mapped_column(JSON)
    studio: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    avatar: Mapped[str] = mapped_column(String(64), default="")
    voice: Mapped[str] = mapped_column(String(64), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    job_id: Mapped[str | None] = mapped_column(String(32))
    video_id: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class CourseAsset(Base):
    __tablename__ = "digital_course_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(100))
    transcript: Mapped[str] = mapped_column(String(600), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CourseVoiceFolder(Base):
    __tablename__ = "digital_course_voice_folders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("digital_course_assets.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CourseVoiceSample(Base):
    __tablename__ = "digital_course_voice_samples"

    asset_id: Mapped[str] = mapped_column(ForeignKey("digital_course_assets.id", ondelete="CASCADE"), primary_key=True)
    folder_id: Mapped[str] = mapped_column(ForeignKey("digital_course_voice_folders.id", ondelete="CASCADE"), index=True)


class CourseJob(Base):
    __tablename__ = "digital_course_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("digital_courses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    input: Mapped[dict] = mapped_column(JSON)
    stage: Mapped[str] = mapped_column(String(80), default="等待处理")
    completed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    error: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
