import re
from copy import deepcopy
from dataclasses import dataclass
from itertools import groupby

from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from docx.text.paragraph import Paragraph
from fastapi import HTTPException

from .lessons import chinese_lesson_document, set_chinese_typeface
from .models import identifier

TYPES = {"single": "单项选择题", "multiple": "多项选择题", "judge": "判断题", "blank": "填空题", "written": "解答题"}
SECTION_NUMBERS = "一二三四五六七八九十"
PREFIX = re.compile(r"^\s*(?:\d{1,3}[.．、)）]|[（(]\d{1,3}[）)])\s*")
SCORE = re.compile(r"[（(]\s*(\d{1,3}|[XxＸ×_＿]+)\s*分\s*[）)]")
SECTION = re.compile(r"^\s*[一二三四五六七八九十]+[、．.]")
ANSWERS = re.compile(r"^\s*(?:(?:第?\s*\d+\s*[.、．）)]\s*)?(?:参考答案|正确答案|答案|参考解析|试题解析|评分标准|评分细则|答案与解析))(?:\s*[:：]|\s*$)")
OPTION = re.compile(r"^\s*([A-H])[.．、)）]\s*(.+)")
INLINE_ANSWER = re.compile(r"[（(【\[]\s*(?:参考|正确)?答案\s*[:：]")
BOOKMARK = re.compile(r"^dexam_[0-9a-f]{32}$")


def question_kind(text, fallback="written"):
    for key, tokens in (
        ("multiple", ("多选", "多项选择", "不定项")), ("single", ("选择", "单选")),
        ("judge", ("判断",)), ("blank", ("填空",)), ("written", ("解答", "简答", "编程", "论述", "计算", "案例")),
    ):
        if any(token in text for token in tokens):
            return key
    return fallback


def answer_marked(text):
    return any(ANSWERS.match(line) or INLINE_ANSWER.search(line) for line in text.splitlines())


def unsafe(paragraph):
    return any(child.tag not in {qn("w:pPr"), qn("w:r"), qn("w:bookmarkStart"), qn("w:bookmarkEnd")}
               for child in paragraph._p) or bool(paragraph._p.xpath(
        ".//w:drawing | .//w:pict | .//w:object | .//w:fldChar | .//w:instrText | "
        ".//w:hyperlink | .//w:sdt | .//w:ins | .//w:del | .//m:oMath | .//w:br[@w:type] | "
        "./w:pPr/w:sectPr"
    ))


@dataclass
class QuestionRange:
    name: str
    paragraphs: list
    complete: bool

    @property
    def text(self):
        return "\n".join(p.text for p in self.paragraphs).strip()

    @property
    def replaceable(self):
        return self.complete and not any(unsafe(p) for p in self.paragraphs) and not answer_marked(self.text)

    @property
    def parts(self):
        lines = self.text.splitlines()
        stem, options = [], []
        for i, line in enumerate(lines):
            match = OPTION.match(line)
            if match:
                if match[1] != chr(65 + len(options)):
                    return self.text, []
                options.append(match[2].strip())
            elif options:
                return self.text, []
            else:
                stem.append(SCORE.sub("", PREFIX.sub("", line)).strip() if i == 0 else line)
        return "\n".join(stem).strip(), options


def mark(paragraphs, name=None):
    name = name or "dexam_" + identifier()
    root = paragraphs[0]._p.getroottree()
    number = max((int(element.get(qn("w:id"))) for element in root.iter(qn("w:bookmarkStart"))
                  if (element.get(qn("w:id")) or "").isdigit()), default=0) + 1
    start, end = OxmlElement("w:bookmarkStart"), OxmlElement("w:bookmarkEnd")
    start.set(qn("w:id"), str(number))
    start.set(qn("w:name"), name)
    end.set(qn("w:id"), str(number))
    first, last = paragraphs[0]._p, paragraphs[-1]._p
    first.insert(int(first.pPr is not None), start)
    last.append(end)
    return name


