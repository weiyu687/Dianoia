import re

from ..exam_word import detect, ranges
from ..exam_math import tag_imported_equations
from ..exams import normalize_paper_math
from .generation import GeneratedQuestion, business_question
from .schemas import Answer, Option, Question


def literal(text):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": str(text or " ")[:8000]}]}]}


def candidates(document, entries=None):
    normalize_paper_math(document)
    tag_imported_equations(document)
    entries = entries if entries is not None else detect(document)
    warnings, result = [], []
    drawings = len(document.element.body.xpath(".//w:drawing | .//w:pict | .//w:object"))
    if drawings:
        warnings.append(f"原文包含 {drawings} 个图片或绘图对象，当前提取文本与可识别公式；请在题目编辑器核对并补入插图。")
    for key, target in ranges(document).items():
        meta = entries.get(key, {})
        if not meta:
            continue
        stem, options = target.parts
        answer, explanation = meta.get("answer", ""), meta.get("explanation", "")
        lines, kept = stem.splitlines(), []
        for line in lines:
            match = re.match(r"\s*(?:参考|正确)?答案\s*[:：]\s*(.*)", line)
            analysis = re.match(r"\s*(?:参考)?解析\s*[:：]\s*(.*)", line)
            if match:
                answer = match[1]
            elif analysis:
                explanation = analysis[1]
            else:
                kept.append(line)
        kind = meta.get("kind", "written")
        notes = []
        if kind in {"single", "multiple"} and not options:
            notes.append("未可靠识别选项，请拆分后填写")
        if not target.replaceable:
            notes.append("原题包含复杂版式或对象，请对照原文核对")
        try:
            data = business_question(GeneratedQuestion(kind=kind, stem="\n".join(kept) or "请补充题干", options=options,
                                     answer=answer, explanation=explanation, tags=meta.get("tags", [])), require_answer=False)
        except ValueError:
            data = Question(kind=kind, body=literal("\n".join(kept) or "请补充题干"),
                            options=[Option(body=literal(value)) for value in options] if kind in {"single", "multiple"} else [],
                            answer=Answer(body=literal(answer), explanation=literal(explanation)))
            notes.append("答案或公式未能可靠转换，请手动补录")
        result.append({"key": key, "question": data.model_dump(), "warnings": notes + data.problems()})
    return {"candidates": result, "warnings": warnings, "count": len(result)}
