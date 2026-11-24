import csv
import hashlib
import json
import math
import re
from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50000
MAX_COLUMNS = 100
ALLOWED_EXTENSIONS = {".csv", ".xls", ".xlsx"}


class TableParseError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_value(value):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value).strip() or None


def _read_csv(data: bytes) -> pd.DataFrame:
    last_error = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return pd.read_csv(BytesIO(data), dtype=object, encoding=encoding, keep_default_na=False,
                               on_bad_lines="error", nrows=MAX_ROWS + 1)
        except (UnicodeDecodeError, pd.errors.ParserError, csv.Error) as error:
            last_error = error
    raise TableParseError("CSV 无法读取，请另存为 UTF-8 或 GB18030 编码") from last_error


def inspect_table(data: bytes, filename: str, sheet_name: str | None = None):
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise TableParseError("仅支持 CSV、XLS 和 XLSX 文件")
    if len(data) > MAX_FILE_BYTES:
        raise TableParseError("单个文件不能超过 20 MB")
    if not data:
        raise TableParseError("文件内容为空")
    try:
        if suffix == ".csv":
            frame = _read_csv(data)
            sheets = []
            sheet = ""
        else:
            if suffix == ".xlsx" and not data.startswith(b"PK"):
                raise TableParseError("XLSX 文件格式无效")
            if suffix == ".xls" and not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
                raise TableParseError("XLS 文件格式无效")
            engine = "xlrd" if suffix == ".xls" else "openpyxl"
            book = pd.ExcelFile(BytesIO(data), engine=engine)
            sheets = list(book.sheet_names)
            if not sheets:
                raise TableParseError("工作簿没有工作表")
            sheet = sheet_name if sheet_name in sheets else sheets[0]
            frame = pd.read_excel(book, sheet_name=sheet, dtype=object, nrows=MAX_ROWS + 1)
    except TableParseError:
        raise
    except Exception as error:
        raise TableParseError("文件无法读取，请检查文件格式、密码保护或工作表内容") from error

    if frame.empty or len(frame.columns) == 0:
        raise TableParseError("所选工作表没有可分析的数据")
    if len(frame) > MAX_ROWS:
        raise TableParseError(f"单个工作表最多支持 {MAX_ROWS} 行数据，请拆分后上传")
    if len(frame.columns) > MAX_COLUMNS:
        raise TableParseError(f"单个工作表最多支持 {MAX_COLUMNS} 列数据")

    columns = []
    counts = {}
    for position, raw in enumerate(frame.columns, start=1):
        label = str(raw).strip() if raw is not None else ""
        if not label or label.casefold().startswith("unnamed:"):
            label = f"未命名列{position}"
        counts[label] = counts.get(label, 0) + 1
        columns.append(label if counts[label] == 1 else f"{label}（{counts[label]}）")
    frame.columns = columns
    rows = []
    for row_index, row in enumerate(frame.to_dict(orient="records"), start=2):
        normalized = {key: safe_value(value) for key, value in row.items()}
        if any(value is not None for value in normalized.values()):
            normalized["__source_row"] = row_index
            rows.append(normalized)
    return {"sheet_names": sheets, "sheet_name": sheet, "columns": columns, "rows": rows,
            "sample_rows": rows[:12], "row_count": len(rows), "sha256": digest(data)}


def write_parsed(path: Path, parsed):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(parsed["rows"], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def read_parsed(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def metric_key(label: str):
    normalized = re.sub(r"\s+", "", label).casefold()
    return "m_" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
