import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import and_, func, select, update

from .. import ai
from ..auth import DB, Teacher, course_access
from ..course_models import CourseJob, DigitalCourse
from ..db import DATA_DIR
from ..models import (ClassGroup, Course, MindMap, TeachingPresentation, identifier, now)
from ..question_banks.models import BankRelease, QuestionBank
from .models import (AnalyticsDashboardTemplate, AnalyticsMappingTemplate, LearningImportBatch,
                     LearningObservation, LearningPlan, SharedLearningResource)
from .parser import TableParseError, inspect_table, read_parsed, write_parsed
from .schemas import (GeneratePlan, MappingConfig, PublishResource, SaveDashboardTemplate,
                      SaveMappingTemplate, SheetSelection, UpdateImport, UpdatePlan)
from .service import (batch_view, metric_key, observation_rows, plan_view, preview_rows, shared_view,
                      shared_view_with_author, validate_mapping)

router = APIRouter(prefix="/api/learning-analytics", tags=["learning analytics"])
FILES = DATA_DIR / "learning-analytics"
TYPE_LABELS = {"presentation": "演示文稿", "mind_map": "思维导图", "digital_course": "数字课程", "question_bank": "在线题库"}
BUILTIN_MAPPING_TEMPLATES = [
    {"id": "builtin-score", "title": "成绩表（姓名/学号 + 多项成绩）", "category": "score", "builtin": True},
    {"id": "builtin-homework", "title": "作业完成情况", "category": "homework", "builtin": True},
    {"id": "builtin-attendance", "title": "考勤记录", "category": "attendance", "builtin": True},
]
BUILTIN_DASHBOARD_TEMPLATES = [
    {"id": "class-overview", "title": "班级综合学情", "config": {"panels": ["metrics", "trend", "distribution", "students"]}},
    {"id": "score-analysis", "title": "成绩与作业", "config": {"panels": ["score", "trend", "distribution"]}},
    {"id": "attendance-analysis", "title": "考勤与参与", "config": {"panels": ["attendance", "trend", "students"]}},
]


def owned_batch(db, user, batch_id):
    row = db.get(LearningImportBatch, batch_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "导入批次不存在")
    course_access(db, user, row.course_id)
    return row


def parse_upload_error(error):
    if isinstance(error, TableParseError):
        return HTTPException(422, str(error))
    return HTTPException(422, "表格文件无法解析，请检查格式后重试")


def safe_title(value, fallback):
    result = re.sub(r"[\x00-\x1f]", " ", (value or "")).strip()
    return (result[:160] or fallback)


def guess_mapping(columns):
    def choose(words):
        return next((column for column in columns if any(word in column.casefold() for word in words)), None)
    student = choose(("学号", "学生编号", "student id", "studentid", "student_id", "student_code", "学员编号", "姓名")) or columns[0]
    name = choose(("姓名", "学生名", "student name"))
    date = choose(("日期", "时间", "date", "time", "周次"))
    tag = choose(("知识点", "章节", "单元", "topic", "chapter"))
    activity = choose(("作业名称", "测验名称", "课堂活动", "活动名称", "作业", "activity", "assignment"))
    maximum_column = choose(("满分", "总分", "最高分", "max score", "maximum"))
    metadata_words = ("班级", "课程班", "学院", "专业", "学校", "性别", "校区", "班号")
    non_ids = [column for column in columns if column not in {student, name, date, tag, activity, maximum_column}
               and not any(word in column.casefold() for word in metadata_words)]
    metrics = []
    for column in non_ids[:12]:
        lowered = column.casefold()
        kind = "attendance" if any(word in lowered for word in ("考勤", "出勤", "签到", "attendance")) else (
            "homework" if any(word in lowered for word in ("作业", "提交", "完成", "homework")) else "score")
        metrics.append({"column": column, "label": column, "kind": kind, "maximum": 100 if kind == "score" else None})
    if not metrics and student != columns[-1]:
        metrics = [{"column": columns[-1], "label": columns[-1], "kind": "score", "maximum": None}]
    return {"student_code": student, "student_name": name, "occurred_at": date, "activity": activity,
            "knowledge_tag": tag, "maximum_column": maximum_column, "metrics": metrics}


def mapping_template_view(row):
    return {"id": row.id, "title": row.title, "category": row.category, "config": row.config, "builtin": False}


def metric_filter(batch, metric_key_value, class_code):
    return [LearningObservation.batch_id == batch.id,
            LearningObservation.metric_key == metric_key_value,
            *([LearningObservation.class_code == class_code] if class_code else [])]


