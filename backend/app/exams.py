import json
import os
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from docx import Document
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select, update
from sqlalchemy.orm import defer

from .ai import generate
from .auth import DB, Teacher, course_access
from .exam_math import convert_legacy_paragraphs, has_supported_formula, insertion_xml, persist_equations, tag_imported_equations
from .exam_sheet import AnswerArea, SheetBuild, answer_sheet, default_area, prepare_areas, print_questions, question_signature, require_questions
from .exam_tex import exam_tex, xelatex_pdf
from .exam_word import add_questions, answer_marked, answer_paper, default_paper, detect, ensure_body_paragraph, ranges, replace_question
from .lessons import Source, Title, lesson_sources, serialize_docx
from .models import ClassGroup, Course, Exam, ExamAnswerDocument, ExamAnswerSheet, ExamDocument, ExamTemplate, now
from .word import DOCX_MIME, convert_word, read_word_upload, word_pdf

router = APIRouter(prefix="/api", tags=["exams"])
Kind = Literal["single", "multiple", "judge", "blank", "written"]
Format = Literal["doc", "docx", "pdf", "tex", "latex-pdf"]
Variant = Literal["paper", "answers", "sheet"]


class Question(BaseModel):
    kind: Kind
    points: int = Field(ge=1, le=100)
    stem: str = Field(min_length=1, max_length=3000)
    options: list[str] = Field(default_factory=list, max_length=8)
    answer: str = Field(min_length=1, max_length=3000)
    explanation: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def valid_item(self):
        if not self.stem.strip() or not self.answer.strip() or answer_marked(self.stem):
            raise ValueError("题干及答案不能为空，题干应独立于答案")
        if any(len(option) > 800 or not option.strip() or answer_marked(option) for option in self.options):
            raise ValueError("选项应为独立的非空文字")
        if any(len(tag) > 40 for tag in self.tags):
            raise ValueError("题目标签过长")
        if any(not has_supported_formula(value) for value in (self.stem, *self.options, self.answer, self.explanation)):
            raise ValueError("题目或答案包含无法排版的公式")
        if self.kind in {"single", "multiple"}:
            keys = [value.strip().upper() for value in self.answer.replace("、", ",").replace("，", ",").split(",")]
            allowed = {chr(65 + index) for index in range(len(self.options))}
            if len(self.options) < 2 or len(set(option.strip() for option in self.options)) != len(self.options):
                raise ValueError("选择题至少需要两个不同的选项")
            if set(keys) - allowed or len(keys) != len(set(keys)) or (len(keys) == 1) != (self.kind == "single"):
                raise ValueError("选择题答案与选项不匹配")
            self.answer = "、".join(sorted(keys))
        elif self.options or (self.kind == "judge" and self.answer.strip() not in {"正确", "错误"}):
            raise ValueError("请核对题型、选项和答案")
        return self


class ExamCreate(BaseModel):
    course_id: int
    title: Title
    template_id: str | None = Field(default=None, max_length=32)
    sources: list[Source] = Field(default_factory=list, max_length=12)
    class_code: str | None = Field(default=None, max_length=64)


class Blueprint(BaseModel):
    kind: Kind
    count: int = Field(ge=1, le=20)
    points: int = Field(ge=1, le=100)


class ExamGenerate(ExamCreate):
    groups: list[Blueprint] = Field(min_length=1, max_length=5)
    difficulty: Literal["基础", "适中", "较难"] = "适中"
    instruction: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_groups(self):
        if sum(group.count for group in self.groups) > 30 or len({group.kind for group in self.groups}) != len(self.groups):
            raise ValueError("试卷最多 30 道题，每种题型请填写一次")
        return self


class QuestionUpdate(BaseModel):
    revision: int = Field(ge=1)
    kind: Kind
    points: int | None = Field(default=None, ge=1, le=100)
    confirmed: bool = True
    answer: str = Field(default="", max_length=3000)
    explanation: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_formulas(self):
        if not all(has_supported_formula(value) for value in (self.answer, self.explanation)):
            raise ValueError("请检查参考答案或评分要点中的公式")
        return self


