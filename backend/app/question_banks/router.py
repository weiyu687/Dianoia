from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import delete, func, select, update

from ..auth import DB, Teacher, course_access
from ..exams import decode, owned as owned_exam, stored_document
from ..models import Course, Resource, identifier, now
from ..word import read_word_upload
from .assets import THEMES, cover_svg, save_image
from .content import plain
from .generation import revise_question
from .importing import candidates
from .models import BankGenerationJob, BankQuestion, BankRelease, QuestionAsset, QuestionBank, QuestionVersion
from .schemas import BankCreate, BankUpdate, Bulk, Generate, Publish, Question, QuestionSave, Revise, Revision, Strict
from .service import (FILES, bank_view, bump, check_sources, clone_bank, create_question, editable, job_view, owned,
                      preflight, publish, question_content, question_count, question_owned, question_rows, question_view,
                      release_view, save_question, update_bank)

router = APIRouter(prefix="/api/question-banks", tags=["online question banks"])


class Key(Strict):
    request_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")


class Adopt(Strict):
    questions: list[Question] = Field(min_length=1, max_length=100)
    request_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")


class Withdraw(Revision):
    release_id: str
    emergency: bool = False


class Status(Revision):
    archived: bool


@router.get("/themes")
def themes(user: Teacher):
    return THEMES


