from html import escape
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from urllib.parse import quote
from functools import lru_cache
import os
import subprocess

from docx import Document
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, StringConstraints
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import select, update
from typing import Annotated

from .auth import DB, Teacher, course_access
from .documents import WORD_EXTENSIONS, convert_with_office
from .models import Lesson, identifier, now
from .resources import owned_resource

router = APIRouter(prefix="/api/lessons", tags=["lessons"])
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class Section(BaseModel):
    id: str = Field(default_factory=identifier, max_length=64)
    title: Title
    content: str = Field(default="", max_length=30000)
    children: list["Section"] = Field(default_factory=list, max_length=30)


class Source(BaseModel):
    resource_id: str = Field(max_length=32)
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class NewLesson(BaseModel):
    course_id: int
    title: Title
    sources: list[Source] = Field(default_factory=list, max_length=12)


class LessonUpdate(BaseModel):
    title: Title
    revision: int = Field(ge=1)
    sections: list[Section] = Field(min_length=1, max_length=30)
    status: Literal["draft", "archived"] = "draft"


def default_sections():
    return [
        Section(title="授课信息"),
        Section(title="教学目的与要求"),
        Section(title="教学重点与难点"),
        Section(title="教学内容与设计", children=[
            Section(title="导入"),
            Section(title="讲授与实践"),
            Section(title="课堂评价"),
        ]),
        Section(title="课后作业及思考题"),
        Section(title="课后小结"),
    ]


def walk_sections(sections, depth=1):
    for section in sections:
        yield section, depth
        yield from walk_sections(section["children"], depth + 1)


def lesson_view(row, detail=False):
    fields = ["id", "course_id", "title", "status", "revision", "created_at", "updated_at"]
    if detail:
        fields.extend(["sections", "sources"])
    return {field: getattr(row, field) for field in fields}


def owned_lesson(db, user, lesson_id):
    row = db.get(Lesson, lesson_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "教案不存在")
    course_access(db, user, row.course_id)
    return row


def source_text(db, user, course_id, selections):
    chunks = []
    for source in selections:
        resource = owned_resource(db, user, source.resource_id)
        if resource.extension in WORD_EXTENSIONS and not resource.has_preview:
            raise HTTPException(409, "请先在资料库中将 Word 资料转换为 PDF")
        if (resource.course_id != course_id or resource.status != "ready"
                or not 1 <= source.start <= source.end <= len(resource.pages)):
            raise HTTPException(422, "请使用当前课程已入库的资料并核对页码")
        for page in range(source.start, source.end + 1):
            if text := resource.pages[page - 1]:
                chunks.append(f"【{resource.title} 第 {page} 页】\n{text}")
    context = "\n\n".join(chunks)
    if len(context) > 45000:
        raise HTTPException(422, "资料范围较长，请缩小选用页码后重试")
    return context


def create_lesson(db, user, data, sections):
    row = Lesson(
        owner_id=user.id, course_id=data.course_id, title=data.title,
        sections=[section.model_dump() for section in sections],
        sources=[source.model_dump() for source in data.sources],
    )
    db.add(row)
    db.commit()
    return lesson_view(row, detail=True)


