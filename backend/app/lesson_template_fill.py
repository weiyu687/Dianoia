import re
from dataclasses import dataclass

from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .lesson_content import add_lesson_table, lesson_blocks

PLACEHOLDER = re.compile(r"\{\{\s*([\w][\w ·-]{0,39}?)\s*\}\}")
HEADING_NUMBER = re.compile(r"^[一二三四五六七八九十\d]+[、.]")
INSTRUCTION = re.compile(r"^[（(](?:教学目标|重点难点|主要是指|主要指|教学内容是|是根据).+[）)]$", re.S)
CONTENT_LABELS = {
    "教学目标", "教学目的与要求", "教学重点", "教学难点", "教学重点与难点", "教学手段",
    "教学方法", "教学过程", "教学内容与设计", "教学内容与教学设计", "课后作业", "课后作业及思考题",
    "思政融入", "使用教材", "教学参考资料",
}
FIXED_LABELS = {"课程名称", "课程代码", "任课教师", "授课主题", "章节名称"}


@dataclass(frozen=True)
class TemplateTarget:
    field: str
    paragraph: Paragraph
    token: str
    block: bool = False


def editable_text(paragraph):
    if paragraph._p.xpath(".//w:drawing | .//w:pict | .//w:object | .//w:fldChar | .//w:hyperlink | .//w:sdt | .//w:br[@w:type]"):
        return None
    return "".join(node.text or "" for node in paragraph._p.xpath("./w:r/w:t"))


def template_targets(document):
    targets = []
    for element in document.element.body.xpath(".//w:p[not(ancestor::w:sdt)]"):
        paragraph = Paragraph(element, document._body)
        text = editable_text(paragraph)
        if text is None:
            continue
        for match in PLACEHOLDER.finditer(text):
            targets.append(TemplateTarget(match[1], paragraph, match[0], text.strip() == match[0]))

    occupied = {target.paragraph._p for target in targets}
    for paragraph in document.paragraphs:
        text = editable_text(paragraph)
        if text is None or paragraph._p in occupied:
            continue
        label = re.sub(r"\s+", "", text).rstrip("：:")
        if label in FIXED_LABELS and text.rstrip().endswith(("：", ":")):
            targets.append(TemplateTarget(label, paragraph, ""))
        elif label == "第*章章节名称（授课章节名称）":
            targets.append(TemplateTarget("章节名称", paragraph, text))
        else:
            label = HEADING_NUMBER.sub("", label)
            following = paragraph._p.getnext()
            if label not in CONTENT_LABELS or following is None or following.tag != qn("w:p") or following in occupied:
                continue
            next_paragraph = Paragraph(following, document._body)
            value = editable_text(next_paragraph)
            if value is not None and (not value.strip() or INSTRUCTION.fullmatch(value.strip())):
                targets.append(TemplateTarget(label, next_paragraph, value, True))

    occupied.update(target.paragraph._p for target in targets)
    for table in document.tables:
        for row in table.rows:
            unique_cells = {cell._tc: cell for cell in row.cells}
            cells = list(unique_cells.values())
            for left, right in zip(cells, cells[1:]):
                label = re.sub(r"\s+", "", left.text).rstrip("：:")
                if label not in FIXED_LABELS | CONTENT_LABELS or right.tables or len(right.paragraphs) != 1:
                    continue
                paragraph = right.paragraphs[0]
                value = editable_text(paragraph)
                if value is not None and not value.strip() and paragraph._p not in occupied:
                    targets.append(TemplateTarget(label, paragraph, value, label in CONTENT_LABELS))
                    occupied.add(paragraph._p)
    return targets


def fill_text(paragraph, token, value):
    nodes = paragraph._p.xpath("./w:r/w:t")
    if not token:
        run = paragraph.runs[-1] if paragraph.runs else paragraph.add_run()
        run.add_text(value)
        return
    text = "".join(node.text or "" for node in nodes)
    start = text.find(token)
    if start < 0:
        return
    end = start + len(token)
    offset = 0
    for node in nodes:
        current = node.text or ""
        next_offset = offset + len(current)
        if offset < end and next_offset > start:
            left = max(0, start - offset)
            right = min(len(current), end - offset)
            node.text = current[:left] + (value if offset <= start else "") + current[right:]
            node.set(qn("xml:space"), "preserve")
        offset = next_offset


def fill_template(document, targets, values):
    for target in targets:
        if target.field not in values:
            continue
        value = values[target.field]
        if not target.block:
            fill_text(target.paragraph, target.token, " ".join(value.splitlines()))
            continue
        blocks = lesson_blocks(value)
        first = blocks.pop(0) if blocks and blocks[0]["type"] == "paragraph" else None
        fill_text(target.paragraph, target.token, first["text"] if first else "")
        after = target.paragraph._p
        for block in blocks:
            if block["type"] == "table":
                node = add_lesson_table(document, block)._tbl
            else:
                node = document.add_paragraph(block["text"], style=target.paragraph.style)._p
            after.addnext(node)
            after = node
        if after.tag == qn("w:tbl") and after.getparent().tag == qn("w:tc") and after.getnext() is None:
            after.addnext(document.add_paragraph()._p)
