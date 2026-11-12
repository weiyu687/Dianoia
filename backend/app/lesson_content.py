import re

CELL_SPLIT = re.compile(r"(?<!\\)\|")
DIVIDER = re.compile(r":?-{3,}:?")


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