def summarize_batch(db, batch, selected_metric, class_code):
    metrics = db.execute(
        select(LearningObservation.metric_key, LearningObservation.metric_label, LearningObservation.metric_type,
               func.count(LearningObservation.id).label("entries"), func.count(func.distinct(LearningObservation.student_code)).label("students"))
        .where(LearningObservation.batch_id == batch.id,
               *([LearningObservation.class_code == class_code] if class_code else []))
        .group_by(LearningObservation.metric_key, LearningObservation.metric_label, LearningObservation.metric_type)
        .order_by(LearningObservation.metric_label)
    ).all()
    metric_list = [{"key": row.metric_key, "label": row.metric_label, "kind": row.metric_type,
                    "entries": int(row.entries or 0), "students": int(row.students or 0)} for row in metrics]
    if not metric_list:
        return {"batch": batch_view(batch), "metrics": [], "selected_metric": None, "summary": {},
                "distribution": [], "categories": [], "students": [], "history": []}
    selected = next((row for row in metric_list if row["key"] == selected_metric), metric_list[0])
    conditions = metric_filter(batch, selected["key"], class_code)
    values = db.scalars(select(LearningObservation).where(*conditions).order_by(LearningObservation.occurred_at, LearningObservation.source_row)).all()
    numeric = [row.value_number for row in values if row.value_number is not None]
    normalized = [row.normalized_score for row in values if row.normalized_score is not None]
    text_counts = Counter(row.value_text for row in values if row.value_number is None and row.value_text)
    by_student = defaultdict(list)
    for row in values:
        by_student[row.student_code].append(row)
    students = []
    for code, items in by_student.items():
        nums = [item.value_number for item in items if item.value_number is not None]
        norms = [item.normalized_score for item in items if item.normalized_score is not None]
        ordered = sorted(items, key=lambda item: (item.occurred_at or batch.created_at, item.source_row))
        students.append({"student_code": code, "student_name": next((item.student_name for item in items if item.student_name), ""),
                         "entries": len(items), "average": round(sum(nums) / len(nums), 2) if nums else None,
                         "normalized_average": round(sum(norms) / len(norms), 2) if nums and len(norms) == len(nums) else None,
                         "latest_value": ordered[-1].value_number if ordered else None,
                         "latest_text": ordered[-1].value_text if ordered else "",
                         "latest_at": ordered[-1].occurred_at})
    students.sort(key=lambda item: (item["student_name"], item["student_code"]))
    distribution = []
    all_normalized = bool(numeric) and len(normalized) == len(numeric)
    if selected["kind"] == "score" and normalized and all_normalized:
        labels = ["0–59", "60–69", "70–79", "80–89", "90–100"]
        counts = [0] * 5
        for value in normalized:
            index = 0 if value < 60 else 1 if value < 70 else 2 if value < 80 else 3 if value < 90 else 4
            counts[index] += 1
        distribution = [{"label": label, "value": count} for label, count in zip(labels, counts)]
    category_rows = [{"label": label, "value": count} for label, count in text_counts.most_common(8)]
    summary = {"students": len(by_student), "entries": len(values), "numeric_entries": len(numeric),
               "missing_values": max(0, batch.valid_count - len(values)),
               "average": round(sum(numeric) / len(numeric), 2) if numeric else None,
               "normalized_average": round(sum(normalized) / len(normalized), 2) if all_normalized and normalized else None,
               "rate": round(sum(numeric) / len(numeric) * 100, 1) if numeric and selected["kind"] in {"attendance", "homework"} else None}
    history_rows = db.execute(
        select(LearningImportBatch.id, LearningImportBatch.title, LearningImportBatch.term_label,
               LearningImportBatch.created_at, func.avg(LearningObservation.normalized_score).label("normalized"),
               func.avg(LearningObservation.value_number).label("average"),
               func.count(LearningObservation.value_number).label("numeric_count"),
               func.count(LearningObservation.normalized_score).label("normalized_count"),
               func.count(LearningObservation.id).label("count"))
        .join(LearningObservation, LearningObservation.batch_id == LearningImportBatch.id)
        .where(LearningImportBatch.course_id == batch.course_id, LearningImportBatch.owner_id == batch.owner_id,
               LearningImportBatch.status == "ready", LearningObservation.metric_key == selected["key"],
               *([LearningObservation.class_code == class_code] if class_code else []))
        .group_by(LearningImportBatch.id).order_by(LearningImportBatch.created_at.desc()).limit(12)
    ).all()
    history = [{"batch_id": row.id, "title": row.title, "term_label": row.term_label,
                "date": row.created_at,
                "average": (round(float(row.normalized), 2) if row.normalized is not None and row.normalized_count == row.numeric_count else None)
                if selected["kind"] == "score" else
                (round(float(row.average) * 100, 1) if selected["kind"] in {"attendance", "homework"} and row.average is not None
                 else round(float(row.average), 2) if row.average is not None else None),
                "comparable": row.normalized is not None and row.normalized_count == row.numeric_count if selected["kind"] == "score" else True,
                "entries": int(row.count or 0)}
               for row in reversed(history_rows)]
    return {"batch": batch_view(batch), "metrics": metric_list, "selected_metric": selected,
            "summary": summary, "distribution": distribution, "categories": category_rows,
            "students": students[:500], "history": history}