class Revise(BaseModel):
    revision: int = Field(ge=1)
    mode: Literal["stem", "options", "difficulty", "replace"]
    instruction: str = Field(default="", max_length=2000)


class Adopt(BaseModel):
    revision: int = Field(ge=1)
    question: Question


class Review(BaseModel):
    revision: int = Field(ge=1)
    reviewed: Literal[True]


class Rename(BaseModel):
    title: Title


class ExamSources(BaseModel):
    revision: int = Field(ge=1)
    sources: list[Source] = Field(default_factory=list, max_length=12)


class FormulaInput(BaseModel):
    latex: str = Field(min_length=1, max_length=1600)


@router.post("/exams/equation")
def convert_equation(data: FormulaInput, user: Teacher):
    try:
        return {"omml": insertion_xml(data.latex.strip())}
    except (ValueError, SyntaxError, IndexError, KeyError, RecursionError) as error:
        raise HTTPException(422, "此公式无法转换为 Word，请检查公式语法或改用受支持的结构") from error


def decode(content):
    return Document(BytesIO(content))


def row_view(row, document=None):
    item = {field: getattr(row, field) for field in (
        "id", "title", "course_id", "revision", "imported", "reviewed", "updated_at",
    )}
    if document is None:
        return item
    questions = []
    for key, target in ranges(document).items():
        questions.append({
            "id": key, "kind": "written", "points": None, "confirmed": False, "placeholder": False,
            "answer": "", "explanation": "", "tags": [], **row.questions.get(key, {}),
            "text": target.text, "replaceable": target.replaceable,
        })
    return item | {"sources": row.sources, "questions": questions,
                   "total_points": sum(question["points"] or 0 for question in questions),
                   "answer_markers": has_answer_markers(document)}


def owned(db, user, exam_id):
    row = db.get(Exam, exam_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, "试卷不存在")
    course_access(db, user, row.course_id)
    return row


def owned_template(db, user, template_id):
    row = db.get(ExamTemplate, template_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, "试卷模板不存在")
    return row


def stored_document(db, row):
    return db.get(ExamDocument, row.id)


def has_answer_markers(document):
    return any(
        answer_marked("".join(t.text or "" for t in p.xpath(".//w:t")))
        for p in document.element.body.xpath(".//w:p")
    )


def normalize_paper_math(document):
    targets = ranges(document)
    changed = persist_equations(document)
    converted = convert_legacy_paragraphs(
        (paragraph for target in targets.values() if target.complete for paragraph in target.paragraphs),
    )
    return targets, changed or converted


def store(db, user, data, document, *, questions=None, imported=False, reviewed=False, answer=None, sheet=None):
    ensure_body_paragraph(document)
    row = Exam(owner_id=user.id, course_id=data.course_id, title=data.title, imported=imported,
               reviewed=reviewed, questions=questions or {}, sources=[source.model_dump() for source in data.sources])
    db.add(row)
    db.flush()
    db.add(ExamDocument(exam_id=row.id, content=serialize_docx(document)))
    if answer is not None:
        content, current = answer
        db.add(ExamAnswerDocument(exam_id=row.id, content=content, based_on_revision=1 if current else 0))
    if sheet is not None:
        db.add(ExamAnswerSheet(exam_id=row.id, content=sheet.content, layout=sheet.layout,
                               question_signature=sheet.question_signature, edited=sheet.edited))
    db.commit()
    return row_view(row, document)


def version(db, row, expected, **values):
    result = db.execute(update(Exam).where(Exam.id == row.id, Exam.revision == expected).values(
        **values, revision=Exam.revision + 1, updated_at=now(),
    ))
    if result.rowcount != 1:
        raise HTTPException(409, "试卷版本已更新，请重新打开后再试")


