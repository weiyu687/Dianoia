import json
import shutil
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from sqlalchemy import func, select, update

from ..auth import course_access
from ..db import DATA_DIR
from ..lessons import Source, lesson_sources
from ..models import ClassGroup, Course, Resource, identifier, now
from .content import asset_ids, plain
from .models import BankGenerationJob, BankQuestion, BankRelease, QuestionAnswer, QuestionAsset, QuestionBank, QuestionVersion, ReleaseQuestion
from .schemas import BankUpdate, Cover, Question

FILES = DATA_DIR / "question-banks"


def owned(db, user, bank_id):
    bank = db.get(QuestionBank, bank_id)
    if not bank or bank.owner_id != user.id:
        raise HTTPException(404, "题库不存在")
    course_access(db, user, bank.course_id)
    return bank


def bump(db, bank, expected=None, **changes):
    statement = update(QuestionBank).where(QuestionBank.id == bank.id)
    if expected is not None:
        statement = statement.where(QuestionBank.revision == expected)
    result = db.execute(statement.values(revision=QuestionBank.revision + 1, updated_at=now(), **changes)
                        .execution_options(synchronize_session=False))
    if not result.rowcount:
        raise HTTPException(409, "题库已在其他窗口更新，请刷新后重试")
    db.expire(bank)


def editable(bank):
    if bank.archived:
        raise HTTPException(409, "请先恢复已归档的题库再编辑")


def question_rows(db, bank_id):
    return select(BankQuestion).where(BankQuestion.bank_id == bank_id, BankQuestion.deleted.is_(False))


def question_count(db, bank_id):
    return db.scalar(select(func.count()).select_from(question_rows(db, bank_id).subquery()))


def question_owned(db, bank, question_id):
    row = db.get(BankQuestion, question_id)
    if not row or row.bank_id != bank.id or row.deleted:
        raise HTTPException(404, "题目不存在")
    return row


def question_content(db, row):
    version = db.get(QuestionVersion, row.version_id)
    answer = db.get(QuestionAnswer, row.version_id)
    return {**version.content, "answer": answer.content}


def question_view(db, row, summary=False):
    data = question_content(db, row)
    result = {"id": row.id, "revision": row.revision, "position": row.position, "version_id": row.version_id}
    if summary:
        return result | {key: data[key] for key in ("kind", "section_id", "material_id", "tags", "difficulty", "confirmed", "included")} | {"excerpt": plain(data["body"])[:240]}
    labels = []
    for source in data["sources"]:
        resource = db.get(Resource, source["resource_id"])
        labels.append({"title": resource.title if resource else "原参考资料已移除", "start": source["start"], "end": source["end"]})
    return result | {"question": data, "source_labels": labels}


def release_view(row):
    return {key: getattr(row, key) for key in ("id", "number", "draft_revision", "status", "class_codes", "created_at")}


def job_view(row):
    return {key: getattr(row, key) for key in ("id", "status", "stage", "completed", "total", "error", "created_at", "updated_at")}


def bank_view(db, bank, detail=False):
    release = db.get(BankRelease, bank.release_id) if bank.release_id else None
    data = {key: getattr(bank, key) for key in ("id", "course_id", "title", "description", "tags", "cover", "revision", "archived", "created_at", "updated_at")}
    data.update(question_count=question_count(db, bank.id), release=release_view(release) if release else None,
                has_unpublished_changes=bool(release and release.draft_revision != bank.revision),
                status="archived" if bank.archived else "published" if release and release.status == "active" else "draft" if not release else "offline")
    if detail:
        data.update(sections=bank.sections, materials=bank.materials, sources=bank.sources,
                    classes=[{"code": c.code, "name": c.name} for c in db.scalars(select(ClassGroup).where(ClassGroup.course_id == bank.course_id).order_by(ClassGroup.code))],
                    releases=[release_view(r) for r in db.scalars(select(BankRelease).where(BankRelease.bank_id == bank.id).order_by(BankRelease.number.desc()))],
                    jobs=[job_view(j) for j in db.scalars(select(BankGenerationJob).where(BankGenerationJob.bank_id == bank.id).order_by(BankGenerationJob.created_at.desc()).limit(10))])
    return data


def check_sources(db, user, bank, sources):
    if not sources:
        return "", []
    chunks, references, _ = lesson_sources(db, user, bank.course_id, sources)
    return chunks, references