@router.get("")
def list_lessons(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    return [lesson_view(row) for row in db.scalars(select(Lesson).where(
        Lesson.owner_id == user.id, Lesson.course_id == course_id
    ).order_by(Lesson.updated_at.desc()))]


@router.post("", status_code=201)
def new_lesson(data: NewLesson, db: DB, user: Teacher):
    course_access(db, user, data.course_id)
    source_text(db, user, data.course_id, data.sources)
    return create_lesson(db, user, data, default_sections())


@router.get("/{lesson_id}")
def get_lesson(lesson_id: str, db: DB, user: Teacher):
    return lesson_view(owned_lesson(db, user, lesson_id), detail=True)


@router.put("/{lesson_id}")
def save_lesson(lesson_id: str, data: LessonUpdate, db: DB, user: Teacher):
    row = owned_lesson(db, user, lesson_id)
    sections = [section.model_dump() for section in data.sections]
    structure = list(walk_sections(sections))
    if (len(structure) > 80 or any(depth > 8 for _, depth in structure)
            or len({section["id"] for section, _ in structure}) != len(structure)):
        raise HTTPException(422, "请检查章节层级、数量及标识")
    result = db.execute(update(Lesson).where(Lesson.id == row.id, Lesson.revision == data.revision).values(
        title=data.title, sections=sections, status=data.status, revision=Lesson.revision + 1, updated_at=now(),
    ))
    if result.rowcount != 1:
        raise HTTPException(409, "教案已在其他窗口更新，请保存当前修改后重新打开")
    db.commit()
    return lesson_view(row, detail=True)


@router.post("/{lesson_id}/copy", status_code=201)
def copy_lesson(lesson_id: str, db: DB, user: Teacher):
    row = owned_lesson(db, user, lesson_id)
    data = NewLesson(course_id=row.course_id, title=f"{row.title[:154]}（副本）", sources=row.sources)
    return create_lesson(db, user, data, [Section.model_validate(section) for section in row.sections])


@router.delete("/{lesson_id}", status_code=204)
def delete_lesson(lesson_id: str, db: DB, user: Teacher):
    db.delete(owned_lesson(db, user, lesson_id))
    db.commit()


def render_docx(row):
    document = Document()
    document.add_heading(row.title, 0)
    for section, depth in walk_sections(row.sections):
        document.add_heading(section["title"], level=min(depth, 9))
        for line in section["content"].splitlines():
            document.add_paragraph(line)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@lru_cache(maxsize=1)
def pdf_font():
    font = os.getenv("DIANOIA_PDF_FONT")
    if not font and os.name == "nt":
        candidate = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc"
        if candidate.exists():
            font = str(candidate)
    if font:
        pdfmetrics.registerFont(TTFont("Dianoia-CJK", font, subfontIndex=0))
        return "Dianoia-CJK"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def render_pdf(row):
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, title=row.title)
    title = ParagraphStyle("title", fontName=pdf_font(), fontSize=20, leading=27, wordWrap="CJK")
    heading = ParagraphStyle("heading", parent=title, fontSize=13, leading=20)
    body = ParagraphStyle("body", parent=title, fontSize=11, leading=17)
    flow = [Paragraph(escape(row.title), title), Spacer(1, 16)]
    for section, depth in walk_sections(row.sections):
        flow.extend([Paragraph(escape(section["title"]), ParagraphStyle("section", parent=heading, leftIndent=(depth - 1) * 10)), Spacer(1, 4)])
        if section["content"]:
            flow.append(Paragraph(escape(section["content"]).replace("\n", "<br/>"), body))
        flow.append(Spacer(1, 10))
    document.build(flow)
    return buffer.getvalue()


@router.get("/{lesson_id}/export/{format}")
def export_lesson(lesson_id: str, format: Literal["pdf", "docx", "doc"], db: DB, user: Teacher, inline: bool = False):
    row = owned_lesson(db, user, lesson_id)
    if format == "pdf":
        content, mime = render_pdf(row), "application/pdf"
    elif format == "docx":
        content, mime = render_docx(row), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        with TemporaryDirectory(prefix="dianoia-export-") as directory:
            path = Path(directory)
            source = path / "lesson.docx"
            source.write_bytes(render_docx(row))
            try:
                converted = convert_with_office(source, "doc:MS Word 97", path)
            except subprocess.SubprocessError:
                converted = None
            if not converted:
                raise HTTPException(503, "旧版 DOC 导出需要配置 LibreOffice")
            content, mime = converted.read_bytes(), "application/msword"
    kind = "inline" if inline and format == "pdf" else "attachment"
    return Response(content, media_type=mime, headers={
        "Content-Disposition": f"{kind}; filename*=UTF-8''{quote(f'{row.title}.{format}', safe='')}",
    })
