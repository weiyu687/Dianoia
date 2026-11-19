"""Bounded JSON rich text shared by authoring, imports and model output."""

import json
import re
from urllib.parse import urlsplit

from ..exam_math import has_supported_formula
from ..lesson_content import lesson_blocks

MATH = re.compile(r"\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<![\\$])\$([^\n$]+?)(?<!\\)\$(?!\$)")
BLOCKS = {"paragraph", "heading", "blockquote", "bulletList", "orderedList", "listItem", "codeBlock", "table", "image", "horizontalRule"}
INLINE = {"text", "hardBreak", "formula"}


def empty_doc():
    return {"type": "doc", "content": [{"type": "paragraph"}]}


def plain(doc):
    if not isinstance(doc, dict):
        return ""
    if doc.get("type") == "text":
        return doc.get("text", "")
    if doc.get("type") == "formula":
        return doc.get("attrs", {}).get("latex", "")
    if doc.get("type") == "image":
        return "[图片]"
    children = [plain(node) for node in doc.get("content", [])]
    return ("" if doc.get("type") in {"paragraph", "heading", "tableCell", "tableHeader"} else "\n").join(children)


def asset_ids(doc):
    result = set()
    if doc.get("type") == "image":
        result.add(doc["attrs"]["assetId"])
    for node in doc.get("content", []):
        result.update(asset_ids(node))
    return result


def validate_doc(value):
    if not isinstance(value, dict) or value.get("type") != "doc":
        raise ValueError("请使用题目富文本编辑器录入内容")
    if len(json.dumps(value, ensure_ascii=False)) > 100000:
        raise ValueError("单个编辑区域内容过长")
    budget = [0]

    def walk(node, parent=None, depth=0):
        budget[0] += 1
        if depth > 16 or budget[0] > 4000 or not isinstance(node, dict):
            raise ValueError("正文结构过于复杂")
        kind = node.get("type")
        if set(node) - {"type", "text", "attrs", "content", "marks"}:
            raise ValueError("正文含未支持的字段")
        children = node.get("content", [])
        if not isinstance(children, list):
            raise ValueError("正文结构有误")
        allowed = {
            None: {"doc"}, "doc": BLOCKS, "paragraph": INLINE, "heading": INLINE,
            "blockquote": BLOCKS, "bulletList": {"listItem"}, "orderedList": {"listItem"},
            "listItem": BLOCKS, "codeBlock": {"text"}, "table": {"tableRow"},
            "tableRow": {"tableCell", "tableHeader"}, "tableCell": BLOCKS, "tableHeader": BLOCKS,
        }.get(parent, set())
        if kind not in allowed:
            raise ValueError("正文含未支持的内容类型或嵌套关系")
        attrs = node.get("attrs", {}) or {}
        if not isinstance(attrs, dict):
            raise ValueError("正文属性有误")
        permitted = {
            "heading": {"level"}, "orderedList": {"start", "type"}, "codeBlock": {"language"},
            "image": {"assetId", "alt", "title"}, "formula": {"latex", "display"},
            "tableCell": {"colspan", "rowspan", "colwidth", "align"},
            "tableHeader": {"colspan", "rowspan", "colwidth", "align"},
        }.get(kind, set())
        if set(attrs) - permitted:
            raise ValueError("正文含未支持的样式属性")
        if kind == "heading" and attrs.get("level", 2) not in {1, 2, 3, 4}:
            raise ValueError("标题层级不受支持")
        if kind == "orderedList" and (not isinstance(attrs.get("start", 1), int) or not 1 <= attrs.get("start", 1) <= 10000):
            raise ValueError("列表编号有误")
        if kind == "formula":
            latex = attrs.get("latex", "")
            if not isinstance(latex, str) or not 1 <= len(latex) <= 1600 or not has_supported_formula(r"\(" + latex + r"\)"):
                raise ValueError("公式语法有误或暂不支持，请在公式面板检查")
            if not isinstance(attrs.get("display", False), bool):
                raise ValueError("公式排版方式有误")
        if kind == "image" and not re.fullmatch(r"[a-f0-9]{32}", str(attrs.get("assetId", ""))):
            raise ValueError("图片必须先上传到当前题库")
        if kind in {"tableCell", "tableHeader"}:
            for key, limit in (("colspan", 20), ("rowspan", 50)):
                if type(attrs.get(key, 1)) is not int or not 1 <= attrs.get(key, 1) <= limit:
                    raise ValueError("表格合并范围有误")
            widths = attrs.get("colwidth")
            if widths is not None and (not isinstance(widths, list) or len(widths) > 20 or any(type(w) is not int or not 0 <= w <= 3000 for w in widths)):
                raise ValueError("表格列宽有误")
            if attrs.get("align") not in {None, "left", "right", "center"}:
                raise ValueError("表格对齐方式有误")
        if kind == "text" and (not isinstance(node.get("text"), str) or not node["text"] or len(node["text"]) > 30000):
            raise ValueError("文字内容有误或过长")
        if kind in INLINE | {"image", "horizontalRule"} and children:
            raise ValueError("正文叶节点不能包含子节点")
        if kind not in {"text"} and "text" in node:
            raise ValueError("文字节点类型不匹配")
        marks = node.get("marks", [])
        if not isinstance(marks, list) or len(marks) > 8:
            raise ValueError("文字样式有误")
        for mark in marks:
            if not isinstance(mark, dict) or set(mark) - {"type", "attrs"} or mark.get("type") not in {"bold", "italic", "strike", "underline", "code", "link"}:
                raise ValueError("文字样式不受支持")
            if mark["type"] == "link":
                url = mark.get("attrs", {}).get("href", "")
                if not isinstance(url, str) or len(url) > 2000 or re.search(r"[\x00-\x20]", url) or urlsplit(url).scheme not in {"https", "http"} or not urlsplit(url).netloc:
                    raise ValueError("链接必须为 HTTP 或 HTTPS 地址")
                mark["attrs"] = {"href": url, "target": "_blank", "rel": "noopener noreferrer nofollow"}
            elif mark.get("attrs"):
                raise ValueError("文字样式属性不受支持")
        if kind == "table" and not 1 <= len(children) <= 50:
            raise ValueError("表格最多 50 行")
        if kind == "tableRow" and not 1 <= len(children) <= 20:
            raise ValueError("表格最多 20 列")
        for child in children:
            walk(child, kind, depth + 1)

    walk(value)
    return value


