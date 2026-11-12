from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import defer

from .auth import DB, Teacher
from .models import LessonTemplate
from .word import read_word_upload, word_pdf

router = APIRouter(prefix="/api/lesson-templates", tags=["lesson templates"])
TemplateTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class TemplateUpdate(BaseModel):
    title: TemplateTitle


def template_view(row):
    return {field: getattr(row, field) for field in ("id", "title", "filename", "created_at")}


def owned_template(db, user, template_id):
    row = db.scalar(select(LessonTemplate).options(defer(LessonTemplate.content)).where(
        LessonTemplate.id == template_id, LessonTemplate.owner_id == user.id,
    ))
    if not row:
        raise HTTPException(404, "教案模板不存在")
    return row


@router.get("")
def list_templates(db: DB, user: Teacher):
    return [template_view(row) for row in db.scalars(
        select(LessonTemplate).options(defer(LessonTemplate.content))
        .where(LessonTemplate.owner_id == user.id).order_by(LessonTemplate.created_at.desc())
    )]


@router.post("", status_code=201)
def upload_template(db: DB, user: Teacher, file: Annotated[UploadFile, File()],
                    title: Annotated[str | None, Form(max_length=160)] = None):
    filename, content, _ = read_word_upload(file, allow_doc=True)
    template = LessonTemplate(
        owner_id=user.id, title=(title or "").strip() or Path(filename).stem[:160],
        filename=filename, content=content,
    )
    db.add(template)
    db.commit()
    return template_view(template)


@router.patch("/{template_id}")
def rename_template(template_id: str, data: TemplateUpdate, db: DB, user: Teacher):
    template = owned_template(db, user, template_id)
    template.title = data.title
    db.commit()
    return template_view(template)


@router.get("/{template_id}/preview")
def preview_template(template_id: str, db: DB, user: Teacher):
    template = owned_template(db, user, template_id)
    return Response(word_pdf(template.content), media_type="application/pdf")


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: str, db: DB, user: Teacher):
    db.delete(owned_template(db, user, template_id))
    db.commit()