def assert_revision(row, expected):
    if row.revision != expected:
        raise HTTPException(409, "试卷版本已更新，请重新打开后再试")


def contextual_sources(db, user, row):
    return lesson_sources(db, user, row.course_id, [Source.model_validate(source) for source in row.sources],
                          skip_unavailable=True)


def parse_model(raw):
    raw = raw.strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw[7:-3].strip()
    return json.loads(raw)


def course_classes(db, course_id):
    return list(db.scalars(select(ClassGroup).where(ClassGroup.course_id == course_id).order_by(ClassGroup.name, ClassGroup.code)))


def school_fields():
    return {"school": os.getenv("DIANOIA_SCHOOL_NAME", "").strip()[:120],
            "term": os.getenv("DIANOIA_ACADEMIC_TERM", "").strip()[:80]}


def create_default_paper(db, user, data, groups=()):
    course = db.get(Course, data.course_id)
    classes = course_classes(db, course.id)
    class_name = next((row.name for row in classes if row.code == data.class_code), "")
    if data.class_code and not class_name:
        raise HTTPException(422, "请选择当前课程的教学班")
    if data.class_code is None and len(classes) == 1:
        class_name = classes[0].name
    return default_paper(data.title, course.name, teacher=user.name, class_name=class_name, groups=groups, **school_fields())


