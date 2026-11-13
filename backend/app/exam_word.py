import re
from copy import deepcopy
from dataclasses import dataclass

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from fastapi import HTTPException

from .lessons import chinese_lesson_document
from .models import identifier

TYPES = {"single": "单项选择题", "multiple": "多项选择题", "judge": "判断题", "blank": "填空题", "written": "解答题"}
PREFIX = re.compile(r"^\s*(?:\d{1,3}[.．、)）]|[（(]\d{1,3}[）)])\s*")
SCORE = re.compile(r"[（(]\s*(\d{1,3}|[XxＸ×]+)\s*分\s*[）)]")
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


def default_paper(title, course_name):
    document = chinese_lesson_document()
    document.add_heading(title, 0)
    document.add_paragraph(f"课程：{course_name}")
    document.add_paragraph("姓名：________________　学号：________________　班级：________________")
    document.add_paragraph("考试说明：请按题目要求作答。")
    table = document.add_table(rows=2, cols=3)
    table.style = "Table Grid"
    for cell, label in zip(table.rows[0].cells, ("总分", "实得分", "阅卷人")):
        cell.text = label
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
    for question in questions:
        kind = question.kind
        if kind not in counts:
            heading = document.add_heading(TYPES[kind], level=1)
            if anchor is not None:
                anchor.addprevious(heading._p)
            counts[kind] = 0
        counts[kind] += 1
        paragraphs = [document.add_paragraph(f"{counts[kind]}. {question.stem}（{question.points}分）")]
        for i, option in enumerate(question.options):
            paragraphs.append(document.add_paragraph(f"{chr(65 + i)}. {option}"))
        if anchor is not None:
            for p in paragraphs:
                anchor.addprevious(p._p)
        key = mark(paragraphs)
        metadata[key] = question.model_dump(exclude={"stem", "options"}) | {"confirmed": True}
        if kind == "written":
            paragraph = document.add_paragraph()
            if anchor is not None:
                anchor.addprevious(paragraph._p)
    if not use_template and document.tables:
        document.tables[0].cell(1, 0).text = str(sum(question.points for question in questions))
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
