import re
from base64 import b64encode
from io import BytesIO
from typing import Literal

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from pydantic import BaseModel, Field

CELL_SPLIT = re.compile(r"(?<!\\)\|")
DIVIDER = re.compile(r":?-{3,}:?")
HAN = re.compile(r"[\u3400-\u9fff]")


def continuation_delta(text, before, after):
    """Remove substantial verbatim overlap at the cursor while keeping the new text."""
    def overlap(left, right):
        for length in range(min(len(left), len(right)), 3, -1):
            candidate = right[:length]
            if left.endswith(candidate) and (len(HAN.findall(candidate)) >= 4 or sum(
                char.isalnum() for char in candidate
            ) >= 8):
                return length
        return 0

    text = text[overlap(before.rstrip(), text):]
    ending = overlap(text.rstrip(), after.lstrip())
    return text.rstrip()[:-ending] if ending else text


def cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith(r"\|"):
        line = line[:-1]
    return [part.strip().replace(r"\|", "|") for part in CELL_SPLIT.split(line)]


def lesson_blocks(text):
    """Read paragraphs and Markdown pipe tables without interpreting HTML."""
    lines = text.splitlines()
    blocks = []
    index = 0
    while index < len(lines):
        if index + 1 < len(lines) and "|" in lines[index] and "|" in lines[index + 1]:
            header, separator = cells(lines[index]), cells(lines[index + 1])
            if 1 <= len(header) <= 12 and len(header) == len(separator) and all(
                DIVIDER.fullmatch(cell) for cell in separator
            ):
                rows = []
                index += 2
                while index < len(lines) and "|" in lines[index] and len(rows) < 50:
                    row = cells(lines[index])
                    if len(row) != len(header):
                        break
                    rows.append(row)
                    index += 1
                blocks.append({"type": "table", "header": header, "rows": rows})
                continue
        blocks.append({"type": "paragraph", "text": lines[index]})
        index += 1
    return blocks


def add_lesson_table(document, block):
    rows = [block["header"], *block["rows"]]
    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement(f"w:{edge}")
        for key, value in (("val", "single"), ("sz", "6"), ("color", "808080")):
            border.set(qn(f"w:{key}"), value)
        borders.append(border)
    table._tbl.tblPr.insert_element_before(borders, "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook")
    for index, values in enumerate(rows):
        for cell, value in zip(table.rows[index].cells, values):
            cell.text = value
            if index == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True
    return table


class WritingFormat(BaseModel):
    font_family: str | None = Field(default=None, pattern=r"^[^\x00-\x1f\x7f]{1,64}$")
    font_size: float | None = Field(default=None, gt=0, le=1638)
    line_rule: Literal["multiple", "exact", "atLeast"] | None = None
    line_spacing: float | None = Field(default=None, gt=0, le=1584)
    space_before: float | None = Field(default=None, ge=0, le=1584)
    space_after: float | None = Field(default=None, ge=0, le=1584)
    bold: bool | None = None
    italic: bool | None = None


def writing_fragment(blocks, style):
    document = Document()

    def format_paragraph(paragraph):
        settings = paragraph.paragraph_format
        if style.line_spacing is not None:
            if style.line_rule == "multiple":
                settings.line_spacing = min(style.line_spacing, 40)
            else:
                settings.line_spacing = Pt(style.line_spacing)
                if style.line_rule == "atLeast":
                    settings.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
        if style.space_before is not None:
            settings.space_before = Pt(style.space_before)
        if style.space_after is not None:
            settings.space_after = Pt(style.space_after)
        for run in paragraph.runs:
            if style.font_family:
                run.font.name = style.font_family
                run._r.rPr.rFonts.set(qn("w:eastAsia"), style.font_family)
            if style.font_size is not None:
                run.font.size = Pt(style.font_size)
            if run.bold is not True:
                run.bold = style.bold
            run.italic = style.italic

    for block in blocks:
        if block["type"] == "paragraph":
            format_paragraph(document.add_paragraph(block["text"]))
        else:
            for row in add_lesson_table(document, block).rows:
                for cell in row.cells:
                    format_paragraph(cell.paragraphs[0])
    buffer = BytesIO()
    document.save(buffer)
    return b64encode(buffer.getvalue()).decode("ascii")