def ranges(document):
    body = document.element.body
    result = {}
    for start in body.iter(qn("w:bookmarkStart")):
        name, number = start.get(qn("w:name"), ""), start.get(qn("w:id"))
        if not BOOKMARK.fullmatch(name):
            continue
        ends = [element for element in body.iter(qn("w:bookmarkEnd")) if element.get(qn("w:id")) == number]
        if name in result:
            result[name].complete = False
            continue
        first = start.getparent()
        if len(ends) != 1 or first.tag != qn("w:p") or ends[0].getparent().tag != qn("w:p"):
            continue
        end = ends[0]
        last = end.getparent()
        parent = first.getparent()
        if last.getparent() is not parent or parent.tag not in {qn("w:body"), qn("w:tc")}:
            continue
        a, b = parent.index(first), parent.index(last)
        elements = list(parent)[a:b + 1]
        if not elements or any(e.tag != qn("w:p") for e in elements):
            continue
        # A partial selection is navigable, but only full paragraphs are safe to replace.
        before = list(first)[:first.index(start)]
        after = list(last)[last.index(end) + 1:]
        outside = any(
            e.tag != qn("w:pPr") and (e.tag != qn("w:r") or any(child.tag != qn("w:rPr") for child in e))
            for e in before + after
        )
        other_marks = any(e is not start and e is not end
                          for p in elements for e in p if e.tag in {qn("w:bookmarkStart"), qn("w:bookmarkEnd")})
        result[name] = QuestionRange(name, [Paragraph(e, document._body) for e in elements], not outside and not other_marks)
    return result


def detect(document):
    result = {}
    if ranges(document):
        return result

    def scan(paragraphs, initial="written"):
        kind = initial
        current = []
        inside_section = False

        def record():
            while len(current) > 1 and not current[-1].text.strip() and not unsafe(current[-1]):
                current.pop()
            if current:
                text = "\n".join(p.text for p in current)
                score = SCORE.search(current[0].text)
                key = mark(current)
                result[key] = {"kind": "single" if kind == "written" and any(OPTION.match(p.text) for p in current[1:]) else kind,
                    "points": int(score[1]) if score and score[1].isdigit() else None,
                    "confirmed": False, "placeholder": not SCORE.sub("", PREFIX.sub("", text)).strip(),
                    "answer": "", "explanation": "", "tags": []}
            current.clear()

        for paragraph in paragraphs:
            text = paragraph.text.strip()
            if ANSWERS.match(text):
                record()
                return kind, True
            if SECTION.match(text):
                record()
                inside_section = True
                kind = question_kind(text)
                continue
            numbered = paragraph._p.xpath("./w:pPr/w:numPr/w:numId | ./w:pPr/w:pStyle")
            auto = paragraph._p.xpath("./w:pPr/w:numPr/w:numId") or (
                numbered and paragraph.style.name == "List Number")
            if PREFIX.match(text) or (text and auto and (inside_section or not OPTION.match(text))):
                record()
                current.append(paragraph)
            elif current:
                current.append(paragraph)
        record()
        return kind, False

    block = []
    kind = "written"
    for element in document.element.body:
        if element.tag == qn("w:p"):
            block.append(Paragraph(element, document._body))
        else:
            kind, ended = scan(block, kind)
            if ended:
                return result
            block.clear()
            if element.tag == qn("w:tbl"):
                for cell in element.xpath("./w:tr/w:tc"):
                    _, ended = scan([Paragraph(p, document._body) for p in cell.xpath("./w:p")], kind)
                    if ended:
                        return result
    scan(block, kind)
    return result


def ensure_body_paragraph(document):
    body = document.element.body
    last = next((element for element in reversed(body) if element.tag != qn("w:sectPr")), None)
    if last is not None and last.tag != qn("w:tbl"):
        return False
    document.add_paragraph()
    return True


def exam_field(paragraph, field):
    run = paragraph.add_run()
    element = OxmlElement("w:fldSimple")
    element.set(qn("w:instr"), field)
    run._r.addnext(element)


