import math
import re
from datetime import datetime

from fastapi import HTTPException

from .parser import metric_key
from .schemas import MappingConfig


PRESENT = {"出勤", "到课", "已到", "正常", "出席", "present", "attended", "yes", "true", "1"}
ABSENT = {"缺勤", "缺席", "未到", "旷课", "未出勤", "absent", "missing", "no", "false", "0"}
DONE = {"已交", "已提交", "完成", "已完成", "按时完成", "submitted", "done", "complete", "completed", "yes", "true", "1"}
NOT_DONE = {"未交", "未提交", "未完成", "缺交", "逾期未交", "missing", "not submitted", "incomplete", "no", "false", "0"}


def normalized_text(value):
    return str(value or "").strip().casefold()


def parse_number(value):
    if value is None or isinstance(value, bool):
        return None, False
    if isinstance(value, (int, float)):
        number = float(value)
        return (number, False) if math.isfinite(number) else (None, False)
    text = str(value).strip().replace(",", "")
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    match = re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text.replace("分", "").strip())
    if not match:
        return None, percent
    try:
        number = float(match.group())
        return (number, percent) if math.isfinite(number) else (None, percent)
    except ValueError:
        return None, percent


def parse_datetime(value):
    if value is None or not str(value).strip():
        return None
    try:
        import pandas as pd
        result = pd.to_datetime(value, errors="coerce")
        if pd.isna(result):
            return None
        if getattr(result, "tzinfo", None):
            result = result.tz_convert(None)
        return result.to_pydatetime() if hasattr(result, "to_pydatetime") else result
    except (TypeError, ValueError, OverflowError):
        return None


def validate_mapping(mapping: MappingConfig, columns):
    used = [mapping.student_code]
    used.extend(item for item in (mapping.student_name, mapping.occurred_at, mapping.activity,
                                  mapping.knowledge_tag, mapping.maximum_column) if item)
    used.extend(metric.column for metric in mapping.metrics)
    missing = sorted(set(used) - set(columns))
    if missing:
        raise HTTPException(422, "字段映射引用了当前工作表中不存在的列：" + "、".join(missing))
    if len({(item.column, item.label) for item in mapping.metrics}) != len(mapping.metrics):
        raise HTTPException(422, "同一列和指标名称不能重复映射")


def preview_rows(rows, mapping):
    issues, valid = [], 0
    for position, row in enumerate(rows, start=1):
        source_row = row.get("__source_row", position + 1)
        student_code = str(row.get(mapping.student_code) or "").strip()
        if not student_code:
            issues.append({"row": source_row, "reason": "缺少学生标识"})
            continue
        populated = any(row.get(metric.column) not in (None, "") for metric in mapping.metrics)
        if not populated:
            issues.append({"row": source_row, "reason": "没有可分析的指标值"})
            continue
        valid += 1
    return {"row_count": len(rows), "valid_count": valid, "invalid_count": len(issues), "issues": issues[:50]}


def observation_rows(rows, mapping, batch):
    from .models import LearningObservation

    for row in rows:
        code = str(row.get(mapping.student_code) or "").strip()
        if not code:
            continue
        name = str(row.get(mapping.student_name) or "").strip() if mapping.student_name else ""
        when = parse_datetime(row.get(mapping.occurred_at)) if mapping.occurred_at else None
        activity = str(row.get(mapping.activity) or "").strip() if mapping.activity else ""
        tag = str(row.get(mapping.knowledge_tag) or "").strip() if mapping.knowledge_tag else ""
        dynamic_max, _ = parse_number(row.get(mapping.maximum_column)) if mapping.maximum_column else (None, False)
        for metric in mapping.metrics:
            original = row.get(metric.column)
            if original is None or not str(original).strip():
                continue
            text = str(original).strip()[:160]
            number, is_percent = parse_number(original)
            maximum = dynamic_max or metric.maximum
            if metric.kind == "score" and is_percent and not maximum:
                maximum = 100.0
            if metric.kind == "homework":
                token = normalized_text(original)
                if token in DONE:
                    number = 1.0
                elif token in NOT_DONE:
                    number = 0.0
            elif metric.kind == "attendance":
                token = normalized_text(original)
                if token in PRESENT:
                    number = 1.0
                elif token in ABSENT:
                    number = 0.0
            normalized = None
            if metric.kind == "score" and number is not None and maximum and maximum > 0:
                normalized = min(100.0, max(0.0, number / maximum * 100))
            yield LearningObservation(
                batch_id=batch.id, course_id=batch.course_id, class_code=batch.class_code,
                student_code=code[:64], student_name=name[:100], occurred_at=when,
                activity=activity[:160], metric_key=metric_key(metric.label), metric_label=metric.label,
                metric_type=metric.kind, value_number=number, value_text=text, maximum=maximum,
                normalized_score=normalized, knowledge_tag=tag[:160], source_row=int(row.get("__source_row", 0) or 0),
            )


def batch_view(row):
    return {"id": row.id, "course_id": row.course_id, "class_code": row.class_code, "term_label": row.term_label,
            "title": row.title, "original_filename": row.original_filename, "extension": row.extension,
            "sheet_name": row.sheet_name, "sheet_names": row.sheet_names or [], "columns": row.columns or [],
            "sample_rows": row.sample_rows or [], "mapping": row.mapping or {}, "row_count": row.row_count,
            "valid_count": row.valid_count, "invalid_count": row.invalid_count, "processed_count": row.processed_count,
            "status": row.status, "error": row.error, "created_at": row.created_at, "confirmed_at": row.confirmed_at}


def plan_view(row):
    return {"id": row.id, "course_id": row.course_id, "class_code": row.class_code, "scope": row.scope,
            "student_code": row.student_code, "title": row.title, "focus": row.focus, "content": row.content,
            "generation_source": row.generation_source, "resource_ids": row.resource_ids or [],
            "batch_ids": row.batch_ids or [], "status": row.status, "created_at": row.created_at,
            "updated_at": row.updated_at}


def shared_view(row):
    return {"id": row.id, "source_type": row.source_type, "source_id": row.source_id,
            "source_revision": row.source_revision, "version": row.version, "owner_id": row.owner_id,
            "course_id": row.course_id, "title": row.title, "summary": row.summary, "subject": row.subject,
            "academic_level": row.academic_level, "term_label": row.term_label, "section": row.section,
            "keywords": row.keywords or [], "status": row.status, "published_at": row.published_at,
            "snapshot": row.snapshot}


def shared_view_with_author(db, row):
    from ..models import User
    owner = db.get(User, row.owner_id)
    return shared_view(row) | {"owner_name": owner.name if owner else ""}
