import hashlib
import json
import re
from dataclasses import dataclass
from itertools import groupby
from typing import Literal

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from fastapi import HTTPException
from pydantic import BaseModel, Field

from .exam_word import (
    PREFIX, SECTION, SECTION_NUMBERS, TYPES, exam_heading, exam_info, exam_layout,
    exam_section, heading_table, ranges,
)

CHOICE = {"single", "multiple"}
OBJECTIVE = CHOICE | {"judge"}
OPTION_LABELS = "ABCDEFGH"


class AnswerArea(BaseModel):
    style: Literal["ruled", "boxed", "blank"] = "ruled"
    lines: int = Field(4, ge=1, le=20)
    line_mm: int = Field(8, ge=6, le=15)
    width_mm: int = Field(146, ge=30, le=146)
    option_count: int | None = Field(None, ge=2, le=8)
    blanks: int = Field(1, ge=1, le=10)
    blank_mm: int = Field(34, ge=12, le=115)


class SheetBuild(BaseModel):
    revision: int = Field(ge=1)
    areas: dict[str, AnswerArea] = Field(max_length=200)
    replace_edits: bool = False


@dataclass
class PrintQuestion:
    id: str
    number: str
    group: int
    kind: str
    points: int | None
    stem: str
    options: list[str]
    confirmed: bool
    placeholder: bool
    rich: bool
    answer: str
    explanation: str
    tags: list[str]

    @property
    def label(self):
        return f"{self.number}."


def print_questions(document, metadata):
    targets = ranges(document)
    by_start = {target.paragraphs[0]._p: target for target in targets.values()}
    questions = []
    section = group = count = 0
    previous = None
    for paragraph in document.element.body.iter(qn("w:p")):
        if paragraph.getparent().tag == qn("w:body") and SECTION.match("".join(paragraph.xpath(".//w:t/text()"))):
            section += 1
        target = by_start.get(paragraph)
        if target is None:
            continue
        values = metadata.get(target.name, {})
        kind = values.get("kind", "written")
        if (section, kind) != previous:
            previous = section, kind
            group += 1
            count = 0
        count += 1
        match = PREFIX.match(target.text)
        stem, options = target.parts
        questions.append(PrintQuestion(
            target.name, re.search(r"\d+", match[0])[0] if match else str(count), group, kind,
            values.get("points"), stem, options, values.get("confirmed", False),
            (values.get("placeholder", False) or not stem) and target.replaceable,
            not target.replaceable,
            values.get("answer", ""), values.get("explanation", ""), values.get("tags", []),
        ))
    return questions


def require_questions(questions, *, tex=False):
    if not questions or any(not q.confirmed or q.placeholder for q in questions):
        raise HTTPException(422, "请先在试卷正文标记并确认题目，补齐空题位")
    if len(questions) > 200:
        raise HTTPException(422, "打印版最多支持 200 道题")
    if tex and any(q.rich for q in questions):
        raise HTTPException(422, "题目含复杂 Word 对象或部分选区，请使用 Word/PDF 导出该试卷")
    if tex and any(q.kind in CHOICE and len(q.options) < 2 for q in questions):
        raise HTTPException(422, "LaTeX 组卷需要每个选择项独立成行，例如 A. 和 B.，也可继续使用 Word/PDF 导出")