def check_docs(db, bank, docs):
    ids = set().union(*(asset_ids(doc) for doc in docs)) if docs else set()
    if ids:
        available = set(db.scalars(select(QuestionAsset.id).where(QuestionAsset.bank_id == bank.id, QuestionAsset.kind == "image", QuestionAsset.id.in_(ids))))
        if ids - available:
            raise HTTPException(422, "正文图片不属于当前题库或已不可用，请重新上传")
        if any(not (FILES / (key + ".webp")).is_file() for key in ids):
            raise HTTPException(422, "题目图片文件不可用，请重新上传")


def validate_question(db, user, bank, data):
    if data.section_id and data.section_id not in {s["id"] for s in bank.sections}:
        raise HTTPException(422, "请选择当前题库中的章节")
    if data.material_id and data.material_id not in {m["id"] for m in bank.materials}:
        raise HTTPException(422, "请选择当前题库的共享材料")
    check_docs(db, bank, [data.body, data.answer.body, data.answer.explanation, *[o.body for o in data.options]])
    check_sources(db, user, bank, data.sources)
    if len(data.model_dump_json()) > 240000:
        raise HTTPException(422, "单题内容过大，请精简至 240 KB 内")


def write_version(db, row, data):
    version = QuestionVersion(id=identifier(), question_id=row.id, number=row.revision,
                              content=data.model_dump(exclude={"answer"}))
    db.add(version)
    db.flush()
    db.add(QuestionAnswer(version_id=version.id, content=data.answer.model_dump()))
    row.version_id = version.id
    row.search_text = plain(data.body)[:5000] + " " + " ".join(data.tags)


def create_question(db, user, bank, data, *, job_id=None, slot=None, question_id=None):
    editable(bank)
    validate_question(db, user, bank, data)
    # The bank row serializes question creation with publication and other writers.
    bump(db, bank)
    if question_count(db, bank.id) >= 2000:
        raise HTTPException(422, "单个题库最多保存 2000 题，请新建另一个题库")
    row = BankQuestion(id=question_id or identifier(), bank_id=bank.id, position=(db.scalar(select(func.max(BankQuestion.position)).where(BankQuestion.bank_id == bank.id)) or 0) + 1,
                       job_id=job_id, slot=slot)
    db.add(row)
    db.flush()
    write_version(db, row, data)
    return row


def save_question(db, user, bank, row, expected, data):
    editable(bank)
    validate_question(db, user, bank, data)
    bump(db, bank)
    result = db.execute(update(BankQuestion).where(BankQuestion.id == row.id, BankQuestion.revision == expected, BankQuestion.deleted.is_(False))
                        .values(revision=BankQuestion.revision + 1).execution_options(synchronize_session=False))
    if not result.rowcount:
        raise HTTPException(409, "题目已更新，请刷新后重试")
    db.expire(row)
    write_version(db, row, data)


def update_bank(db, user, bank, data: BankUpdate):
    check_sources(db, user, bank, data.sources)
    check_docs(db, bank, [m.body for m in data.materials])
    if data.cover.asset_id:
        asset = db.get(QuestionAsset, data.cover.asset_id)
        if not asset or asset.bank_id != bank.id or asset.kind != "cover":
            raise HTTPException(422, "封面不属于当前题库")
    if len(data.model_dump_json()) > 1500000:
        raise HTTPException(422, "共享材料过大，请减少材料数量或长度")
    section_ids, material_ids = {s.id for s in data.sections}, {m.id for m in data.materials}
    for row in db.scalars(question_rows(db, bank.id)):
        content = db.get(QuestionVersion, row.version_id).content
        if content["section_id"] and content["section_id"] not in section_ids:
            raise HTTPException(422, "章节内仍有题目，请先移动或删除这些题目")
        if content["material_id"] and content["material_id"] not in material_ids:
            raise HTTPException(422, "共享材料仍被题目引用，请先解除引用")
    if data.archived:
        busy = db.scalar(select(BankGenerationJob.id).where(BankGenerationJob.bank_id == bank.id, BankGenerationJob.status.in_(["queued", "running"])))
        if busy:
            raise HTTPException(409, "请先取消生成任务再归档")
        db.execute(update(BankRelease).where(BankRelease.bank_id == bank.id, BankRelease.status == "active").values(status="closed"))
    bump(db, bank, data.revision, **data.model_dump(exclude={"revision"}))