@router.get("/exams/course-fields")
def exam_course_fields(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    return [{"code": row.code, "name": row.name} for row in course_classes(db, course_id)]


@router.get("/exams")
def list_exams(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    return [row_view(row) for row in db.scalars(select(Exam).where(
        Exam.owner_id == user.id, Exam.course_id == course_id,
    ).order_by(Exam.updated_at.desc()))]


@router.post("/exams", status_code=201)
def create_exam(data: ExamCreate, db: DB, user: Teacher):
    course_access(db, user, data.course_id)
    lesson_sources(db, user, data.course_id, data.sources)
    if data.template_id:
        document = decode(owned_template(db, user, data.template_id).content)
        return store(db, user, data, document, questions=detect(document), imported=True)
    return store(db, user, data, create_default_paper(db, user, data), reviewed=True)


@router.post("/exams/import", status_code=201)
def import_exam(db: DB, user: Teacher, course_id: Annotated[int, Form()], file: Annotated[UploadFile, File()],
                title: Annotated[str | None, Form(max_length=160)] = None):
    course_access(db, user, course_id)
    filename, _, document = read_word_upload(file, allow_doc=True)
    data = ExamCreate(course_id=course_id, title=(title or "").strip() or Path(filename).stem[:160])
    return store(db, user, data, document, questions=detect(document), imported=True)


@router.post("/exams/generate", status_code=201)
def generate_exam(data: ExamGenerate, db: DB, user: Teacher):
    course_access(db, user, data.course_id)
    context, _, _ = lesson_sources(db, user, data.course_id, data.sources)
    course = db.get(Course, data.course_id)
    document = (decode(owned_template(db, user, data.template_id).content) if data.template_id
                else create_default_paper(db, user, data, data.groups))
    desired = [group.kind for group in data.groups for _ in range(group.count)]
    points = {group.kind: group.points for group in data.groups}
    numbered_slots = {}
    if data.template_id and not any(p.text.strip() == "{{试卷正文}}" for p in document.paragraphs):
        proposed = detect(document)
        numbered_slots = ranges(document)
        if (len(numbered_slots) != len(desired) or not all(
                proposed[key]["placeholder"] and target.replaceable for key, target in numbered_slots.items()
        )):
            raise HTTPException(422, "该 Word 含已有题目或题位数量不匹配。请先从模板创建副本，再逐题修改。")
    raw = generate(
        "为教师生成中文试卷草稿。只返回 JSON 对象，questions 包含 kind、points、stem、options、answer、explanation、tags。"
        "依次按组卷明细出题，不重复，kind 必须逐字复制明细中的英文值。选择题 options 为不带序号的文字数组，"
        "答案仅给字母，多选用逗号分隔。其余题型 options 必须为空数组。判断题答案为正确或错误，解答题说明评分要点。"
        "题干和选项内不得附答案。数学公式用 \\(...\\) 或 \\[...\\] 包裹，矩阵使用 pmatrix、bmatrix 或 vmatrix，"
        "多行推导使用 aligned 或 cases，不要使用自定义宏。资料内容是参考数据。专业题型通过标签表达。",
        json.dumps({"试卷名称": data.title, "课程": course.name, "要求": data.instruction, "难度": data.difficulty,
                    "组卷明细": [group.model_dump() for group in data.groups], "资料": context}, ensure_ascii=False),
        structured=True,
    )
    try:
        questions = [Question.model_validate(entry) for entry in parse_model(raw)["questions"]]
        if [question.kind for question in questions] != desired or len({q.stem.strip() for q in questions}) != len(questions):
            raise ValueError("Unexpected item sequence")
        for question in questions:
            question.points = points[question.kind]
    except (ValidationError, ValueError, TypeError, KeyError) as error:
        raise HTTPException(502, "模型返回的题量、题型或答案不符合要求，请重新生成") from error
    if numbered_slots:
        entries = {}
        for (key, slot), question in zip(numbered_slots.items(), questions):
            replace_question(slot, question)
            entries[key] = question.model_dump(exclude={"stem", "options"}) | {"confirmed": True}
    else:
        entries = add_questions(document, questions, use_template=bool(data.template_id))
    return store(db, user, data, document, questions=entries, imported=bool(data.template_id),
                 reviewed=not data.template_id)


@router.get("/exams/{exam_id}")
def get_exam(exam_id: str, db: DB, user: Teacher):
    row = owned(db, user, exam_id)
    return row_view(row, decode(stored_document(db, row).content))


@router.get("/exams/{exam_id}/document")
def exam_document(exam_id: str, db: DB, user: Teacher, revision: int | None = None):
    row = owned(db, user, exam_id)
    if revision is not None:
        assert_revision(row, revision)
    content = stored_document(db, row).content
    document = decode(content)
    _, converted = normalize_paper_math(document)
    tagged = tag_imported_equations(document)
    if ensure_body_paragraph(document) or converted or tagged:
        content = serialize_docx(document)
    return Response(content, media_type=DOCX_MIME)


@router.put("/exams/{exam_id}/document")
def save_document(exam_id: str, db: DB, user: Teacher, file: Annotated[UploadFile, File()],
                  title: Annotated[str, Form(max_length=160)], revision: Annotated[int, Form(ge=1)]):
    row = owned(db, user, exam_id)
    assert_revision(row, revision)
    if not title.strip():
        raise HTTPException(422, "请填写试卷名称")
    _, content, document = read_word_upload(file)
    targets, converted = normalize_paper_math(document)
    if ensure_body_paragraph(document) or converted:
        content = serialize_docx(document)
    stored = stored_document(db, row)
    questions = {key: value for key, value in row.questions.items() if key in targets}
    changed = stored.content != content
    version(db, row, revision, title=title.strip(), questions=questions, reviewed=row.reviewed and not changed)
    stored.content = content
    db.commit()
    return row_view(row, document)


@router.patch("/exams/{exam_id}")
def rename_exam(exam_id: str, data: Rename, db: DB, user: Teacher):
    row = owned(db, user, exam_id)
    version(db, row, row.revision, title=data.title)
    db.commit()
    return row_view(row)


@router.post("/exams/{exam_id}/copy", status_code=201)
def copy_exam(exam_id: str, db: DB, user: Teacher):
    row = owned(db, user, exam_id)
    data = ExamCreate(course_id=row.course_id, title=f"{row.title[:156]}（副本）", sources=row.sources)
    document = decode(stored_document(db, row).content)
    saved = db.get(ExamAnswerDocument, exam_id)
    answer = (saved.content, saved.based_on_revision == row.revision) if saved else None
    return store(db, user, data, document, questions=row.questions, imported=row.imported,
                 reviewed=row.reviewed, answer=answer, sheet=db.get(ExamAnswerSheet, exam_id))


@router.delete("/exams/{exam_id}", status_code=204)
def delete_exam(exam_id: str, db: DB, user: Teacher):
    db.delete(owned(db, user, exam_id))
    db.commit()


def target_question(db, user, exam_id, key, expected):
    row = owned(db, user, exam_id)
    assert_revision(row, expected)
    word = stored_document(db, row)
    document = decode(word.content)
    target = ranges(document).get(key)
    if target is None:
        raise HTTPException(404, "题目定位已失效，请重新选中正文并标记")
    return row, word, document, target


@router.put("/exams/{exam_id}/questions/{key}")
def save_question(exam_id: str, key: str, data: QuestionUpdate, db: DB, user: Teacher):
    row, _, document, target = target_question(db, user, exam_id, key, data.revision)
    entry = row.questions.get(key, {}) | data.model_dump(exclude={"revision"}) | {"placeholder": not target.parts[0].strip()}
    version(db, row, data.revision, questions=row.questions | {key: entry})
    db.commit()
    return row_view(row, document)


@router.post("/exams/{exam_id}/questions/{key}/revise")
def revise_question(exam_id: str, key: str, data: Revise, db: DB, user: Teacher):
    row, _, _, target = target_question(db, user, exam_id, key, data.revision)
    meta = row.questions.get(key, {})
    if not meta.get("confirmed") or not target.replaceable:
        raise HTTPException(422, "请先确认题型和题目范围，复杂内容可先在 Word 中手动整理")
    if data.mode == "options" and (meta["kind"] not in {"single", "multiple"} or not meta.get("answer")):
        raise HTTPException(422, "修改干扰项前请先保存选择题的正确答案")
    stem, options = target.parts
    if data.mode == "options" and (not stem or not options):
        raise HTTPException(422, "请先把每个选项整理成独立的 A.、B. 段落")
    context, refs, _ = contextual_sources(db, user, row)
    raw = generate(
        "只修改教师指定的这一题，输出 JSON 对象，字段 kind、points、stem、options、answer、explanation、tags。"
        "stem 不含题号、分值和答案。题型与分值沿用给定值。单选/多选答案为字母，多个用逗号。"
        "修改干扰项时保留题干和正确选项，核对解析。判断题答案为正确或错误。除选择题外 options 必须为空数组。"
        "数学公式用 \\(...\\) 或 \\[...\\] 包裹，矩阵使用 pmatrix、bmatrix 或 vmatrix，禁止自定义宏。资料仅供参考。",
        json.dumps({"当前题目": target.text, "题干": stem, "选项": options, "题目信息": meta, "修改方式": data.mode,
                    "要求": data.instruction, "资料": context}, ensure_ascii=False), structured=True,
    )
    try:
        candidate = Question.model_validate(parse_model(raw))
        if candidate.kind != meta["kind"]:
            raise ValueError("Unexpected item type")
        if data.mode == "options":
            keys = meta["answer"].upper().replace("、", ",").replace("，", ",").split(",")
            indices = [ord(key.strip()) - 65 for key in keys if len(key.strip()) == 1]
            if not indices or len(indices) != len(keys) or len(candidate.options) != len(options) or any(
                not 0 <= index < len(options) or options[index] != candidate.options[index].strip() for index in indices
            ) or set(candidate.answer.split("、")) != {key.strip() for key in keys}:
                raise ValueError("Correct options changed")
            candidate.stem = stem
        if meta.get("points"):
            candidate.points = meta["points"]
    except (ValidationError, ValueError, TypeError, KeyError) as error:
        raise HTTPException(502, "模型返回的题型或答案有误，请重试") from error
    return {"revision": data.revision, "question": candidate.model_dump(), "references": refs}


@router.post("/exams/{exam_id}/questions/{key}/adopt")
def adopt_question(exam_id: str, key: str, data: Adopt, db: DB, user: Teacher):
    row, word, document, target = target_question(db, user, exam_id, key, data.revision)
    meta = row.questions.get(key, {})
    if not meta.get("confirmed") or meta["kind"] != data.question.kind:
        raise HTTPException(422, "请确认题目，AI 修改须保留题型")
    replace_question(target, data.question, meta.get("points"))
    entry = data.question.model_dump(exclude={"stem", "options"}) | {"confirmed": True, "placeholder": False}
    entry["points"] = meta.get("points") or entry["points"]
    version(db, row, data.revision, questions=row.questions | {key: entry}, reviewed=False)
    word.content = serialize_docx(document)
    db.commit()
    return row_view(row, document)


@router.put("/exams/{exam_id}/review")
def review_exam(exam_id: str, data: Review, db: DB, user: Teacher):
    row = owned(db, user, exam_id)
    assert_revision(row, data.revision)
    document = decode(stored_document(db, row).content)
    if has_answer_markers(document):
        raise HTTPException(422, "正文仍有答案或评分说明标记，请移到教师答案后再确认")
    version(db, row, data.revision, reviewed=True)
    db.commit()
    return row_view(row, document)


@router.put("/exams/{exam_id}/sources")
def update_sources(exam_id: str, data: ExamSources, db: DB, user: Teacher):
    row = owned(db, user, exam_id)
    assert_revision(row, data.revision)
    lesson_sources(db, user, row.course_id, data.sources)
    version(db, row, data.revision, sources=[source.model_dump() for source in data.sources])
    db.commit()
    return row_view(row, decode(stored_document(db, row).content))


def print_fields(db, user, row, document):
    first_table = next(iter(document.tables), None)
    class_name = ""
    if first_table is not None:
        for line in first_table.rows:
            values = [cell.text.strip() for cell in line.cells]
            for index, value in enumerate(values):
                if value == "教学班" and index + 1 < len(values):
                    class_name = values[index + 1]
                elif value.startswith("考试班级："):
                    class_name = value.removeprefix("考试班级：").strip()
    return {"title": row.title, "course": db.get(Course, row.course_id).name, "teacher": user.name,
            "class_name": class_name if class_name.strip("_＿") else "", **school_fields()}


def generated_answers(db, user, row):
    document = decode(stored_document(db, row).content)
    questions = row_view(row, document)["questions"]
    return serialize_docx(answer_paper(questions=questions, **print_fields(db, user, row, document)))


@router.get("/exams/{exam_id}/answers")
def answer_state(exam_id: str, db: DB, user: Teacher):
    row = owned(db, user, exam_id)
    saved = db.get(ExamAnswerDocument, exam_id)
    return {"revision": row.revision, "saved": saved is not None,
            "stale": bool(saved and saved.based_on_revision != row.revision)}


@router.get("/exams/{exam_id}/answers/document")
def answer_document(exam_id: str, db: DB, user: Teacher, revision: int, regenerate: bool = False):
    row = owned(db, user, exam_id)
    assert_revision(row, revision)
    saved = db.get(ExamAnswerDocument, exam_id)
    content = saved.content if saved and not regenerate else generated_answers(db, user, row)
    if saved and not regenerate:
        document = decode(content)
        converted = convert_legacy_paragraphs(document.paragraphs)
        if tag_imported_equations(document) or converted:
            content = serialize_docx(document)
    return Response(content, media_type=DOCX_MIME)


@router.put("/exams/{exam_id}/answers/document")
def save_answer_document(exam_id: str, db: DB, user: Teacher, file: Annotated[UploadFile, File()],
                         revision: Annotated[int, Form(ge=1)]):
    row = owned(db, user, exam_id)
    assert_revision(row, revision)
    _, content, document = read_word_upload(file)
    normalized = persist_equations(document)
    if ensure_body_paragraph(document) or normalized:
        content = serialize_docx(document)
    version(db, row, revision)
    saved = db.get(ExamAnswerDocument, exam_id)
    if saved is None:
        saved = ExamAnswerDocument(exam_id=exam_id)
        db.add(saved)
    saved.content, saved.based_on_revision = content, revision + 1
    db.commit()
    return {"revision": row.revision, "saved": True, "stale": False}


def sheet_context(db, user, row):
    document = decode(stored_document(db, row).content)
    return print_fields(db, user, row, document), print_questions(document, row.questions)


def sheet_view(row, fields, questions, saved):
    stale = bool(saved and saved.question_signature != question_signature(questions, fields))
    return {"revision": row.revision, "saved": saved is not None, "stale": stale, "edited": bool(saved and saved.edited),
            "can_build": bool(questions) and len(questions) <= 200 and all(q.confirmed and not q.placeholder for q in questions),
            "questions": [{"id": q.id, "kind": q.kind, "group": q.group, "number": q.number,
                           "stem": q.stem[:140], "option_count": len(q.options),
                           "area": (saved.layout.get(q.id) if saved else None) or default_area(q).model_dump()}
                          for q in questions[:200]]}


@router.get("/exams/{exam_id}/sheet")
def sheet_state(exam_id: str, db: DB, user: Teacher):
    row = owned(db, user, exam_id)
    fields, questions = sheet_context(db, user, row)
    return sheet_view(row, fields, questions, db.get(ExamAnswerSheet, exam_id))


def update_sheet_revision(db, row, revision):
    version(db, row, revision)
    answers = db.get(ExamAnswerDocument, row.id)
    if answers and answers.based_on_revision == revision:
        answers.based_on_revision = revision + 1


@router.put("/exams/{exam_id}/sheet")
def build_sheet(exam_id: str, data: SheetBuild, db: DB, user: Teacher):
    row = owned(db, user, exam_id)
    assert_revision(row, data.revision)
    fields, questions = sheet_context(db, user, row)
    prepare_areas(questions, data.areas)
    saved = db.get(ExamAnswerSheet, exam_id)
    if saved and saved.edited and not data.replace_edits:
        raise HTTPException(409, "答题卡有手动修改，请确认后重新生成")
    content = serialize_docx(answer_sheet(fields, questions, data.areas))
    update_sheet_revision(db, row, data.revision)
    if saved is None:
        saved = ExamAnswerSheet(exam_id=exam_id)
        db.add(saved)
    saved.content = content
    saved.layout = {key: area.model_dump() for key, area in data.areas.items()}
    saved.question_signature = question_signature(questions, fields)
    saved.edited = False
    db.commit()
    return sheet_view(row, fields, questions, saved)


@router.get("/exams/{exam_id}/sheet/document")
def sheet_document(exam_id: str, db: DB, user: Teacher, revision: int):
    row = owned(db, user, exam_id)
    assert_revision(row, revision)
    saved = db.get(ExamAnswerSheet, exam_id)
    if saved is None:
        raise HTTPException(404, "请先生成答题卡")
    return Response(saved.content, media_type=DOCX_MIME)


@router.put("/exams/{exam_id}/sheet/document")
def save_sheet_document(exam_id: str, db: DB, user: Teacher, file: Annotated[UploadFile, File()],
                        revision: Annotated[int, Form(ge=1)]):
    row = owned(db, user, exam_id)
    assert_revision(row, revision)
    saved = db.get(ExamAnswerSheet, exam_id)
    if saved is None:
        raise HTTPException(404, "请先生成答题卡")
    _, content, document = read_word_upload(file)
    normalized = persist_equations(document)
    if ensure_body_paragraph(document) or normalized:
        content = serialize_docx(document)
    fields, questions = sheet_context(db, user, row)
    update_sheet_revision(db, row, revision)
    saved.content, saved.edited = content, True
    db.commit()
    return sheet_view(row, fields, questions, saved)


@router.get("/exams/{exam_id}/export/{variant}/{format}")
def export_exam(exam_id: str, variant: Variant, format: Format, db: DB, user: Teacher, inline: bool = False):
    row = owned(db, user, exam_id)
    content = stored_document(db, row).content
    inline = inline and format in {"pdf", "latex-pdf"}
    latex = format in {"tex", "latex-pdf"}
    sheet = db.get(ExamAnswerSheet, exam_id) if variant == "sheet" else None
    if variant == "paper":
        document = decode(content)
        if (latex or not inline) and (not row.reviewed or has_answer_markers(document)):
            raise HTTPException(422, "请先核对学生卷正文并确认已移出参考答案")
        if not latex and normalize_paper_math(document)[1]:
            content = serialize_docx(document)
    elif variant == "sheet":
        if sheet is None:
            raise HTTPException(404, "请先生成答题卡")
        content = sheet.content
    elif not latex:
        saved = db.get(ExamAnswerDocument, exam_id)
        content = saved.content if saved else generated_answers(db, user, row)
        if saved:
            document = decode(content)
            if convert_legacy_paragraphs(document.paragraphs):
                content = serialize_docx(document)
    media = {"docx": DOCX_MIME, "doc": "application/msword", "pdf": "application/pdf",
             "tex": "application/x-tex", "latex-pdf": "application/pdf"}[format]
    if latex:
        fields, questions = sheet_context(db, user, row)
        require_questions(questions, tex=variant == "paper")
        areas = None
        if sheet:
            if sheet.question_signature != question_signature(questions, fields):
                raise HTTPException(409, "试卷题目或卷头已更新，请先按当前试卷重新生成答题卡")
            areas = {key: AnswerArea.model_validate(value) for key, value in sheet.layout.items()}
            prepare_areas(questions, areas)
        content = exam_tex(fields, questions, variant, areas)
        if format == "latex-pdf":
            content = xelatex_pdf(content)
    elif format == "pdf":
        content = word_pdf(content)
    elif format == "doc":
        content = convert_word(content, "docx", "doc:MS Word 97")
    suffix = {"answers": "（参考答案）", "sheet": "（答题卡）"}.get(variant, "（待核对预览）" if not row.reviewed else "")
    extension = "pdf" if format == "latex-pdf" else format
    mode = " LaTeX" if format == "latex-pdf" else ""
    filename = quote(f"{row.title}{suffix}{mode}.{extension}", safe="")
    return Response(content, media_type=media,
                    headers={"Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{filename}"})


def template_view(row):
    return {key: getattr(row, key) for key in ("id", "title", "filename", "created_at")}


@router.get("/exam-templates")
def list_templates(db: DB, user: Teacher):
    return [template_view(row) for row in db.scalars(select(ExamTemplate).options(defer(ExamTemplate.content))
            .where(ExamTemplate.owner_id == user.id).order_by(ExamTemplate.created_at.desc()))]


@router.post("/exam-templates", status_code=201)
def upload_template(db: DB, user: Teacher, file: Annotated[UploadFile, File()],
                    title: Annotated[str | None, Form(max_length=160)] = None):
    filename, content, _ = read_word_upload(file, allow_doc=True)
    row = ExamTemplate(owner_id=user.id, title=(title or "").strip() or Path(filename).stem[:160],
                       filename=filename, content=content)
    db.add(row)
    db.commit()
    return template_view(row)


@router.patch("/exam-templates/{template_id}")
def rename_template(template_id: str, data: Rename, db: DB, user: Teacher):
    row = owned_template(db, user, template_id)
    row.title = data.title
    db.commit()
    return template_view(row)


@router.get("/exam-templates/{template_id}/preview")
def preview_template(template_id: str, db: DB, user: Teacher):
    return Response(word_pdf(owned_template(db, user, template_id).content), media_type="application/pdf")


@router.delete("/exam-templates/{template_id}", status_code=204)
def delete_template(template_id: str, db: DB, user: Teacher):
    db.delete(owned_template(db, user, template_id))
    db.commit()