def heading_table(document, rows, widths, *, centered=False, grid=True, height=8):
    table = document.add_table(rows=len(rows), cols=len(widths))
    table.style = "Table Grid" if grid else "Normal Table"
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for column, width in zip(table.columns, widths):
        column.width = Mm(width)
    for row, values in zip(table.rows, rows):
        row.height = Mm(height)
        for cell, text, width in zip(row.cells, values, widths):
            cell.width = Mm(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            if centered:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.add_run(text)
    return table


def exam_info(document, course, teacher, term, class_name):
    table = heading_table(document, [
        ("课程名称", course, "姓　名", "________________"),
        ("学年学期", term or "________________", "学　号", "________________"),
        ("任课教师", teacher or "________________", "教学班", class_name or "________________"),
        ("考试方式", "□ 闭卷　□ 开卷", "卷　别", "□ A 卷　□ B 卷"),
    ], (25, 61, 23, 55), grid=False, height=8)
    for row in table.rows:
        for index in (0, 2):
            row.cells[index].paragraphs[0].runs[0].bold = True


def exam_section(document, label, *, scoring=False):
    heading = document.add_heading(label, level=1)
    heading.paragraph_format.space_before = Pt(13)
    heading.paragraph_format.space_after = Pt(6)
    heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    heading.runs[0].font.size = Pt(12)
    if scoring:
        table = heading_table(document, [("得分", ""), ("评分人", "")], (20, 24), centered=True, height=6)
        table.alignment = WD_TABLE_ALIGNMENT.RIGHT
        # Keep the title and both scoring rows with at least the first question.
        for row in table.rows:
            for cell in row.cells:
                cell.paragraphs[0].paragraph_format.keep_with_next = True


def exam_layout():
    document = chinese_lesson_document()
    section = document.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin = section.right_margin = Mm(23)
    section.top_margin, section.bottom_margin = Mm(21), Mm(18)
    document.styles["Normal"].font.size = Pt(11)
    document.styles["Normal"].paragraph_format.space_after = Pt(5)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("第 ")
    exam_field(footer, "PAGE")
    footer.add_run(" 页　共 ")
    exam_field(footer, "NUMPAGES")
    footer.add_run(" 页")
    return document


def exam_heading(document, text, size, *, color="000000"):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(9)
    run = paragraph.add_run(text)
    set_chinese_typeface(run._r.get_or_add_rPr(), "黑体")
    run.bold, run.font.size, run.font.color.rgb = True, Pt(size), RGBColor.from_string(color)


def default_paper(title, course_name, *, school="", teacher="", term="", class_name="", groups=()):
    document = exam_layout()
    exam_heading(document, f"{school}期末考试试卷", 19)
    if re.sub(r"\s+", "", title).casefold() != re.sub(r"\s+", "", course_name).casefold() and title != f"{school}期末考试试卷":
        exam_heading(document, title, 12)
    exam_info(document, course_name, teacher, term, class_name)
    labels = list(SECTION_NUMBERS[:len(groups) if groups else 5])
    total = str(sum(group.count * group.points for group in groups)) if groups else "______"
    details = document.add_paragraph()
    details.alignment = WD_ALIGN_PARAGRAPH.CENTER
    details.paragraph_format.space_before = Pt(8)
    details.add_run(f"考试时长  ______ 分钟　　　　卷面总分  {total} 分").bold = True
    column_count = len(labels) + 2
    heading_table(document, [
        ["题　号", *labels, "总　分"], ["得　分", *([""] * (column_count - 1))],
    ], (23, *([141 / (column_count - 1)] * (column_count - 1))), centered=True, height=7)
    document.add_paragraph("考生须知：请填写姓名、学号和教学班，按题号顺序作答。")
    if not groups:
        exam_section(document, "一、____________（共____题，共____分）", scoring=True)
        for index in range(1, 3):
            document.add_paragraph(f"{index}. （____分）")
        document.add_paragraph()
    return document


def answer_paper(title, course, teacher, questions, *, school="", term="", class_name=""):
    document = exam_layout()
    exam_heading(document, f"{school}考试参考答案", 23, color="9E2525")
    exam_heading(document, title, 15)
    heading_table(document, [
        (f"课程名称：{course}", f"学期：{term or '________________'}"),
        (f"任课教师：{teacher}", f"考试班级：{class_name or '________________'}"),
        (f"题目总分：{sum(question['points'] or 0 for question in questions)} 分", ""),
    ], (82, 82))
    document.add_paragraph()
    groups = {}
    for question in questions:
        kind = question["kind"]
        groups[kind] = groups.get(kind, 0) + (question["points"] or 0)
    if groups:
        heading_table(document, [("题型", "分值"), *((TYPES[kind], str(points)) for kind, points in groups.items())],
                      (82, 82), centered=True)
    for kind, entries in groupby(questions, key=lambda question: question["kind"]):
        group = list(entries)
        heading = document.add_heading(TYPES[kind], 1)
        heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
        objective = kind in {"single", "multiple", "judge"}
        if objective:
            for start in range(0, len(group), 8):
                batch = group[start:start + 8]
                numbers = []
                for index, question in enumerate(batch, start=start + 1):
                    match = PREFIX.match(question["text"])
                    numbers.append(re.search(r"\d+", match[0])[0] if match else str(index))
                answers = [question["answer"] or "待补充" for question in batch]
                heading_table(document, [("题号", *numbers), ("答案", *answers)],
                              (24, *([140 / len(batch)] * len(batch))), centered=True)
        for index, question in enumerate(group, start=1):
            if objective and not question["explanation"]:
                continue
            first = question["text"].splitlines()
            text = first[0] if first else "未填写题干"
            document.add_paragraph(text if PREFIX.match(text) else f"{index}. {text}")
            if not objective:
                paragraph = document.add_paragraph()
                paragraph.add_run("参考答案　").bold = True
                paragraph.add_run(question["answer"] or "待补充").font.color.rgb = RGBColor.from_string("204D86")
            if question["explanation"]:
                paragraph = document.add_paragraph()
                paragraph.add_run("解析与评分要点　").bold = True
                paragraph.add_run(question["explanation"])
    ensure_body_paragraph(document)
    return document


def add_questions(document, questions, *, use_template=False):
    anchor = None
    if use_template:
        slots = [p for p in document.paragraphs if p.text.strip() == "{{试卷正文}}" and not unsafe(p)]
        if len(slots) > 1:
            raise HTTPException(422, "请在模板正文中保留一个试卷正文插入位置")
        anchor = slots[0]._p if slots else None
        if anchor is None:
            raise HTTPException(422, "该 Word 没有试卷正文占位符。可从模板创建副本后标记题目，或使用默认版式组卷。")
    metadata = {}
    counts = {}
    groups = {}
    for question in questions:
        count, points = groups.get(question.kind, (0, 0))
        groups[question.kind] = count + 1, points + question.points
    for index, question in enumerate(questions):
        kind = question.kind
        if kind not in counts:
            if anchor is not None:
                heading = document.add_heading(TYPES[kind], level=1)
                heading.runs[0].font.color.rgb = RGBColor(0, 0, 0)
                anchor.addprevious(heading._p)
            else:
                count, points = groups[kind]
                exam_section(document, f"{SECTION_NUMBERS[len(counts)]}、{TYPES[kind]}（共{count}题，共{points}分）", scoring=True)
            counts[kind] = 0
        counts[kind] += 1
        paragraphs = [document.add_paragraph(f"{counts[kind]}. {question.stem}（{question.points}分）")]
        if anchor is None:
            paragraphs[0].paragraph_format.space_after = Pt(4)
        for i, option in enumerate(question.options):
            paragraph = document.add_paragraph(f"{chr(65 + i)}. {option}")
            if anchor is None:
                paragraph.paragraph_format.left_indent = Mm(5)
                paragraph.paragraph_format.space_after = Pt(2)
            paragraphs.append(paragraph)
        if question.options and anchor is None:
            paragraphs[0].paragraph_format.keep_with_next = True
        if anchor is not None:
            for p in paragraphs:
                anchor.addprevious(p._p)
        key = mark(paragraphs)
        metadata[key] = question.model_dump(exclude={"stem", "options"}) | {"confirmed": True}
        if kind == "written" and (anchor is not None or index + 1 < len(questions)):
            paragraph = document.add_paragraph()
            if anchor is not None:
                anchor.addprevious(paragraph._p)
    if anchor is not None:
        anchor.getparent().remove(anchor)
    return metadata


def replace_question(target, question, previous_points=None):
    if not target.replaceable:
        raise HTTPException(422, "这道题包含复杂对象、答案或未完整选中的段落，请先在 Word 中手动调整范围")
    first, *remaining = target.paragraphs
    prefix = PREFIX.match(first.text)
    old_score = SCORE.search(first.text)
    points = question.points if previous_points is None else previous_points
    score = old_score[0] if old_score and old_score[1].isdigit() and int(old_score[1]) == points else (
        f"（{points}分）" if points else ""
    )
    if prefix:
        head = prefix[0]
    else:
        head = ""
    texts = [f"{head}{question.stem}{score}", *[f"{chr(65 + i)}. {option}" for i, option in enumerate(question.options)]]
    properties = [deepcopy(p.runs[0]._r.rPr) if p.runs and p.runs[0]._r.rPr is not None else None
                  for p in target.paragraphs]
    end = target.paragraphs[-1]._p.find(qn("w:bookmarkEnd"))
    end.getparent().remove(end)
    last = first
    for i, text in enumerate(texts):
        original = target.paragraphs[min(i, len(target.paragraphs) - 1)]
        if i < len(target.paragraphs):
            paragraph = target.paragraphs[i]
            for run in paragraph.runs:
                run._r.getparent().remove(run._r)
        else:
            new = OxmlElement("w:p")
            last._p.addnext(new)
            paragraph = Paragraph(new, first._parent)
            if original._p.pPr is not None:
                new.append(deepcopy(original._p.pPr))
                if new.pPr.numPr is not None:
                    new.pPr.remove(new.pPr.numPr)
        run = paragraph.add_run(text)
        style = properties[min(i, len(properties) - 1)]
        if style is not None:
            run._r.insert(0, deepcopy(style))
        last = paragraph
    for paragraph in remaining[len(texts) - 1:]:
        paragraph._p.getparent().remove(paragraph._p)
    last._p.append(end)