def snapshot_for(db, user, data):
    course_access(db, user, int(data.course_id))
    if data.source_type == "presentation":
        row = db.get(TeachingPresentation, data.source_id)
        if not row or row.owner_id != user.id or row.course_id != data.course_id:
            raise HTTPException(404, "演示文稿不存在或无权发布")
        snapshot = json.loads(json.dumps(row.document, ensure_ascii=False))
        def strip_private(value):
            if isinstance(value, dict):
                return {key: strip_private(item) for key, item in value.items()
                        if key not in {"notes", "citations", "sources", "speaker_notes", "teacher_notes"}}
            if isinstance(value, list):
                return [strip_private(item) for item in value]
            return value
        return row, strip_private(snapshot)
    if data.source_type == "mind_map":
        row = db.get(MindMap, data.source_id)
        if not row or row.owner_id != user.id or row.course_id != data.course_id:
            raise HTTPException(404, "思维导图不存在或无权发布")
        snapshot = json.loads(json.dumps(row.document, ensure_ascii=False))
        def strip_map(node):
            if isinstance(node, dict):
                node.pop("sources", None)
                for child in node.get("children", []):
                    strip_map(child)
        snapshot.pop("sources", None)
        strip_map(snapshot.get("root", {}))
        return row, snapshot
    if data.source_type == "digital_course":
        row = db.get(DigitalCourse, data.source_id)
        if not row or row.owner_id != user.id or row.course_id != data.course_id:
            raise HTTPException(404, "数字课程不存在或无权发布")
        job = db.get(CourseJob, row.video_id) if row.video_id else None
        if not job or job.status != "succeeded":
            raise HTTPException(409, "请先完成数字课程视频生产再发布")
        return row, {"title": row.title, "slides": row.slides, "video_job_id": job.id, "video_available": True}
    if data.source_type == "question_bank":
        row = db.get(QuestionBank, data.source_id)
        if not row or row.owner_id != user.id or row.course_id != data.course_id or row.archived:
            raise HTTPException(404, "在线题库不存在或无权发布")
        release = db.get(BankRelease, row.release_id) if row.release_id else None
        if not release or release.status != "active":
            raise HTTPException(409, "请先在在线题库中发布一个有效版本")
        return release, release.snapshot
    raise HTTPException(422, "暂不支持此资源类型")


