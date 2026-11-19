from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import identifier, now


class QuestionBank(Base):
    __tablename__ = "qbank_banks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(3000), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    cover: Mapped[dict] = mapped_column(JSON, default=dict)
    sections: Mapped[list] = mapped_column(JSON, default=list)
    materials: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    release_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[object] = mapped_column(DateTime, default=now)
    updated_at: Mapped[object] = mapped_column(DateTime, default=now, onupdate=now)


class BankQuestion(Base):
    __tablename__ = "qbank_questions"
    __table_args__ = (UniqueConstraint("job_id", "slot", name="uq_qbank_job_slot"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    bank_id: Mapped[str] = mapped_column(ForeignKey("qbank_banks.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[str | None] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=0)
    search_text: Mapped[str] = mapped_column(String(6000), default="")
    job_id: Mapped[str | None] = mapped_column(String(32))
    slot: Mapped[int | None] = mapped_column(Integer)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class QuestionVersion(Base):
    __tablename__ = "qbank_versions"
    __table_args__ = (UniqueConstraint("question_id", "number", name="uq_qbank_question_version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    question_id: Mapped[str] = mapped_column(ForeignKey("qbank_questions.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime, default=now)


class QuestionAnswer(Base):
    __tablename__ = "qbank_answers"
    version_id: Mapped[str] = mapped_column(ForeignKey("qbank_versions.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[dict] = mapped_column(JSON)


class BankRelease(Base):
    __tablename__ = "qbank_releases"
    __table_args__ = (UniqueConstraint("bank_id", "number", name="uq_qbank_release_number"),
                      UniqueConstraint("bank_id", "request_key", name="uq_qbank_publish_request"))
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    bank_id: Mapped[str] = mapped_column(ForeignKey("qbank_banks.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    draft_revision: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active")
    class_codes: Mapped[list] = mapped_column(JSON, default=list)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime, default=now)


class ReleaseQuestion(Base):
    __tablename__ = "qbank_release_questions"
    release_id: Mapped[str] = mapped_column(ForeignKey("qbank_releases.id", ondelete="CASCADE"), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("qbank_versions.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)


class QuestionAsset(Base):
    __tablename__ = "qbank_assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    bank_id: Mapped[str] = mapped_column(ForeignKey("qbank_banks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(255))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[object] = mapped_column(DateTime, default=now)


class BankGenerationJob(Base):
    __tablename__ = "qbank_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identifier)
    bank_id: Mapped[str] = mapped_column(ForeignKey("qbank_banks.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("bank_id", "request_key", name="uq_qbank_generation_request"),)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    config: Mapped[dict] = mapped_column(JSON)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(160), default="等待生成")
    error: Mapped[str] = mapped_column(String(500), default="")
    lease: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[object] = mapped_column(DateTime, default=now)
    updated_at: Mapped[object] = mapped_column(DateTime, default=now, onupdate=now)
