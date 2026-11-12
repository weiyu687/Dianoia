import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from pypdf import PdfReader
from pptx import Presentation

from .db import DATA_DIR

FILES = DATA_DIR / "resources"
MAX_PAGES = 500
WORD_EXTENSIONS = {"doc", "docx"}
EXTENSIONS = WORD_EXTENSIONS | {"pptx", "pdf"}
WORD_PDF_FILTER = 'pdf:writer_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"true"}}'
CHAPTER = re.compile(r"^(?:第[一二三四五六七八九十百零〇0-9]+[章节篇单元]|\d+(?:\.\d+)+\s+).{1,80}$")
NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)+)\s+")


class OfficeUnavailable(RuntimeError):
    pass


def office_executable():
    if configured := os.getenv("DIANOIA_SOFFICE"):
        return configured
    if executable := shutil.which("soffice"):
        return executable
    if os.name == "nt":
        locations = [DATA_DIR / "tools" / "LibreOffice"]
        locations.extend(Path(os.environ[key]) / "LibreOffice" for key in ("ProgramFiles", "ProgramFiles(x86)") if key in os.environ)
        for root in locations:
            for name in ("soffice.com", "soffice.exe"):
                executable = root / "program" / name
                if executable.is_file():
                    return str(executable)
    return None


def convert_with_office(source, format_spec, output_dir):
    office = office_executable()
    if not office:
        return None
    with TemporaryDirectory(prefix="dianoia-office-") as profile:
        subprocess.run(
            [office, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless",
             "--convert-to", format_spec, "--outdir", str(output_dir), str(source)],
            check=True, timeout=45, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    result = output_dir / f"{source.stem}.{format_spec.split(':', 1)[0]}"
    return result if result.exists() else None


def include_child_pages(nodes):
    for node in nodes:
        children = node["children"]
        include_child_pages(children)
        if children:
            node["end"] = max(node["end"], max(child["end"] for child in children))
    return nodes


def named_outline(nodes):
    result = []
    for node in nodes:
        children = named_outline(node["children"])
        if node["title"].strip():
            result.append({**node, "children": children})
        else:
            result.extend(children)
    return result


def candidate_outline(nodes, page_count):
    def visit(siblings, limit):
        for index, node in enumerate(siblings):
            following = siblings[index + 1]["start"] if index + 1 < len(siblings) else limit + 1
            node["end"] = max(node["start"], min(limit, following - 1))
            visit(node["children"], node["end"])
    visit(nodes, page_count)
    return include_child_pages(nodes)


def restore_saved_outline(nodes, page_count):
    named = named_outline(nodes)
    if named != nodes:
        return candidate_outline(named, page_count)
    return include_child_pages(named)


def numbered_outline(headings, page_count):
    root = []
    ancestors = []
    for title, start in headings:
        number = NUMBERED_HEADING.match(title)
        depth = min(number.group(1).count(".") + 1, 8) if number else 1
        ancestors = ancestors[:depth - 1]
        siblings = ancestors[-1]["children"] if ancestors else root
        node = {"title": title, "start": start, "children": []}
        siblings.append(node)
        ancestors.append(node)
    return candidate_outline(root, page_count)


def pdf_data(source):
    reader = PdfReader(source)
    if reader.is_encrypted:
        raise ValueError("请上传未加密的 PDF")
    page_count = len(reader.pages)
    if page_count > MAX_PAGES:
        raise ValueError(f"首期支持最多 {MAX_PAGES} 页的资料")
    pages = [(page.extract_text() or "").strip() for page in reader.pages]

    def read_bookmarks(items, depth=0):
        nodes = []
        if depth >= 8:
            return nodes
        previous = None
        for item in items:
            if isinstance(item, list):
                children = read_bookmarks(item, depth + 1)
                if previous is None:
                    nodes.extend(children)
                else:
                    previous["children"] = children
                continue
            page_index = reader.get_destination_page_number(item)
            previous = None
            if isinstance(page_index, int) and 0 <= page_index < page_count:
                previous = {"title": (item.title or "").strip()[:160], "start": page_index + 1, "children": []}
                nodes.append(previous)
        return nodes

    nodes = named_outline(read_bookmarks(reader.outline))
    if not nodes:
        headings = []
        for index, text in enumerate(pages, start=1):
            for line in text.splitlines()[:12]:
                if CHAPTER.match(line.strip()):
                    headings.append((line.strip(), index))
        return pages, numbered_outline(headings, page_count)
    return pages, candidate_outline(nodes, page_count)


def validate_format(source, extension):
    with source.open("rb") as file:
        header = file.read(8)
    if extension == "pdf" and not header.startswith(b"%PDF-"):
        raise ValueError("文件不是有效的 PDF")
    if extension == "doc" and header != bytes.fromhex("D0CF11E0A1B11AE1"):
        raise ValueError("文件不是受支持的旧版 Word 文档")
    if extension in {"docx", "pptx"}:
        expected = "word/document.xml" if extension == "docx" else "ppt/presentation.xml"
        with ZipFile(source) as archive:
            if expected not in archive.namelist():
                raise ValueError("文件内容与扩展名不符")
            members = archive.infolist()
            if len(members) > 5000 or sum(item.file_size for item in members) > 100 * 1024 * 1024:
                raise ValueError("文档解压后体积超出限制")
            if any("vbaproject" in name.lower() for name in archive.namelist()):
                raise ValueError("请移除文档宏后重新上传")


def slide_text(presentation):
    pages = []
    chapters = []
    for index, slide in enumerate(presentation.slides, start=1):
        title = slide.shapes.title
        if title and title.text.strip() and CHAPTER.match(title.text.strip()):
            chapters.append((title.text.strip()[:160], index))
        lines = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                lines.append(shape.text)
            if shape.has_table:
                lines.extend(" | ".join(cell.text for cell in row.cells) for row in shape.table.rows)
        pages.append("\n".join(lines).strip())
    return pages, numbered_outline(chapters, len(pages))


def inspect_resource(source, extension):
    validate_format(source, extension)
    if extension == "pdf":
        pages, outline = pdf_data(source)
        return pages, outline, True, len(pages)
    if extension in WORD_EXTENSIONS:
        if not office_executable():
            raise OfficeUnavailable("服务器未配置 LibreOffice，暂时无法转换 Word 资料")
        with TemporaryDirectory(prefix="word-pdf-", dir=source.parent) as folder:
            try:
                pdf = convert_with_office(source, WORD_PDF_FILTER, Path(folder))
            except FileNotFoundError as error:
                raise OfficeUnavailable("找不到配置的 LibreOffice 可执行文件") from error
            if not pdf:
                raise ValueError("Word 文件未能转换成 PDF，请检查文件是否加密或损坏")
            pages, outline = pdf_data(pdf)
            pdf.replace(source.parent / "preview.pdf")
        return pages, outline, True, len(pages)
    slides, slide_outline = slide_text(Presentation(source))
    pdf = convert_with_office(source, "pdf", source.parent)
    if pdf:
        pages, outline = pdf_data(pdf)
        if slides and len(slides) == len(pages):
            pages = [slide or page for slide, page in zip(slides, pages)]
        if pdf.name != "preview.pdf":
            pdf.replace(source.parent / "preview.pdf")
        return pages, outline or (slide_outline if len(pages) == len(slides) else []), True, len(pages)
    return slides, slide_outline, False, len(slides)