def inline(text):
    nodes, offset = [], 0
    for match in MATH.finditer(text):
        if match.start() > offset:
            nodes.append({"type": "text", "text": text[offset:match.start()]})
        index = next(i for i, part in enumerate(match.groups()) if part is not None)
        nodes.append({"type": "formula", "attrs": {"latex": match.group(index + 1), "display": index < 2}})
        offset = match.end()
    if offset < len(text):
        nodes.append({"type": "text", "text": text[offset:]})
    return nodes


def text_doc(text):
    nodes = []
    # Keep code literal; process prose/table formula delimiters without interpreting HTML.
    for part in re.split(r"(```[\s\S]*?```)", str(text)):
        if part.startswith("```") and part.endswith("```"):
            language, _, body = part[3:-3].partition("\n")
            nodes.append({"type": "codeBlock", "attrs": {"language": language[:40]},
                          "content": [{"type": "text", "text": body or " "}]})
            continue
        formulas = []

        def protect(match):
            index = next(i for i, value in enumerate(match.groups()) if value is not None)
            formulas.append({"type": "formula", "attrs": {"latex": match.group(index + 1), "display": index < 2}})
            return "\ufff0MATH" + str(len(formulas) - 1) + "\ufff1"

        def restore(value):
            result, offset = [], 0
            for match in re.finditer("\ufff0MATH([0-9]+)\ufff1", value):
                if match.start() > offset:
                    result.append({"type": "text", "text": value[offset:match.start()]})
                number = int(match[1])
                result.append(formulas[number] if number < len(formulas) else {"type": "text", "text": match[0]})
                offset = match.end()
            if offset < len(value):
                result.append({"type": "text", "text": value[offset:]})
            return result

        # Protect whole equations before splitting Markdown lines/cells. This preserves
        # multi-line matrices/cases and literal pipes inside a table-cell equation.
        protected = MATH.sub(protect, part)
        if re.search(r"\\[()[\]]", protected):
            raise ValueError("数学公式的定界符不完整，请使用公式编辑器检查")
        for block in lesson_blocks(protected):
            if block["type"] == "paragraph":
                if block["text"].strip():
                    nodes.append({"type": "paragraph", "content": restore(block["text"])})
            else:
                rows = [block["header"], *block["rows"]]
                nodes.append({"type": "table", "content": [
                    {"type": "tableRow", "content": [{"type": "tableHeader" if index == 0 else "tableCell",
                     "content": [{"type": "paragraph", "content": restore(cell)}]} for cell in row]}
                    for index, row in enumerate(rows)]})
    return validate_doc({"type": "doc", "content": nodes or [{"type": "paragraph"}]})
