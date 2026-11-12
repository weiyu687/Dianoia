import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

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
