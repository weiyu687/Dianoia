from threading import Lock
from typing import Literal

from ..presentations import (
    GenerateDeck, SlideChange, generate_presentation, get_presentation, list_presentations,
    list_templates as list_slide_templates, store_suggestion,
)


def make_tools(run_tool, course_id):
    created_presentations = {}
    presentation_suggestions = {}
    creation_lock = Lock()

    def find_presentations() -> list:
        """列出当前课程的演示文稿 ID、名称和版本。"""
        return run_tool(lambda session, teacher: list_presentations(course_id, session, teacher)[:50])

    def find_presentation_templates() -> list:
        """列出可用于制作演示文稿的教学模板名称与 ID。"""
        return run_tool(lambda session, teacher: [
            {key: template[key] for key in ("id", "title", "builtin")} for template in list_slide_templates(session, teacher)[:50]
        ])

    def presentation_contents(presentation_id: str, page: int | None = None) -> dict:
        """读取课件大纲或指定页的文字、备注及课件资料。页码从 1 开始。"""
        def read(session, teacher):
            row = get_presentation(presentation_id, session, teacher)
            if row["course_id"] != course_id:
                return {"error": "当前课程没有该课件"}
            document = row["document"]
            slides = document["slides"]
            if page is not None and not 1 <= page <= len(slides):
                return {"error": "页码超过课件范围"}
            if page is None:
                content = [{"id": slide["id"], "page": index, "title": next((
                    element["text"] for element in slide["elements"] if element["kind"] == "text"
                ), "")[:160]} for index, slide in enumerate(slides, 1)]
            else:
                slide = slides[page - 1]
                content = [{"id": slide["id"], "page": page, "notes": slide["notes"][:2000], "citations": slide["citations"],
                            "text": [{"id": item["id"], "text": item["text"][:800]}
                                     for item in slide["elements"] if item["kind"] == "text"][:16]}]
            return {"title": row["title"], "revision": row["revision"], "slides": content, "sources": document["sources"]}
        return run_tool(read)

    def create_presentation_draft(title: str, instruction: str = "", template_id: str | None = None,
                                  sources: list[dict] | None = None, page_count: int = 8, audience: str = "",
                                  minutes: int = 45, lesson_id: str | None = None, language: Literal["zh", "en"] = "zh",
                                  writing_style: Literal["general", "academic", "workshop", "briefing"] = "general",
                                  density: Literal["compact", "standard", "detailed"] = "standard", speaker_notes: bool = True,
                                  charts: Literal["auto", "off", "example"] = "auto", chart_data: str = "") -> dict:
        """生成当前课程的课件。sources 含 resource_id、start、end。chart_data 是教师给出的类别,数值，每行一项。"""
        try:
            data = GenerateDeck(course_id=course_id, title=title, instruction=instruction, template_id=template_id,
                                sources=sources or [], page_count=page_count, audience=audience, minutes=minutes,
                                lesson_id=lesson_id, language=language, writing_style=writing_style, density=density,
                                speaker_notes=speaker_notes, charts=charts, chart_data=chart_data)
        except ValueError:
            return {"error": "请核对课件标题、页数、模板和资料页码"}

        def create(session, teacher):
            key = data.model_dump_json()
            with creation_lock:
                if key not in created_presentations:
                    row = generate_presentation(data, session, teacher)
                    created_presentations[key] = {"id": row["id"], "title": row["title"], "editor": f"/#/presentations/{row['id']}"}
                return created_presentations[key]
        return run_tool(create)

    def propose_presentation_edit(presentation_id: str, page: int, instruction: str, mode: str = "page",
                                  element_id: str | None = None) -> dict:
        """为指定页生成修改候选。mode 为 page、text、notes 或 insert。text 需要文本对象 ID。"""
        def propose(session, teacher):
            row = get_presentation(presentation_id, session, teacher)
            slides = row["document"]["slides"]
            if row["course_id"] != course_id or not 1 <= page <= len(slides):
                return {"error": "当前课程没有该课件或页码越界"}
            try:
                data = SlideChange(revision=row["revision"], mode=mode, slide_id=slides[page - 1]["id"],
                                   element_id=element_id, instruction=instruction)
            except ValueError:
                return {"error": "请核对修改范围和要求"}
            key = (presentation_id, data.model_dump_json())
            with creation_lock:
                if key not in presentation_suggestions:
                    candidate_id = store_suggestion(presentation_id, data, session, teacher)
                    presentation_suggestions[key] = {"id": candidate_id, "presentation_id": presentation_id,
                                                     "page": page, "title": row["title"]}
                candidate = presentation_suggestions[key]
            return candidate | {"editor": f"/#/presentations/{presentation_id}?page={page}&candidate={candidate['id']}"}
        return run_tool(propose)

    tools = [
        find_presentations,
        find_presentation_templates,
        presentation_contents,
        create_presentation_draft,
        propose_presentation_edit,
    ]
    return tools, {"created_presentations": created_presentations, "presentation_suggestions": presentation_suggestions}
