import subprocess
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from fastapi import HTTPException
from lxml.etree import XMLSyntaxError

from .documents import WORD_EXTENSIONS, WORD_PDF_FILTER, convert_with_office, validate_format

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_WORD_BYTES = 25 * 1024 * 1024


def convert_office_document(content, extension, format_spec, *, label="Word"):
    with TemporaryDirectory(prefix="dianoia-office-") as folder:
        directory = Path(folder)
        source = directory / f"document.{extension}"
        source.write_bytes(content)
        try:
            converted = convert_with_office(source, format_spec, directory)
        except FileNotFoundError as error:
            raise HTTPException(503, "请配置可用的 LibreOffice") from error
        except subprocess.TimeoutExpired as error:
            raise HTTPException(504, f"{label} 转换超时，请稍后重试") from error
        except subprocess.CalledProcessError as error:
            raise HTTPException(422, f"{label} 转换失败，请检查文件是否损坏") from error
        if converted is None:
            raise HTTPException(503, f"未生成转换文件，请检查 LibreOffice 配置和 {label} 文件")
        return converted.read_bytes()


convert_word = convert_office_document


def word_pdf(content):
    return convert_word(content, "docx", WORD_PDF_FILTER)


def read_word_upload(file, allow_doc=False):
    name = Path((file.filename or "").replace("\\", "/")).name
    extension = Path(name).suffix.lower().removeprefix(".")
    formats = WORD_EXTENSIONS if allow_doc else {"docx"}
    if extension not in formats or len(name) > 255:
        raise HTTPException(415, "请选择 DOC 或 DOCX 文件" if allow_doc else "请选择 DOCX 文件")
    content = file.file.read(MAX_WORD_BYTES + 1)
    if not content or len(content) > MAX_WORD_BYTES:
        raise HTTPException(422, "Word 文件不能为空或超过 25 MB")
    try:
        with TemporaryDirectory(prefix="dianoia-word-check-") as folder:
            source = Path(folder) / f"original.{extension}"
            source.write_bytes(content)
            validate_format(source, extension)
            if extension == "doc":
                content = convert_word(content, "doc", "docx")
                if len(content) > MAX_WORD_BYTES:
                    raise HTTPException(422, "转换后的 DOCX 超过 25 MB")
                docx = Path(folder) / "converted.docx"
                docx.write_bytes(content)
                validate_format(docx, "docx")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except BadZipFile as error:
        raise HTTPException(422, "无法读取 Word 文件，请检查文件格式") from error
    try:
        document = Document(BytesIO(content))
    except (BadZipFile, PackageNotFoundError, KeyError, ValueError, XMLSyntaxError) as error:
        raise HTTPException(422, "无法读取 Word 文件，请检查文件格式") from error
    return name, content, document