def question_signature(questions, fields):
    values = [(q.id, q.number, q.kind, q.group, q.points, q.stem, q.options, q.confirmed, q.placeholder, q.tags) for q in questions]
    content = json.dumps([fields, values], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def default_area(question):
    if question.kind == "blank":
        blanks = len(re.findall(r"_{2,}|＿{2,}", question.stem)) or 1
        return AnswerArea(blanks=min(blanks, 10))
    if any(any(word in tag for word in ("编程", "作图", "绘图")) for tag in question.tags):
        return AnswerArea(style="boxed", lines=6)
    return AnswerArea(option_count=len(question.options) if question.kind in CHOICE and len(question.options) >= 2 else None)


def prepare_areas(questions, areas):
    require_questions(questions)
    if set(areas) != {q.id for q in questions}:
        raise HTTPException(409, "答题卡设置与当前题目不匹配，请重新打开作答区设置")
    for q in questions:
        area = areas[q.id]
        if q.kind in CHOICE:
            if len(q.options) >= 2:
                area.option_count = len(q.options)
            if area.option_count is None:
                raise HTTPException(422, f"请填写第{q.group}大题第{q.number}小题的选项数量")


def sheet_groups(questions):
    for group, entries in groupby(questions, key=lambda q: q.group):
        items = list(entries)
        number = SECTION_NUMBERS[group - 1] if group <= len(SECTION_NUMBERS) else str(group)
        points = sum(q.points or 0 for q in items)
        label = f"{number}、{TYPES[items[0].kind]}（共{len(items)}题"
        if all(q.points for q in items):
            label += f"，共{points}分"
        yield f"{label}）", items


def selection_labels(question, area):
    return list("√×") if question.kind == "judge" else list(OPTION_LABELS[:area.option_count])


def answer_tab(paragraph, end_mm, underline=True):
    leader = WD_TAB_LEADER.LINES if underline else WD_TAB_LEADER.SPACES
    paragraph.paragraph_format.tab_stops.add_tab_stop(Mm(end_mm), leader=leader)
    paragraph.add_run("\t")


def blank_rows(area):
    return min(5, max(1, 144 // (area.blank_mm + 16)))


def avoid_split(row):
    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def answer_sheet(fields, questions, areas):
    document = exam_layout()
    exam_heading(document, f"{fields['school']}期末考试答题卡", 19)
    exam_heading(document, fields["title"], 12)
    exam_info(document, fields["course"], fields["teacher"], fields["term"], fields["class_name"])
    instruction = document.add_paragraph("作答须知：请按题号在对应区域内作答，选择题和判断题请在相应选项上作标记。")
    instruction.paragraph_format.space_before = Pt(8)
    for label, items in sheet_groups(questions):
        exam_section(document, label)
        for q in items:
            area = areas[q.id]
            if q.kind in OBJECTIVE:
                labels = selection_labels(q, area)
                table = heading_table(document, [(q.label, *(f"［{label}］" for label in labels))],
                                      (20, *([144 / len(labels)] * len(labels))), grid=False, height=7)
                avoid_split(table.rows[0])
            elif q.kind == "blank":
                per_row = blank_rows(area)
                for start in range(0, area.blanks, per_row):
                    paragraph = document.add_paragraph()
                    if start == 0:
                        paragraph.add_run(q.label)
                    answer_tab(paragraph, 12, False)
                    end = 12
                    for index in range(start, min(area.blanks, start + per_row)):
                        if area.blanks > 1:
                            paragraph.add_run(f"({index + 1}) ")
                        end += area.blank_mm + (12 if area.blanks > 1 else 0)
                        answer_tab(paragraph, end, area.style != "blank")
            else:
                title = document.add_paragraph(q.label)
                title.paragraph_format.keep_with_next = True
                if area.style == "ruled":
                    for _ in range(area.lines):
                        paragraph = document.add_paragraph()
                        paragraph.paragraph_format.space_after = Pt(0)
                        paragraph.paragraph_format.line_spacing = Mm(area.line_mm)
                        answer_tab(paragraph, area.width_mm)
                else:
                    # Use multiple short rows only when a single writing area would exceed a printable page.
                    block = min(20, 216 // area.line_mm)
                    for start in range(0, area.lines, block):
                        height = min(block, area.lines - start) * area.line_mm
                        table = heading_table(document, [("",)], (area.width_mm,), height=height, grid=area.style == "boxed")
                        table.alignment = WD_ALIGN_PARAGRAPH.LEFT
                        avoid_split(table.rows[0])
    document.add_paragraph()
    return document