@router.get("")
def list_banks(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    return [bank_view(db, bank) for bank in db.scalars(select(QuestionBank).where(QuestionBank.owner_id == user.id,
            QuestionBank.course_id == course_id).order_by(QuestionBank.updated_at.desc()))]


@router.post("", status_code=201)
def new_bank(data: BankCreate, db: DB, user: Teacher):
    course_access(db, user, data.course_id)
    bank = QuestionBank(id=identifier(), owner_id=user.id, course_id=data.course_id, title=data.title,
                        cover={"theme": "academic", "accent": "#7759ce", "layout": "left", "asset_id": None},
                        sections=[{"id": identifier(), "title": "第一章", "parent_id": None}])
    db.add(bank)
    db.commit()
    return bank_view(db, bank, True)


@router.get("/assets/{asset_id}")
def image_file(asset_id: str, db: DB, user: Teacher, thumbnail: bool = False):
    asset = db.get(QuestionAsset, asset_id)
    if not asset:
        raise HTTPException(404, "图片不存在")
    owned(db, user, asset.bank_id)
    path = FILES / (asset.id + ("-thumb" if thumbnail and asset.kind == "cover" else "") + ".webp")
    if not path.is_file():
        raise HTTPException(404, "图片文件不可用")
    return FileResponse(path, media_type="image/webp")


@router.get("/{bank_id}")
def get_bank(bank_id: str, db: DB, user: Teacher):
    return bank_view(db, owned(db, user, bank_id), True)


@router.put("/{bank_id}")
def edit_bank(bank_id: str, data: BankUpdate, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    update_bank(db, user, bank, data)
    db.commit()
    return bank_view(db, bank, True)


@router.post("/{bank_id}/copy", status_code=201)
def copy_bank(bank_id: str, data: Key, db: DB, user: Teacher):
    result = clone_bank(db, user, owned(db, user, bank_id), data.request_key)
    db.commit()
    return bank_view(db, result, True)


@router.patch("/{bank_id}/status")
def status_bank(bank_id: str, data: Status, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    if data.archived and db.scalar(select(BankGenerationJob.id).where(BankGenerationJob.bank_id == bank.id,
                         BankGenerationJob.status.in_(["queued", "running"])).limit(1)):
        raise HTTPException(409, "请先取消生成任务再归档")
    bump(db, bank, data.revision, archived=data.archived)
    if data.archived:
        db.execute(update(BankRelease).where(BankRelease.bank_id == bank.id, BankRelease.status == "active").values(status="closed"))
    db.commit()
    return bank_view(db, bank, True)


@router.delete("/{bank_id}", status_code=204)
def delete_bank(bank_id: str, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    if db.scalar(select(BankRelease.id).where(BankRelease.bank_id == bank.id).limit(1)):
        raise HTTPException(409, "题库已有发布历史，请下架并归档以保留发布内容")
    if db.scalar(select(BankGenerationJob.id).where(BankGenerationJob.bank_id == bank.id, BankGenerationJob.status.in_(["running", "queued"])).limit(1)):
        raise HTTPException(409, "请先取消生成任务")
    assets = list(db.scalars(select(QuestionAsset).where(QuestionAsset.bank_id == bank.id)))
    db.delete(bank)
    db.commit()
    for asset in assets:
        for suffix in (".webp", "-thumb.webp"):
            (FILES / (asset.id + suffix)).unlink(missing_ok=True)


@router.get("/{bank_id}/cover")
def get_cover(bank_id: str, db: DB, user: Teacher, release_id: str | None = None):
    bank = owned(db, user, bank_id)
    if release_id:
        release = db.get(BankRelease, release_id)
        if not release or release.bank_id != bank.id:
            raise HTTPException(404, "发布版本不存在")
        data = release.snapshot
    else:
        data = {"title": bank.title, "cover": bank.cover, "course_name": db.get(Course, bank.course_id).name}
    asset_id = data["cover"].get("asset_id")
    if asset_id:
        return image_file(asset_id, db, user)
    return Response(cover_svg(data["title"], data["course_name"], data["cover"]), media_type="image/svg+xml",
                    headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})


@router.post("/{bank_id}/assets", status_code=201)
def upload_image(bank_id: str, db: DB, user: Teacher, file: UploadFile = File(),
                 kind: Literal["cover", "image"] = Form(default="image"),
                 x: float = Form(default=0, ge=0, le=1), y: float = Form(default=0, ge=0, le=1),
                 width: float = Form(default=1, gt=0, le=1), height: float = Form(default=1, gt=0, le=1)):
    bank = owned(db, user, bank_id)
    editable(bank)
    asset = save_image(db, bank, file.file.read(5 * 1024 * 1024 + 1), Path(file.filename or "图片").name, kind,
                       (x, y, width, height) if kind == "cover" else None)
    db.commit()
    return {"id": asset.id, "width": asset.width, "height": asset.height, "name": asset.name,
            "url": f"/api/question-banks/assets/{asset.id}"}


@router.get("/{bank_id}/questions")
def list_questions(bank_id: str, db: DB, user: Teacher, page: int = Query(default=1, ge=1), limit: int = Query(default=30, ge=1, le=100),
                   section_id: str | None = None, kind: str | None = None, q: str = Query(default="", max_length=160), pending: bool = False):
    bank = owned(db, user, bank_id)
    statement = question_rows(db, bank.id).join(QuestionVersion, QuestionVersion.id == BankQuestion.version_id)
    if section_id:
        ids = {section_id}
        for _ in range(8):
            ids.update(s["id"] for s in bank.sections if s["parent_id"] in ids)
        statement = statement.where(QuestionVersion.content["section_id"].as_string().in_(ids))
    if kind:
        statement = statement.where(QuestionVersion.content["kind"].as_string() == kind)
    if pending:
        statement = statement.where(QuestionVersion.content["confirmed"].as_boolean().is_(False))
    if q.strip():
        statement = statement.where(BankQuestion.search_text.icontains(q.strip(), autoescape=True))
    count = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(BankQuestion.position, BankQuestion.id).offset((page - 1) * limit).limit(limit))
    return {"items": [question_view(db, row, True) for row in rows], "total": count, "page": page, "limit": limit}


@router.post("/{bank_id}/questions", status_code=201)
def add_question(bank_id: str, data: Question, db: DB, user: Teacher,
                 idempotency_key: Annotated[str | None, Header(pattern=r"^[a-f0-9]{32}$")] = None):
    bank = owned(db, user, bank_id)
    from uuid import NAMESPACE_URL, uuid5
    key = uuid5(NAMESPACE_URL, f"qbank-question:{bank.id}:{idempotency_key}").hex if idempotency_key else None
    if key and (prior := db.get(BankQuestion, key)):
        if prior.deleted or question_content(db, prior) != data.model_dump():
            raise HTTPException(409, "此题已保存，请刷新题库后继续编辑")
        return question_view(db, prior) | {"bank_revision": bank.revision}
    row = create_question(db, user, bank, data, question_id=key)
    db.commit()
    return question_view(db, row) | {"bank_revision": bank.revision}


@router.get("/{bank_id}/questions/{question_id}")
def read_question(bank_id: str, question_id: str, db: DB, user: Teacher):
    return question_view(db, question_owned(db, owned(db, user, bank_id), question_id))


@router.put("/{bank_id}/questions/{question_id}")
def edit_question(bank_id: str, question_id: str, data: QuestionSave, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    row = question_owned(db, bank, question_id)
    save_question(db, user, bank, row, data.revision, data.question)
    db.commit()
    return question_view(db, row) | {"bank_revision": bank.revision}


@router.post("/{bank_id}/bulk")
def bulk(bank_id: str, data: Bulk, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    editable(bank)
    rows = [question_owned(db, bank, key) for key in dict.fromkeys(data.ids)]
    bump(db, bank, data.bank_revision)
    positions = sorted(row.position for row in rows)
    for index, row in enumerate(rows):
        if data.action == "delete":
            row.deleted = True
        elif data.action == "reorder":
            row.position = positions[index]
        else:
            item = question_content(db, row)
            if data.action == "move":
                item["section_id"] = data.section_id
            elif data.action == "tags":
                item["tags"] = data.tags
            else:
                item["included"] = data.action == "include"
            save_question(db, user, bank, row, row.revision, Question.model_validate(item))
    db.commit()
    return bank_view(db, bank, True)


@router.post("/{bank_id}/questions/{question_id}/revise")
def propose_question(bank_id: str, question_id: str, data: Revise, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    editable(bank)
    row = question_owned(db, bank, question_id)
    if row.revision != data.revision:
        raise HTTPException(409, "题目已更新，请刷新后重试")
    question = question_content(db, row)
    sources = question["sources"] or bank.sources
    from ..lessons import Source
    context, _ = check_sources(db, user, bank, [Source.model_validate(s) for s in sources])
    result = revise_question(question, data, context, sources)
    return {"question": result.model_dump(), "based_on_revision": data.revision}


@router.get("/{bank_id}/preflight")
def check_publish(bank_id: str, db: DB, user: Teacher):
    result, _ = preflight(db, owned(db, user, bank_id))
    return result


@router.post("/{bank_id}/publish", status_code=201)
def publish_bank(bank_id: str, data: Publish, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    release = publish(db, user, bank, data)
    db.commit()
    return {"release": release_view(release), "bank": bank_view(db, bank, True)}


@router.post("/{bank_id}/withdraw")
def withdraw(bank_id: str, data: Withdraw, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    release = db.get(BankRelease, data.release_id)
    if not release or release.bank_id != bank.id:
        raise HTTPException(404, "发布版本不存在")
    bump(db, bank, data.revision)
    release.status = "revoked" if data.emergency else "closed"
    db.commit()
    return bank_view(db, bank, True)


@router.get("/{bank_id}/preview")
def preview_bank(bank_id: str, db: DB, user: Teacher, release_id: str | None = None):
    bank = owned(db, user, bank_id)
    if release_id:
        release = db.get(BankRelease, release_id)
        if not release or release.bank_id != bank.id:
            raise HTTPException(404, "发布版本不存在")
        return {**release.snapshot, "release": release_view(release)}
    _, questions = preflight(db, bank)
    return {"schema_version": 1, "title": bank.title, "description": bank.description, "cover": bank.cover,
            "sections": bank.sections, "materials": bank.materials, "questions": questions, "release": None}


@router.post("/{bank_id}/jobs", status_code=202)
def generate_questions(bank_id: str, data: Generate, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    editable(bank)
    if prior := db.scalar(select(BankGenerationJob).where(BankGenerationJob.bank_id == bank.id, BankGenerationJob.request_key == data.request_key)):
        return job_view(prior)
    if data.section_id and data.section_id not in {s["id"] for s in bank.sections}:
        raise HTTPException(422, "章节不存在")
    if db.scalar(select(BankGenerationJob.id).where(BankGenerationJob.bank_id == bank.id, BankGenerationJob.status.in_(["queued", "running"])).limit(1)):
        raise HTTPException(409, "当前题库已有生成任务，请等待完成或取消")
    from ..ai import model_settings
    model_settings()
    context, _ = check_sources(db, user, bank, data.sources)
    kinds = [group.kind for group in data.groups for _ in range(group.count)]
    if question_count(db, bank.id) + len(kinds) > 2000:
        raise HTTPException(422, "单个题库最多保存 2000 题")
    bump(db, bank)
    # Serialize the active-job check with other creators, including repeated requests.
    if prior := db.scalar(select(BankGenerationJob).where(BankGenerationJob.bank_id == bank.id, BankGenerationJob.request_key == data.request_key)):
        db.rollback()
        return job_view(prior)
    if db.scalar(select(BankGenerationJob.id).where(BankGenerationJob.bank_id == bank.id, BankGenerationJob.status.in_(["queued", "running"])).limit(1)):
        raise HTTPException(409, "当前题库已有生成任务")
    job = BankGenerationJob(id=identifier(), bank_id=bank.id, request_key=data.request_key, total=len(kinds),
            config={"request": data.model_dump(), "kinds": kinds, "title": bank.title,
                    "sources": [s.model_dump() for s in data.sources], "context": context})
    db.add(job)
    db.commit()
    return job_view(job)


@router.post("/{bank_id}/jobs/{job_id}/{operation}")
def control_job(bank_id: str, job_id: str, operation: Literal["cancel", "retry"], db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    job = db.get(BankGenerationJob, job_id)
    if not job or job.bank_id != bank.id:
        raise HTTPException(404, "生成任务不存在")
    if operation == "cancel":
        if job.status not in {"queued", "running"}:
            raise HTTPException(409, "任务已结束")
        job.status, job.stage = "cancelled", "已取消，已生成题目保留"
    else:
        editable(bank)
        if job.status not in {"failed", "cancelled"}:
            raise HTTPException(409, "当前任务不支持重试")
        if db.scalar(select(BankGenerationJob.id).where(BankGenerationJob.bank_id == bank.id, BankGenerationJob.status.in_(["running", "queued"])).limit(1)):
            raise HTTPException(409, "已有生成任务在执行")
        job.status, job.stage, job.error = "queued", "等待继续生成", ""
    job.lease, job.updated_at = None, now()
    db.commit()
    return job_view(job)


@router.post("/{bank_id}/imports/word")
def import_word(bank_id: str, db: DB, user: Teacher, file: UploadFile = File()):
    owned(db, user, bank_id)
    _, _, document = read_word_upload(file, allow_doc=True)
    result = candidates(document)
    if not result["count"]:
        raise HTTPException(422, "未识别到题目，请检查题号，或先在试卷功能中标记题目范围")
    if result["count"] > 100:
        raise HTTPException(422, "一次导入最多 100 题，请拆分文件")
    return result


@router.get("/{bank_id}/imports/exams/{exam_id}")
def import_exam(bank_id: str, exam_id: str, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    exam = owned_exam(db, user, exam_id)
    if exam.course_id != bank.course_id:
        raise HTTPException(404, "当前课程没有该试卷")
    confirmed = {key: meta for key, meta in exam.questions.items() if meta.get("confirmed")}
    result = candidates(decode(stored_document(db, exam).content), confirmed)
    if not result["count"]:
        raise HTTPException(422, "请先在试卷编辑器中确认需要导入的题目")
    return result


@router.post("/{bank_id}/imports/adopt", status_code=201)
def adopt_import(bank_id: str, data: Adopt, db: DB, user: Teacher):
    bank = owned(db, user, bank_id)
    # A deterministic job marker makes import retries atomic and idempotent.
    from uuid import NAMESPACE_URL, uuid5
    marker = uuid5(NAMESPACE_URL, f"qbank-import:{bank.id}:{data.request_key}").hex
    prior = list(db.scalars(select(BankQuestion).where(BankQuestion.bank_id == bank.id, BankQuestion.job_id == marker)))
    if prior:
        return {"count": len(prior), "bank_revision": bank.revision}
    for index, item in enumerate(data.questions):
        item.confirmed = False
        create_question(db, user, bank, item, job_id=marker, slot=index)
    db.commit()
    return {"count": len(data.questions), "bank_revision": bank.revision}
