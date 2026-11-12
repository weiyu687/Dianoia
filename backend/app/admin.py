from io import BytesIO
from typing import Annotated
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from .auth import Administrator, DB, account_key, passwords
from .models import ClassGroup, Course, Enrollment, LoginSession, Student, TeachingAssignment, User

router = APIRouter(prefix="/api/admin", tags=["school administration"])
SHEETS = {
    "教师": ("工号", "姓名"),
    "学生": ("学号", "姓名"),
    "课程": ("课程编号", "课程名称"),
    "教学班": ("班级编号", "班级名称", "课程编号"),
    "任课": ("工号", "课程编号"),
    "名单": ("学号", "班级编号"),
}


@router.get("/overview")
def overview(db: DB, user: Administrator):
    entities = {"students": Student, "courses": Course, "classes": ClassGroup}
    counts = {label: db.scalar(select(func.count()).select_from(table)) for label, table in entities.items()}
    rows = db.scalars(select(User).where(User.role == "teacher").order_by(User.username)).all()
    return {
        **counts,
        "teachers": len(rows),
        "accounts": [{"id": row.id, "username": row.username, "name": row.name, "enabled": row.enabled} for row in rows],
    }


@router.get("/template")
def template(user: Administrator):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, fields in SHEETS.items():
        sheet = workbook.create_sheet(name)
        sheet.append(fields)
    buffer = BytesIO()
    workbook.save(buffer)
    return Response(
        buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="dianoia-import.xlsx"'},
    )


def read_sheets(file):
    blob = file.file.read(2 * 1024 * 1024 + 1)
    if not file.filename or not file.filename.lower().endswith(".xlsx") or len(blob) > 2 * 1024 * 1024:
        raise HTTPException(422, "请选择不超过 2 MB 的 XLSX 导入表")
    try:
        with ZipFile(BytesIO(blob)) as archive:
            if sum(member.file_size for member in archive.infolist()) > 20 * 1024 * 1024:
                raise HTTPException(422, "工作簿解压后超出限制")
        workbook = load_workbook(BytesIO(blob), read_only=True, keep_links=False)
    except (BadZipFile, InvalidFileException, ValueError, KeyError) as error:
        raise HTTPException(422, "无法打开工作簿") from error
    data = {}
    errors = []
    try:
        for name, fields in SHEETS.items():
            data[name] = []
            if name not in workbook.sheetnames:
                continue
            sheet = workbook[name]
            rows = sheet.iter_rows(max_col=len(fields))
            header = tuple(str(cell.value or "").strip() for cell in next(rows, ()))
            if header != fields:
                errors.append(f"{name}表头应为 {'、'.join(fields)}")
                continue
            for index, row in enumerate(rows, start=2):
                if index > 2001:
                    errors.append(f"{name}最多支持 2000 行")
                    break
                values = tuple(str(cell.value).strip() if cell.value is not None else "" for cell in row)
                if not any(values):
                    continue
                if (not all(values) or any(cell.data_type == "f" for cell in row)
                        or len(values[0]) > 64 or any(len(value) > 100 for value in values)):
                    errors.append(f"{name}第 {index} 行有空值、公式或字段超长")
                    continue
                data[name].append((index, values))
    finally:
        workbook.close()
    return data, errors


@router.post("/import")
def import_school(db: DB, user: Administrator, file: Annotated[UploadFile, File()], apply: Annotated[bool, Form()] = False):
    data, errors = read_sheets(file)
    counts = {name: {"added": 0, "updated": 0, "unchanged": 0} for name in SHEETS}
    teachers = {row.username: row for row in db.scalars(select(User))}
    courses = {row.code: row for row in db.scalars(select(Course))}
    students = {row.code: row for row in db.scalars(select(Student))}
    classes = {row.code: row for row in db.scalars(select(ClassGroup))}
    assignments = {(row.teacher_id, row.course_id) for row in db.scalars(select(TeachingAssignment))}
    enrollments = {(row.student_code, row.class_code) for row in db.scalars(select(Enrollment))}

    def upsert(name, lookup, key, factory, values):
        existing = lookup.get(key)
        if existing is None:
            existing = factory(**values)
            lookup[key] = existing
            db.add(existing)
            counts[name]["added"] += 1
        elif any(getattr(existing, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(existing, key, value)
            counts[name]["updated"] += 1
        else:
            counts[name]["unchanged"] += 1

    for name, rows in data.items():
        seen = set()
        for row, values in rows:
            key = tuple(values) if name in {"任课", "名单"} else values[0]
            if name in {"教师", "任课"}:
                key = account_key(key) if isinstance(key, str) else (account_key(key[0]), key[1])
            if key in seen:
                errors.append(f"{name}第 {row} 行重复")
                continue
            seen.add(key)
            first, second, *rest = values
            if name == "教师":
                existing = teachers.get(key)
                if existing is None:
                    teacher = User(username=key, name=second, role="teacher", enabled=False, password_hash="uninitialized")
                    db.add(teacher)
                    teachers[key] = teacher
                    counts[name]["added"] += 1
                elif existing.role != "teacher":
                    errors.append(f"教师第 {row} 行工号与管理员账号冲突")
                else:
                    upsert(name, teachers, key, User, {"name": second})
            elif name == "学生":
                upsert(name, students, first, Student, {"code": first, "name": second})
            elif name == "课程":
                upsert(name, courses, first, Course, {"code": first, "name": second})
            elif name == "教学班":
                course = courses.get(rest[0])
                if course is None:
                    errors.append(f"教学班第 {row} 行课程不存在")
                else:
                    upsert(name, classes, first, ClassGroup, {"code": first, "name": second, "course_id": course.id})
            elif name == "任课":
                teacher, course = teachers.get(key[0]), courses.get(second)
                if not teacher or teacher.role != "teacher" or not course:
                    errors.append(f"任课第 {row} 行教师或课程不存在")
                elif (teacher.id, course.id) in assignments:
                    counts[name]["unchanged"] += 1
                else:
                    db.add(TeachingAssignment(teacher_id=teacher.id, course_id=course.id))
                    assignments.add((teacher.id, course.id))
                    counts[name]["added"] += 1
            elif first not in students or second not in classes:
                errors.append(f"名单第 {row} 行学生或班级不存在")
            elif key in enrollments:
                counts[name]["unchanged"] += 1
            else:
                db.add(Enrollment(student_code=first, class_code=second))
                enrollments.add(key)
                counts[name]["added"] += 1
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "导入期间数据发生变化，请重新预检") from None

    if apply and not errors:
        db.commit()
    else:
        db.rollback()
    return {"rows": counts, "errors": errors[:100], "applied": apply and not errors}


class TeacherAccount(BaseModel):
    enabled: bool
    password: str | None = Field(default=None, min_length=10, max_length=128)


@router.put("/teachers/{teacher_id}/account")
def teacher_account(teacher_id: int, data: TeacherAccount, db: DB, user: Administrator):
    teacher = db.get(User, teacher_id)
    if not teacher or teacher.role != "teacher":
        raise HTTPException(404, "教师不存在")
    if data.enabled and not data.password and teacher.password_hash == "uninitialized":
        raise HTTPException(422, "开通账号前请设置密码")
    if data.password:
        teacher.password_hash = passwords.hash(data.password)
    teacher.enabled = data.enabled
    if data.password or not data.enabled:
        db.execute(delete(LoginSession).where(LoginSession.user_id == teacher.id))
    db.commit()
    return {"enabled": teacher.enabled}