@router.get("/context")
def context(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    course = db.get(Course, course_id)
    classes = db.scalars(select(ClassGroup).where(ClassGroup.course_id == course_id).order_by(ClassGroup.name))
    batches = db.scalars(select(LearningImportBatch).where(
        LearningImportBatch.owner_id == user.id, LearningImportBatch.course_id == course_id
    ).order_by(LearningImportBatch.created_at.desc()).limit(50))
    return {"owner_id": user.id, "course": {"id": course.id, "name": course.name},
            "classes": [{"code": row.code, "name": row.name} for row in classes],
            "batches": [batch_view(row) for row in batches]}


@router.post("/imports/preview", status_code=201)
async def create_import(db: DB, user: Teacher, course_id: int = Form(...), class_code: str = Form(""),
                       term_label: str = Form(""), title: str = Form(""), sheet_name: str = Form(""),
                       file: UploadFile = File(...)):
    course_access(db, user, course_id)
    if class_code and not db.get(ClassGroup, class_code):
        raise HTTPException(422, "请选择当前课程已有的班级")
    if class_code:
        group = db.get(ClassGroup, class_code)
        if group.course_id != course_id:
            raise HTTPException(422, "班级不属于当前课程")
    filename = Path(file.filename or "data.csv").name[:255]
    data = await file.read(20 * 1024 * 1024 + 1)
    try:
        parsed = inspect_table(data, filename, sheet_name or None)
    except Exception as error:
        raise parse_upload_error(error) from error
    batch_id = identifier()
    folder = FILES / batch_id
    folder.mkdir(parents=True, exist_ok=False)
    extension = Path(filename).suffix.lower()
    original_path, parsed_path = folder / f"original{extension}", folder / "parsed.json"
    original_path.write_bytes(data)
    write_parsed(parsed_path, parsed)
    row = LearningImportBatch(
        id=batch_id, owner_id=user.id, course_id=course_id, class_code=class_code or None,
        term_label=term_label.strip()[:64], title=safe_title(title, Path(filename).stem),
        original_filename=filename, extension=extension, file_sha256=parsed["sha256"],
        original_path=str(original_path.relative_to(DATA_DIR)), parsed_path=str(parsed_path.relative_to(DATA_DIR)),
        sheet_name=parsed["sheet_name"], sheet_names=parsed["sheet_names"], columns=parsed["columns"],
        sample_rows=parsed["sample_rows"], row_count=parsed["row_count"], status="mapping",
    )
    db.add(row)
    db.commit()
    result = batch_view(row)
    result["suggested_mapping"] = guess_mapping(parsed["columns"])
    return result


@router.put("/imports/{batch_id}/sheet")
def select_sheet(batch_id: str, data: SheetSelection, db: DB, user: Teacher):
    row = owned_batch(db, user, batch_id)
    if row.status not in {"mapping", "failed"}:
        raise HTTPException(409, "已确认的批次不能切换工作表")
    original = DATA_DIR / row.original_path
    try:
        parsed = inspect_table(original.read_bytes(), row.original_filename, data.sheet_name or None)
    except Exception as error:
        raise parse_upload_error(error) from error
    write_parsed(DATA_DIR / row.parsed_path, parsed)
    row.sheet_name, row.sheet_names = parsed["sheet_name"], parsed["sheet_names"]
    row.columns, row.sample_rows, row.row_count = parsed["columns"], parsed["sample_rows"], parsed["row_count"]
    row.mapping, row.valid_count, row.invalid_count = {}, 0, 0
    row.status, row.error = "mapping", ""
    db.commit()
    result = batch_view(row)
    result["suggested_mapping"] = guess_mapping(row.columns)
    return result


@router.put("/imports/{batch_id}")
def update_import(batch_id: str, data: UpdateImport, db: DB, user: Teacher):
    row = owned_batch(db, user, batch_id)
    if row.status not in {"mapping", "failed"}:
        raise HTTPException(409, "已确认的批次不能修改名称或班级")
    if data.class_code:
        group = db.get(ClassGroup, data.class_code)
        if not group or group.course_id != row.course_id:
            raise HTTPException(422, "班级不属于当前课程")
    row.title, row.class_code, row.term_label = data.title.strip(), data.class_code, data.term_label.strip()
    row.updated_at = now()
    db.commit()
    return batch_view(row)


@router.put("/imports/{batch_id}/mapping")
def save_mapping(batch_id: str, data: MappingConfig, db: DB, user: Teacher):
    row = owned_batch(db, user, batch_id)
    if row.status not in {"mapping", "failed"}:
        raise HTTPException(409, "此批次已进入后台处理")
    validate_mapping(data, row.columns)
    parsed = read_parsed(DATA_DIR / row.parsed_path)
    counts = preview_rows(parsed, data)
    row.mapping = data.model_dump()
    row.valid_count, row.invalid_count = counts["valid_count"], counts["invalid_count"]
    row.status, row.error = "mapping", ""
    db.commit()
    return batch_view(row) | {"validation": counts}


@router.get("/imports/{batch_id}/preview")
def import_preview(batch_id: str, db: DB, user: Teacher):
    row = owned_batch(db, user, batch_id)
    if not row.mapping:
        return {"batch": batch_view(row), "validation": None}
    counts = preview_rows(read_parsed(DATA_DIR / row.parsed_path), MappingConfig.model_validate(row.mapping))
    return {"batch": batch_view(row), "validation": counts}


@router.post("/imports/{batch_id}/confirm")
def confirm_import(batch_id: str, db: DB, user: Teacher):
    row = owned_batch(db, user, batch_id)
    if row.status not in {"mapping", "failed"}:
        return batch_view(row)
    if not row.mapping:
        raise HTTPException(422, "请先完成字段映射并保存预览")
    mapping = MappingConfig.model_validate(row.mapping)
    validate_mapping(mapping, row.columns)
    counts = preview_rows(read_parsed(DATA_DIR / row.parsed_path), mapping)
    if not counts["valid_count"]:
        raise HTTPException(422, "没有包含学生标识和指标数据的有效记录")
    row.valid_count, row.invalid_count = counts["valid_count"], counts["invalid_count"]
    row.status, row.error, row.processed_count = "queued", "", 0
    row.confirmed_at, row.updated_at = now(), now()
    db.commit()
    return batch_view(row)


@router.post("/imports/{batch_id}/retry")
def retry_import(batch_id: str, db: DB, user: Teacher):
    row = owned_batch(db, user, batch_id)
    if row.status != "failed":
        raise HTTPException(409, "只有失败的批次可以重新入队")
    if not row.mapping:
        raise HTTPException(422, "请先完成字段映射")
    row.status, row.error, row.processed_count, row.updated_at = "queued", "", 0, now()
    db.commit()
    return batch_view(row)


@router.get("/imports")
def list_imports(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    rows = db.scalars(select(LearningImportBatch).where(
        LearningImportBatch.owner_id == user.id, LearningImportBatch.course_id == course_id
    ).order_by(LearningImportBatch.created_at.desc()).limit(100))
    return [batch_view(row) for row in rows]


@router.delete("/imports/{batch_id}", status_code=204)
def delete_import(batch_id: str, db: DB, user: Teacher):
    row = owned_batch(db, user, batch_id)
    if row.status in {"queued", "processing"}:
        raise HTTPException(409, "请等待导入任务完成后再删除")
    folder = FILES / batch_id
    db.delete(row)
    db.commit()
    shutil.rmtree(folder, ignore_errors=True)


@router.get("/dashboard")
def dashboard(course_id: int, db: DB, user: Teacher, batch_id: str | None = None,
              class_code: str | None = None, metric: str | None = None):
    course_access(db, user, course_id)
    if class_code:
        group = db.get(ClassGroup, class_code)
        if not group or group.course_id != course_id:
            raise HTTPException(422, "班级不属于当前课程")
    query = select(LearningImportBatch).where(LearningImportBatch.owner_id == user.id,
                                               LearningImportBatch.course_id == course_id,
                                               LearningImportBatch.status == "ready")
    if class_code:
        query = query.where((LearningImportBatch.class_code == class_code) | (LearningImportBatch.class_code.is_(None)))
    if batch_id:
        query = query.where(LearningImportBatch.id == batch_id)
    batch = db.scalar(query.order_by(LearningImportBatch.created_at.desc()).limit(1))
    if not batch:
        return {"batch": None, "metrics": [], "selected_metric": None, "summary": {}, "distribution": [],
                "categories": [], "students": [], "history": []}
    return summarize_batch(db, batch, metric, class_code)


@router.get("/students/{student_code}")
def student_detail(student_code: str, course_id: int, db: DB, user: Teacher, class_code: str | None = None):
    course_access(db, user, course_id)
    if class_code:
        group = db.get(ClassGroup, class_code)
        if not group or group.course_id != course_id:
            raise HTTPException(422, "班级不属于当前课程")
    facts = db.scalars(select(LearningObservation).join(LearningImportBatch,
        LearningImportBatch.id == LearningObservation.batch_id).where(
        LearningObservation.course_id == course_id, LearningObservation.student_code == student_code,
        LearningImportBatch.owner_id == user.id, LearningImportBatch.status == "ready",
        *([LearningObservation.class_code == class_code] if class_code else [])
    ).order_by(LearningObservation.occurred_at.desc(), LearningObservation.source_row.desc()).limit(500)).all()
    if not facts:
        raise HTTPException(404, "没有找到该学生的已导入记录")
    return {"student_code": student_code, "student_name": next((row.student_name for row in facts if row.student_name), ""),
            "entries": [{"metric_key": row.metric_key, "metric_label": row.metric_label, "metric_type": row.metric_type,
                         "value_number": row.value_number, "value_text": row.value_text, "maximum": row.maximum,
                         "normalized_score": row.normalized_score, "knowledge_tag": row.knowledge_tag,
                         "activity": row.activity, "occurred_at": row.occurred_at, "batch_id": row.batch_id,
                         "source_row": row.source_row} for row in facts]}


@router.get("/mapping-templates")
def get_mapping_templates(db: DB, user: Teacher):
    custom = db.scalars(select(AnalyticsMappingTemplate).where(AnalyticsMappingTemplate.owner_id == user.id)
                        .order_by(AnalyticsMappingTemplate.updated_at.desc()))
    return BUILTIN_MAPPING_TEMPLATES + [mapping_template_view(row) for row in custom]


@router.post("/mapping-templates", status_code=201)
def create_mapping_template(data: SaveMappingTemplate, db: DB, user: Teacher):
    row = AnalyticsMappingTemplate(owner_id=user.id, title=data.title.strip(), category=data.category,
                                   config=data.config.model_dump())
    db.add(row)
    db.commit()
    return mapping_template_view(row)


@router.delete("/mapping-templates/{template_id}", status_code=204)
def delete_mapping_template(template_id: str, db: DB, user: Teacher):
    row = db.get(AnalyticsMappingTemplate, template_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "映射模板不存在")
    db.delete(row)
    db.commit()


@router.get("/dashboard-templates")
def get_dashboard_templates(db: DB, user: Teacher):
    rows = db.scalars(select(AnalyticsDashboardTemplate).where(AnalyticsDashboardTemplate.owner_id == user.id)
                      .order_by(AnalyticsDashboardTemplate.created_at.desc()))
    return BUILTIN_DASHBOARD_TEMPLATES + [{"id": row.id, "title": row.title, "config": row.config, "builtin": False} for row in rows]


@router.post("/dashboard-templates", status_code=201)
def create_dashboard_template(data: SaveDashboardTemplate, db: DB, user: Teacher):
    row = AnalyticsDashboardTemplate(owner_id=user.id, title=data.title.strip(), config=data.config)
    db.add(row)
    db.commit()
    return {"id": row.id, "title": row.title, "config": row.config, "builtin": False}


@router.delete("/dashboard-templates/{template_id}", status_code=204)
def delete_dashboard_template(template_id: str, db: DB, user: Teacher):
    row = db.get(AnalyticsDashboardTemplate, template_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "大屏模板不存在")
    db.delete(row)
    db.commit()


def draft_text(scope, focus, stats):
    lines = ["## 数据依据", f"- 本次统计覆盖 {stats.get('students', 0)} 名学生、{stats.get('entries', 0)} 条指标记录。"]
    if stats.get("normalized_average") is not None:
        lines.append(f"- 可标准化成绩均值为 {stats['normalized_average']:.1f} 分；该值仅描述本批次，不代表学生能力等级。")
    if stats.get("average") is not None and stats.get("normalized_average") is None:
        lines.append(f"- 原始指标均值为 {stats['average']:.2f}，满分或计量口径尚未统一。")
    lines += ["", "## 后续安排", "1. 先复核缺失记录、指标口径和异常值，再据此调整教学安排。",
              "2. 结合课堂练习和学生反馈，安排一次针对性讲解或分层练习。",
              "3. 一周后用同一指标复盘变化；样本不足时不做学生能力判断。"]
    if focus.strip():
        lines += ["", "## 教师关注点", focus.strip()]
    lines += ["", "> 这是基于当前上传数据生成的教师审核草稿，不能替代教师判断。"]
    return "\n".join(lines)


@router.post("/plans", status_code=201)
def generate_plan(data: GeneratePlan, db: DB, user: Teacher):
    course_access(db, user, data.course_id)
    if data.class_code:
        group = db.get(ClassGroup, data.class_code)
        if not group or group.course_id != data.course_id:
            raise HTTPException(422, "班级不属于当前课程")
    query = select(LearningImportBatch).where(LearningImportBatch.owner_id == user.id,
        LearningImportBatch.course_id == data.course_id, LearningImportBatch.status == "ready")
    if data.batch_ids:
        query = query.where(LearningImportBatch.id.in_(data.batch_ids))
    batches = db.scalars(query.order_by(LearningImportBatch.created_at.desc()).limit(20)).all()
    if data.batch_ids and len(batches) != len(set(data.batch_ids)):
        raise HTTPException(422, "计划只能引用当前教师已完成的导入批次")
    if not batches:
        raise HTTPException(422, "请先完成一份数据导入")
    if data.scope == "student" and not data.student_code:
        raise HTTPException(422, "请选择学生")
    batch_ids = [row.id for row in batches]
    aggregate_rows = db.execute(select(LearningObservation.metric_label, LearningObservation.metric_type,
        func.count(LearningObservation.id).label("entries"), func.avg(LearningObservation.value_number).label("mean"),
        func.avg(LearningObservation.normalized_score).label("normalized_mean"),
        func.count(func.distinct(LearningObservation.student_code)).label("students"))
        .where(LearningObservation.batch_id.in_(batch_ids),
            *([LearningObservation.class_code == data.class_code] if data.class_code else []),
            *([LearningObservation.student_code == data.student_code] if data.scope == "student" else []))
        .group_by(LearningObservation.metric_label, LearningObservation.metric_type)).all()
    if not aggregate_rows:
        raise HTTPException(422, "所选范围没有可用于计划的记录")
    aggregate = {row.metric_label: {"type": row.metric_type, "entries": int(row.entries),
                 "mean": round(float(row.normalized_mean if row.normalized_mean is not None else row.mean), 2)
                 if row.normalized_mean is not None or row.mean is not None else None}
                 for row in aggregate_rows}
    total_entries = sum(int(row.entries) for row in aggregate_rows)
    students_count = 1 if data.scope == "student" else max(int(row.students or 0) for row in aggregate_rows)
    normalized_values = [(float(row.normalized_mean), int(row.entries)) for row in aggregate_rows if row.normalized_mean is not None]
    raw_values = [(float(row.mean), int(row.entries)) for row in aggregate_rows if row.mean is not None]
    stats = {"students": students_count, "entries": total_entries, "metrics": aggregate,
             "normalized_average": round(sum(value * count for value, count in normalized_values) /
                 sum(count for _, count in normalized_values), 1) if normalized_values else None,
             "average": round(raw_values[0][0], 2) if len(raw_values) == 1 else None}
    resource_ids = list(dict.fromkeys(data.resource_ids))
    resources = db.scalars(select(SharedLearningResource).where(SharedLearningResource.id.in_(resource_ids),
        SharedLearningResource.status == "published")).all() if resource_ids else []
    if len(resources) != len(resource_ids):
        raise HTTPException(422, "推荐内容只能引用仍在发布状态的资源")
    recommended = [{"title": row.title, "type": TYPE_LABELS.get(row.source_type, "学习资源"),
                    "section": row.section, "keywords": row.keywords} for row in resources]
    focus = data.focus.strip()
    if data.scope == "student":
        focus = focus.replace(data.student_code, "该生")
        student_names = set(db.scalars(select(LearningObservation.student_name).where(
            LearningObservation.batch_id.in_(batch_ids), LearningObservation.student_code == data.student_code,
            LearningObservation.student_name != "").distinct()))
        for name in student_names:
            focus = focus.replace(name, "该生")
    source = "rules"
    content = draft_text(data.scope, focus, stats)
    try:
        prompt = {"分析范围": "单个学生" if data.scope == "student" else "班级",
                  "指标汇总（不是逐条记录）": stats, "教师给定关注点": focus,
                  "已选资源": recommended}
        content = ai.generate(
            "你是学校教学支持助手。仅根据提供的脱敏聚合数值撰写可编辑的教师计划草稿。禁止推断品行、诊断能力或给学生排名；说明数据范围、样本量、待核实事项和可执行的一周教学/学习安排。"
            "推荐资源只能引用输入中已有标题，不能虚构资源。只输出 Markdown，不增加未经提供的数值。",
            json.dumps(prompt, ensure_ascii=False),
        )
        source = "ai"
    except Exception:
        pass
    title = f"{'学生学习' if data.scope == 'student' else '班级教学'}计划 · {batches[0].title}"[:160]
    plan = LearningPlan(owner_id=user.id, course_id=data.course_id, class_code=data.class_code,
        scope=data.scope, student_code=data.student_code or "", title=title, focus=focus,
        content=content, generation_source=source, resource_ids=resource_ids, batch_ids=batch_ids, status="draft")
    db.add(plan)
    db.commit()
    return plan_view(plan) | {"recommendations": recommended}


@router.get("/plans")
def list_plans(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    return [plan_view(row) for row in db.scalars(select(LearningPlan).where(
        LearningPlan.owner_id == user.id, LearningPlan.course_id == course_id
    ).order_by(LearningPlan.updated_at.desc()).limit(100))]


@router.put("/plans/{plan_id}")
def update_plan(plan_id: str, data: UpdatePlan, db: DB, user: Teacher):
    row = db.get(LearningPlan, plan_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "计划不存在")
    course_access(db, user, row.course_id)
    valid = set(db.scalars(select(SharedLearningResource.id).where(
        SharedLearningResource.id.in_(data.resource_ids), SharedLearningResource.status == "published"
    ))) if data.resource_ids else set()
    if valid != set(data.resource_ids):
        raise HTTPException(422, "计划中的推荐内容已下架，请重新选择")
    row.title, row.focus, row.content, row.resource_ids = data.title.strip(), data.focus.strip(), data.content, data.resource_ids
    row.updated_at = now()
    db.commit()
    return plan_view(row)


@router.delete("/plans/{plan_id}", status_code=204)
def delete_plan(plan_id: str, db: DB, user: Teacher):
    row = db.get(LearningPlan, plan_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "计划不存在")
    db.delete(row)
    db.commit()


@router.get("/publishables")
def publishables(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    decks = db.scalars(select(TeachingPresentation).where(TeachingPresentation.owner_id == user.id,
        TeachingPresentation.course_id == course_id).order_by(TeachingPresentation.updated_at.desc()).limit(100))
    maps = db.scalars(select(MindMap).where(MindMap.owner_id == user.id, MindMap.course_id == course_id)
                      .order_by(MindMap.updated_at.desc()).limit(100))
    courses = db.scalars(select(DigitalCourse).where(DigitalCourse.owner_id == user.id,
        DigitalCourse.course_id == course_id).order_by(DigitalCourse.updated_at.desc()).limit(100))
    banks = db.scalars(select(QuestionBank).where(QuestionBank.owner_id == user.id,
        QuestionBank.course_id == course_id, QuestionBank.archived.is_(False)).order_by(QuestionBank.updated_at.desc()).limit(100))
    return [{"source_type": "presentation", "id": row.id, "title": row.title, "revision": row.revision} for row in decks] + \
        [{"source_type": "mind_map", "id": row.id, "title": row.title, "revision": row.revision} for row in maps] + \
        [{"source_type": "digital_course", "id": row.id, "title": row.title, "revision": row.revision,
          "ready": bool(row.video_id and db.get(CourseJob, row.video_id) and db.get(CourseJob, row.video_id).status == "succeeded")} for row in courses] + \
        [{"source_type": "question_bank", "id": row.id, "title": row.title, "revision": row.revision,
          "ready": bool(row.release_id and db.get(BankRelease, row.release_id) and db.get(BankRelease, row.release_id).status == "active")} for row in banks]


@router.post("/shared-resources", status_code=201)
def publish_resource(data: PublishResource, db: DB, user: Teacher):
    source, snapshot = snapshot_for(db, user, data)
    source_revision = int(getattr(source, "revision", getattr(source, "draft_revision", 1)))
    latest = db.scalar(select(SharedLearningResource).where(
        SharedLearningResource.source_type == data.source_type, SharedLearningResource.source_id == data.source_id
    ).order_by(SharedLearningResource.version.desc()).limit(1))
    if latest and latest.owner_id != user.id:
        raise HTTPException(404, "资源不存在或无权发布")
    version = (latest.version if latest and latest.source_revision == source_revision else (latest.version + 1 if latest else 1))
    if latest and latest.source_revision == source_revision:
        latest.title, latest.summary, latest.subject = data.title.strip(), data.summary.strip(), data.subject.strip()
        latest.academic_level, latest.term_label, latest.section = data.academic_level.strip(), data.term_label.strip(), data.section.strip()
        latest.keywords, latest.snapshot = list(dict.fromkeys(item.strip() for item in data.keywords if item.strip()))[:30], snapshot
        latest.status, latest.published_at, latest.updated_at = "published", now(), now()
        db.commit()
        return shared_view(latest)
    if latest:
        db.execute(update(SharedLearningResource).where(
            SharedLearningResource.source_type == data.source_type, SharedLearningResource.source_id == data.source_id,
            SharedLearningResource.status == "published"
        ).values(status="superseded", updated_at=now()))
    row = SharedLearningResource(id=identifier(), source_type=data.source_type, source_id=data.source_id,
        source_revision=source_revision, version=version, owner_id=user.id, course_id=data.course_id,
        title=data.title.strip(), summary=data.summary.strip(), subject=data.subject.strip(),
        academic_level=data.academic_level.strip(), term_label=data.term_label.strip(), section=data.section.strip(),
        keywords=list(dict.fromkeys(item.strip() for item in data.keywords if item.strip()))[:30],
        snapshot=snapshot, status="published")
    db.add(row)
    db.commit()
    return shared_view_with_author(db, row)


@router.get("/shared-resources")
def list_shared_resources(db: DB, user: Teacher, query: str = "", source_type: str | None = None,
                          course_id: int | None = None, limit: int = 100):
    statement = select(SharedLearningResource).where(SharedLearningResource.status == "published")
    if source_type in TYPE_LABELS:
        statement = statement.where(SharedLearningResource.source_type == source_type)
    if course_id:
        course_access(db, user, course_id)
        statement = statement.where(SharedLearningResource.course_id == course_id)
    if query.strip():
        term = f"%{query.strip()[:80]}%"
        statement = statement.where((SharedLearningResource.title.ilike(term)) | (SharedLearningResource.summary.ilike(term)) |
                                   (SharedLearningResource.subject.ilike(term)) | (SharedLearningResource.section.ilike(term)))
    rows = db.scalars(statement.order_by(SharedLearningResource.published_at.desc()).limit(min(max(limit, 1), 200)))
    return [shared_view_with_author(db, row) for row in rows]


@router.get("/shared-resources/{resource_id}")
def get_shared_resource(resource_id: str, db: DB, user: Teacher):
    row = db.get(SharedLearningResource, resource_id)
    if not row or row.status != "published":
        raise HTTPException(404, "资源不存在或已下架")
    return shared_view_with_author(db, row)


@router.delete("/shared-resources/{resource_id}", status_code=204)
def withdraw_resource(resource_id: str, db: DB, user: Teacher):
    row = db.get(SharedLearningResource, resource_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "资源不存在或无权下架")
    row.status, row.updated_at = "withdrawn", now()
    db.commit()
