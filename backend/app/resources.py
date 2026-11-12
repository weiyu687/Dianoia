from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile
import shutil
import subprocess

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pypdf.errors import PdfReadError
from sqlalchemy import select

from .auth import DB, Teacher, course_access
from .documents import EXTENSIONS, FILES, WORD_EXTENSIONS, OfficeUnavailable, inspect_resource
from .models import Resource, identifier

router = APIRouter(prefix="/api/resources", tags=["resources"])
MAX_UPLOAD = 25 * 1024 * 1024


class OutlineNode(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    children: list["OutlineNode"] = Field(default_factory=list, max_length=100)


class ResourceUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    outline: list[OutlineNode] | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern="^(draft|ready)$")


def resource_view(row, detail=False):
    result = {key: getattr(row, key) for key in (
        "id", "title", "filename", "course_id", "extension", "size", "page_count", "has_preview", "status", "created_at", "updated_at"
    )}
    if detail:
        result.update(outline=row.outline, has_text=any(row.pages), text_pages=[bool(page) for page in row.pages])
    return result


def owned_resource(db, user, resource_id):
    row = db.get(Resource, resource_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "资料不存在")
    course_access(db, user, row.course_id)
    return row


def process_resource_file(original, extension):
    try:
        return inspect_resource(original, extension)
    except OfficeUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(504, "文档转换超时，请稍后重试") from error
    except (ValueError, PdfReadError, BadZipFile, KeyError, subprocess.CalledProcessError) as error:
        message = str(error) if type(error) is ValueError else "文件无法解析，请检查格式后重试"
        raise HTTPException(422, message) from error


@router.get("")
def list_resources(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    return [resource_view(row) for row in db.scalars(
        select(Resource).where(Resource.owner_id == user.id, Resource.course_id == course_id)
        .order_by(Resource.updated_at.desc())
    )]


@router.post("", status_code=201)
def upload_resource(
    db: DB, user: Teacher, course_id: Annotated[int, Form()], file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=160)] = None,
):
    course_access(db, user, course_id)
    name = Path((file.filename or "").replace("\\", "/")).name
    extension = Path(name).suffix.lower().removeprefix(".")
    if extension not in EXTENSIONS or len(name) > 255:
        raise HTTPException(415, "请选择 DOC、DOCX、PDF 或 PPTX 文件")
    folder = FILES / identifier()
    folder.mkdir(parents=True)
    original = folder / f"original.{extension}"
    try:
        size = 0
        with original.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "单个文件不能超过 25 MB")
                target.write(chunk)
        if not size:
            raise HTTPException(422, "文件为空")
        pages, outline, preview, page_count = process_resource_file(original, extension)
        row = Resource(
            id=folder.name, owner_id=user.id, course_id=course_id, filename=name,
            title=(title or "").strip() or Path(name).stem[:160], extension=extension,
            size=size, page_count=page_count, pages=pages, outline=outline, has_preview=preview,
        )
        db.add(row)
        db.commit()
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return resource_view(row, detail=True)


@router.get("/{resource_id}")
def get_resource(resource_id: str, db: DB, user: Teacher):
    return resource_view(owned_resource(db, user, resource_id), detail=True)


@router.post("/{resource_id}/process")
def process_word_resource(resource_id: str, db: DB, user: Teacher):
    row = owned_resource(db, user, resource_id)
    if row.extension not in WORD_EXTENSIONS:
        raise HTTPException(422, "只有 Word 资料支持此转换操作")
    folder = FILES / row.id
    if row.has_preview and (folder / "preview.pdf").is_file():
        return resource_view(row, detail=True)
    original = folder / f"original.{row.extension}"
    if not original.is_file():
        raise HTTPException(409, "找不到原始 Word 文件，请重新上传")
    row.pages, row.outline, row.has_preview, row.page_count = process_resource_file(original, row.extension)
    if not any(row.pages):
        row.status = "draft"
    db.commit()
    return resource_view(row, detail=True)


@router.get("/{resource_id}/file")
def get_original(resource_id: str, db: DB, user: Teacher):
    row = owned_resource(db, user, resource_id)
    return FileResponse(FILES / row.id / f"original.{row.extension}", filename=row.filename)


@router.get("/{resource_id}/preview")
def get_preview(resource_id: str, db: DB, user: Teacher):
    row = owned_resource(db, user, resource_id)
    if not row.has_preview:
        raise HTTPException(404, "没有可用的 PDF 预览")
    name = "original.pdf" if row.extension == "pdf" else "preview.pdf"
    return FileResponse(FILES / row.id / name, media_type="application/pdf")


@router.get("/{resource_id}/pages/{page}")
def get_page(resource_id: str, page: int, db: DB, user: Teacher):
    row = owned_resource(db, user, resource_id)
    if row.extension in WORD_EXTENSIONS and not row.has_preview:
        raise HTTPException(409, "请先将 Word 资料转换为 PDF")
    if not 1 <= page <= len(row.pages):
        raise HTTPException(404, "这一页没有可读文本")
    return {"text": row.pages[page - 1]}


def validate_outline(nodes, lower, upper, depth=1):
    if depth > 8 and nodes:
        raise HTTPException(422, "目录最多支持 8 层")
    prior_end = lower
    for node in nodes:
        if not node.title.strip() or not lower <= node.start <= node.end <= upper or node.start < prior_end:
            raise HTTPException(422, "请按页码排序，子章节页码必须在父章节范围内")
        prior_end = node.end
        validate_outline(node.children, node.start, node.end, depth + 1)


@router.patch("/{resource_id}")
def update_resource(resource_id: str, data: ResourceUpdate, db: DB, user: Teacher):
    row = owned_resource(db, user, resource_id)
    if not data.title.strip():
        raise HTTPException(422, "资料名称不能为空")
    if data.outline is not None:
        validate_outline(data.outline, 1, row.page_count)
        row.outline = [node.model_dump() for node in data.outline]
    if data.status == "ready":
        if row.extension in WORD_EXTENSIONS and not row.has_preview:
            raise HTTPException(409, "请先将 Word 资料转换为 PDF")
        if not any(row.pages):
            raise HTTPException(422, "没有可提取的正文。请上传带文本层的文件")
    row.title = data.title.strip()
    if data.status is not None:
        row.status = data.status
    db.commit()
    return resource_view(row, detail=True)


@router.delete("/{resource_id}", status_code=204)
def delete_resource(resource_id: str, db: DB, user: Teacher):
    row = owned_resource(db, user, resource_id)
    db.delete(row)
    db.commit()
    shutil.rmtree(FILES / resource_id, ignore_errors=True)