def preflight(db, bank):
    issues, selected, size = [], [], 0
    for row in db.scalars(question_rows(db, bank.id).order_by(BankQuestion.position, BankQuestion.id)):
        item = question_view(db, row)
        data = Question.model_validate(item["question"])
        if not data.included:
            continue
        problems = data.problems() + ([] if data.confirmed else ["尚未核对确认"])
        if problems:
            issues.append({"question_id": row.id, "excerpt": plain(data.body)[:80], "messages": problems})
        selected.append(item)
        size += len(json.dumps(item, ensure_ascii=False))
        if size > 8000000:
            raise HTTPException(422, "本次发布内容超过 8 MB，请分成多个题库")
    if not selected:
        issues.append({"question_id": None, "excerpt": "题库", "messages": ["至少选择一道题目用于发布"]})
    for material in bank.materials:
        check_docs(db, bank, [material["body"]])
    return {"ready": not issues and not bank.archived, "issues": issues, "question_count": len(selected)}, selected


def publish(db, user, bank, data):
    prior = db.scalar(select(BankRelease).where(BankRelease.bank_id == bank.id, BankRelease.request_key == data.request_key))
    classes = sorted(set(data.class_codes))
    if prior:
        if prior.draft_revision != data.revision + 1 or prior.class_codes != classes:
            raise HTTPException(409, "此发布请求标识已用于其他内容")
        return prior
    editable(bank)
    valid = set(db.scalars(select(ClassGroup.code).where(ClassGroup.course_id == bank.course_id)))
    if set(classes) - valid:
        raise HTTPException(422, "发布班级必须属于当前课程")
    if not valid:
        raise HTTPException(422, "请先由学校管理端为当前课程录入教学班")
    bump(db, bank, data.revision)
    check, questions = preflight(db, bank)
    if not check["ready"]:
        raise HTTPException(422, "请先完成发布预检中的问题；未准备好的题目可取消勾选「参与发布」")
    db.execute(update(BankRelease).where(BankRelease.bank_id == bank.id, BankRelease.status == "active").values(status="superseded"))
    course = db.get(Course, bank.course_id)
    number = (db.scalar(select(func.max(BankRelease.number)).where(BankRelease.bank_id == bank.id)) or 0) + 1
    snapshot = {"schema_version": 1, "title": bank.title, "description": bank.description, "tags": bank.tags,
                "course_id": bank.course_id, "course_name": course.name, "cover": bank.cover,
                "sections": bank.sections, "materials": bank.materials, "questions": questions}
    release = BankRelease(id=identifier(), bank_id=bank.id, number=number, draft_revision=bank.revision,
                          request_key=data.request_key, class_codes=classes, snapshot=snapshot)
    db.add(release)
    db.flush()
    db.add_all([ReleaseQuestion(release_id=release.id, version_id=q["version_id"], position=i) for i, q in enumerate(questions)])
    bank.release_id = release.id
    return release


def clone_bank(db, user, bank, key):
    new_id = uuid5(NAMESPACE_URL, f"dianoia:bank-copy:{user.id}:{bank.id}:{key}").hex
    if existing := db.get(QuestionBank, new_id):
        return existing
    copied = QuestionBank(id=new_id, owner_id=user.id, course_id=bank.course_id, title=bank.title[:156] + "（副本）",
                          description=bank.description, tags=bank.tags, cover=bank.cover, sections=bank.sections,
                          materials=bank.materials, sources=bank.sources)
    db.add(copied)
    db.flush()
    mapping = {}
    for asset in db.scalars(select(QuestionAsset).where(QuestionAsset.bank_id == bank.id)):
        replacement = QuestionAsset(id=identifier(), bank_id=new_id, name=asset.name, kind=asset.kind, width=asset.width, height=asset.height)
        source = FILES / (asset.id + ".webp")
        if not source.is_file():
            raise HTTPException(422, "原题库存在不可用图片，请先修正")
        shutil.copyfile(source, FILES / (replacement.id + ".webp"))
        if asset.kind == "cover":
            from PIL import Image
            with Image.open(source) as image:
                image.resize((400, 225), Image.Resampling.LANCZOS).save(FILES / (replacement.id + "-thumb.webp"), "WEBP", quality=85)
        db.add(replacement)
        mapping[asset.id] = replacement.id

    def remap(value):
        if isinstance(value, dict):
            return {k: mapping.get(v, v) if k in {"assetId", "asset_id"} else remap(v) for k, v in value.items()}
        if isinstance(value, list):
            return [remap(v) for v in value]
        return value

    copied.cover, copied.materials = remap(bank.cover), remap(bank.materials)
    for original in db.scalars(question_rows(db, bank.id).order_by(BankQuestion.position)):
        content = Question.model_validate(remap(question_content(db, original)))
        create_question(db, user, copied, content)
    return copied
