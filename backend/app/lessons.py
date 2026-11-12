import os
import re
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from docx import Document
from docx.table import Table
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, StringConstraints
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import select, update

from .auth import DB, Teacher, course_access
from .documents import WORD_EXTENSIONS
from .lesson_templates import owned_template
from .models import Lesson, LessonDocument, identifier, now
from .resources import owned_resource
from .word import DOCX_MIME, convert_word, read_word_upload, word_pdf

router = APIRouter(prefix="/api/lessons", tags=["lessons"])
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
WORD_HEADING = re.compile(r"(?:Heading|标题)\s*([1-9])$", re.IGNORECASE)


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
    template_id: str | None = Field(default=None, max_length=32)
    blank_document: bool = False


class LessonUpdate(BaseModel):
    title: Title
    revision: int = Field(ge=1)
    sections: list[Section] | None = Field(default=None, min_length=1, max_length=30)
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


def create_lesson(db, user, data, sections, docx=None):
    row = Lesson(
        owner_id=user.id, course_id=data.course_id, title=data.title,
        sections=[section.model_dump() for section in sections],
        sources=[source.model_dump() for source in data.sources],
    )
    db.add(row)
    if docx is not None:
        db.flush()
        db.add(LessonDocument(lesson_id=row.id, content=docx))
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
    if data.template_id:
        content = owned_template(db, user, data.template_id).content
        return create_lesson(db, user, data, document_sections(Document(BytesIO(content))), content)
    if data.blank_document:
        document = Document()
        document.add_paragraph()
        return create_lesson(db, user, data, document_sections(document), serialize_docx(document))
    return create_lesson(db, user, data, default_sections())


@router.get("/{lesson_id}")
def get_lesson(lesson_id: str, db: DB, user: Teacher):
    return lesson_view(owned_lesson(db, user, lesson_id), detail=True)


@router.put("/{lesson_id}")
def save_lesson(lesson_id: str, data: LessonUpdate, db: DB, user: Teacher):
    row = owned_lesson(db, user, lesson_id)
    fields = {"title": data.title, "status": data.status}
    if data.sections is not None and not db.get(LessonDocument, row.id):
        sections = [section.model_dump() for section in data.sections]
        structure = list(walk_sections(sections))
        if (len(structure) > 80 or any(depth > 8 for _, depth in structure)
                or len({section["id"] for section, _ in structure}) != len(structure)):
            raise HTTPException(422, "请检查章节层级、数量及标识")
        fields["sections"] = sections
    update_revision(db, row.id, data.revision, **fields)
    db.commit()
    return lesson_view(row, detail=True)


def update_revision(db, lesson_id, revision, **fields):
    result = db.execute(update(Lesson).where(Lesson.id == lesson_id, Lesson.revision == revision).values(
        **fields, revision=Lesson.revision + 1, updated_at=now(),
    ))
    if result.rowcount != 1:
        raise HTTPException(409, "教案已在其他窗口更新，请保留当前修改后重新打开")


@router.get("/{lesson_id}/document")
def get_lesson_document(lesson_id: str, db: DB, user: Teacher, revision: int | None = None):
    result = db.execute(select(Lesson, LessonDocument.content).outerjoin(LessonDocument).where(
        Lesson.id == lesson_id, Lesson.owner_id == user.id,
    )).one_or_none()
    if not result:
        raise HTTPException(404, "教案不存在")
    row, content = result
    course_access(db, user, row.course_id)
    if revision is not None and row.revision != revision:
        raise HTTPException(409, "教案已更新，请重新打开")
    return Response(content if content is not None else render_docx(row), media_type=DOCX_MIME)


@router.put("/{lesson_id}/document")
def save_lesson_document(
    lesson_id: str, db: DB, user: Teacher,
    title: Annotated[str, Form(max_length=160)], revision: Annotated[int, Form(ge=1)],
    file: Annotated[UploadFile, File()],
):
    row = owned_lesson(db, user, lesson_id)
    if not title.strip():
        raise HTTPException(422, "教案名称不能为空")
    _, content, document = read_word_upload(file)
    sections = [section.model_dump() for section in document_sections(document)]
    update_revision(db, row.id, revision, title=title.strip(), sections=sections)
    word = db.get(LessonDocument, row.id)
    if word:
        word.content = content
    else:
        db.add(LessonDocument(lesson_id=row.id, content=content))
    db.commit()
    return lesson_view(row, detail=True)


@router.post("/{lesson_id}/copy", status_code=201)
def copy_lesson(lesson_id: str, db: DB, user: Teacher):
    row = owned_lesson(db, user, lesson_id)
    data = NewLesson(course_id=row.course_id, title=f"{row.title[:154]}（副本）", sources=row.sources)
    word = db.get(LessonDocument, row.id)
    return create_lesson(db, user, data, [Section.model_validate(section) for section in row.sections],
                         word.content if word else None)


@router.delete("/{lesson_id}", status_code=204)
def delete_lesson(lesson_id: str, db: DB, user: Teacher):
    db.delete(owned_lesson(db, user, lesson_id))
    db.commit()


def render_docx(row):
    return render_sections_docx(row.title, row.sections)


def render_sections_docx(title, sections):
    document = Document()
    document.add_heading(title, 0)
    for section, depth in walk_sections(sections):
        document.add_heading(section["title"], level=min(depth, 9))
        for line in section["content"].splitlines():
            document.add_paragraph(line)
    return serialize_docx(document)


def serialize_docx(document):
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def document_sections(document):
    roots = []
    ancestors = []
    current = Section(title="正文")
    lines = []
    headings = 0
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            lines.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
            continue
        heading = WORD_HEADING.fullmatch(block.style.name or "")
        if not heading or not block.text.strip() or headings >= 29:
            lines.append(block.text)
            continue
        current.content = "\n".join(lines)[:30000]
        if headings == 0 and current.content.strip():
            roots.append(current)
        level = int(heading[1])
        while ancestors and ancestors[-1][0] >= level:
            ancestors.pop()
        current = Section(title=block.text.strip()[:160])
        siblings = ancestors[-1][1].children if ancestors else roots
        siblings.append(current)
        ancestors.append((level, current))
        headings += 1
        lines = []
    current.content = "\n".join(lines)[:30000]
    return roots or [current]


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
    word = db.get(LessonDocument, row.id)
    if format == "pdf":
        content, mime = (word_pdf(word.content) if word else render_pdf(row)), "application/pdf"
    elif format == "docx":
        content, mime = (word.content if word else render_docx(row)), DOCX_MIME
    else:
        content = convert_word(word.content if word else render_docx(row), "docx", "doc:MS Word 97")
        mime = "application/msword"
    kind = "inline" if inline and format == "pdf" else "attachment"
    return Response(content, media_type=mime, headers={
        "Content-Disposition": f"{kind}; filename*=UTF-8''{quote(f'{row.title}.{format}', safe='')}",
    })
