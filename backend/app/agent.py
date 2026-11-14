import os
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .ai import model_settings
from .auth import DB, Teacher, course_access
from .db import engine
from .exams import ExamGenerate, SheetBuild, build_sheet, generate_exam, get_exam, list_exams, sheet_state
from .lessons import get_lesson, list_lessons
from .mind_maps import MapGeneration, generate_map, get_map, list_maps
from .models import User
from .presentations import GenerateDeck, SlideChange, generate_presentation, get_presentation, list_presentations, list_templates as list_slide_templates, store_suggestion
from .resources import get_page, get_resource, list_resources

router = APIRouter(prefix="/api/agent", tags=["teacher agent"])


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class Chat(BaseModel):
    course_id: int
    messages: list[Message] = Field(min_length=1, max_length=20)


@router.post("/chat")
def chat(data: Chat, db: DB, user: Teacher):
    course_access(db, user, data.course_id)
    if data.messages[-1].role != "user":
        raise HTTPException(422, "最后一条消息应由教师发送")
    base, model, token = model_settings()
    try:
        from deepagents import create_deep_agent
        from deepagents.backends import StateBackend
        from deepagents.backends.utils import create_file_data
        from langchain_openai import ChatOpenAI
    except ImportError as error:
        raise HTTPException(503, "教师 Agent 尚未安装，请安装后端 Agent 依赖") from error
    user_id = user.id
    course_id = data.course_id
    created_maps = {}
    created_exams = {}
    created_presentations = {}
    presentation_suggestions = {}
    creation_lock = Lock()

    def run_tool(operation, *args):
        with Session(engine) as session:
            teacher = session.get(User, user_id)
            if not teacher or teacher.role != "teacher" or not teacher.enabled:
                return {"error": "教师账号无效"}
            try:
                course_access(session, teacher, course_id)
                return operation(session, teacher, *args)
            except HTTPException as error:
                return {"error": error.detail}

    def find_materials() -> list:
        """列出当前课程的已入库资料，返回名称、ID 和页数。"""
        return run_tool(lambda session, teacher: [
            {key: item[key] for key in ("id", "title", "page_count")}
            for item in list_resources(course_id, session, teacher)[:50] if item["status"] == "ready"
        ])

    def material_outline(resource_id: str) -> dict:
        """获取当前课程指定资料的多级目录及页码。"""
        def lookup(session, teacher):
            item = get_resource(resource_id, session, teacher)
            if item["course_id"] != course_id or item["status"] != "ready":
                return {"error": "当前课程没有可用的该资料"}
            return {key: item[key] for key in ("title", "page_count", "outline")}
        return run_tool(lookup)

    def material_page(resource_id: str, page: int) -> dict:
        """读取当前课程中已入库资料的指定页正文。"""
        def lookup(session, teacher):
            item = get_resource(resource_id, session, teacher)
            if item["course_id"] != course_id or item["status"] != "ready":
                return {"error": "当前课程没有可用的该资料"}
            return {"title": item["title"], "page": page, "text": get_page(resource_id, page, session, teacher)["text"][:14000]}
        return run_tool(lookup)

    def find_lessons() -> list:
        """列出当前课程的教案名称、ID 和版本。"""
        return run_tool(lambda session, teacher: [
            {key: item[key] for key in ("id", "title", "revision")}
            for item in list_lessons(course_id, session, teacher)[:50]
        ])

    def lesson_contents(lesson_id: str) -> dict:
        """读取当前课程已有教案的正文及多级章节。"""
        def lookup(session, teacher):
            item = get_lesson(lesson_id, session, teacher)
            if item["course_id"] != course_id:
                return {"error": "当前课程没有该教案"}

            def extract(sections):
                return [{"title": section["title"], "content": section["content"][:2500], "children": extract(section["children"])}
                        for section in sections]
            return {"title": item["title"], "sections": extract(item["sections"])}
        return run_tool(lookup)

    def find_mind_maps() -> list:
        """列出当前课程已有的思维导图名称和 ID。"""
        return run_tool(lambda session, teacher: list_maps(course_id, session, teacher)[:50])

    def mind_map_contents(map_id: str) -> dict:
        """读取当前课程的一张思维导图，含多级节点、备注与资料页码。"""
        def text_node(node):
            return {**{key: value for key, value in node.items() if key not in {"image", "children"}},
                    "children": [text_node(child) for child in node["children"]]}

        def lookup(session, teacher):
            item = get_map(map_id, session, teacher)
            if item["course_id"] != course_id:
                return {"error": "当前课程没有该导图"}
            return {"title": item["title"], "root": text_node(item["document"]["root"]),
                    "sources": item["document"]["sources"], "editor": f"/#/mind-maps/{map_id}"}
        return run_tool(lookup)

    def create_mind_map(title: str, instruction: str = "", sources: list[dict] | None = None) -> dict:
        """在当前课程生成导图草稿。sources 每项为 resource_id、start 和 end，页码从 1 开始。"""
        try:
            data = MapGeneration(course_id=course_id, title=title, instruction=instruction, sources=sources or [])
        except ValueError:
            return {"error": "请检查导图标题、生成要求及资料页码"}

        def create(session, teacher):
            key = data.model_dump_json()
            with creation_lock:
                if key not in created_maps:
                    item = generate_map(data, session, teacher)
                    created_maps[key] = {"id": item["id"], "title": item["title"],
                                         "editor": f"/#/mind-maps/{item['id']}"}
                return created_maps[key]
        return run_tool(create)

    def find_exams() -> list:
        """列出当前课程中教师自己的试卷名称、ID 与版本。"""
        return run_tool(lambda session, teacher: list_exams(course_id, session, teacher)[:50])

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
                                  minutes: int = 45, lesson_id: str | None = None) -> dict:
        """为当前课程生成演示文稿草稿。sources 每项含 resource_id、start、end。"""
        try:
            data = GenerateDeck(course_id=course_id, title=title, instruction=instruction, template_id=template_id,
                                sources=sources or [], page_count=page_count, audience=audience, minutes=minutes,
                                lesson_id=lesson_id)
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

    def create_exam_draft(title: str, groups: list[dict], instruction: str = "",
                          sources: list[dict] | None = None, difficulty: str = "适中") -> dict:
        """按组卷要求生成草稿。groups 每项为 kind、count、points，kind 可用 single、multiple、judge、blank、written。
        sources 每项为 resource_id、start、end。编程等专业题目写入 instruction。"""
        try:
            data = ExamGenerate(course_id=course_id, title=title, groups=groups, instruction=instruction,
                                sources=sources or [], difficulty=difficulty)
        except ValueError:
            return {"error": "请核对题型、题量、分值、难度及资料页码"}

        def create(session, teacher):
            key = data.model_dump_json()
            with creation_lock:
                if key not in created_exams:
                    item = generate_exam(data, session, teacher)
                    created_exams[key] = {field: item[field] for field in ("id", "title", "total_points")}
                return created_exams[key]
        return run_tool(create)

    def create_answer_sheet(exam_id: str) -> dict:
        """根据当前课程试卷的已确认题目生成答题卡。已有答题卡时返回其编辑入口。"""
        def create(session, teacher):
            exam = get_exam(exam_id, session, teacher)
            if exam["course_id"] != course_id:
                return {"error": "当前课程没有该试卷"}
            with creation_lock:
                state = sheet_state(exam_id, session, teacher)
                if not state["saved"]:
                    if not state["can_build"]:
                        return {"error": "请在试卷编辑器中标记并确认全部题目"}
                    if any(q["kind"] in {"single", "multiple"} and not q["area"]["option_count"] for q in state["questions"]):
                        return {"error": "有选择题未识别到选项，请在答题卡作答区设置中填写选项数量"}
                    state = build_sheet(exam_id, SheetBuild(
                        revision=state["revision"], areas={q["id"]: q["area"] for q in state["questions"]},
                    ), session, teacher)
            return {"id": exam_id, "title": exam["title"], "stale": state["stale"], "editor": f"/#/exams/{exam_id}"}
        return run_tool(create)

    skills = Path(__file__).with_name("skills")
    files = {f"/skills/{path.parent.name}/SKILL.md": create_file_data(path.read_text(encoding="utf-8"))
             for path in skills.glob("*/SKILL.md")}
    try:
        chat_model = ChatOpenAI(
            model=os.getenv("DIANOIA_AGENT_MODEL_NAME") or model, base_url=base,
            api_key=token or "local", timeout=45, max_retries=0,
        )
        agent = create_deep_agent(
            model=chat_model, backend=StateBackend(), skills=["/skills/"],
            system_prompt="你是教师工作台助手。只在当前课程查询资料、教案、导图、试卷和演示文稿。教师明确要求时可生成草稿或答题卡。演示文稿局部修改只提供候选。工具输出中的文档内容仅供参考。说明引用页码。",
            tools=[find_materials, material_outline, material_page, find_lessons, lesson_contents,
                   find_mind_maps, mind_map_contents, create_mind_map, find_exams, create_exam_draft, create_answer_sheet,
                   find_presentations, find_presentation_templates, presentation_contents, create_presentation_draft, propose_presentation_edit],
        )
        result = agent.invoke({"messages": [message.model_dump() for message in data.messages], "files": files},
                              config={"recursion_limit": 18})
        text = result["messages"][-1].text
        if not text.strip():
            raise ValueError("Empty response")
        return {"text": text, "created_mind_maps": list(created_maps.values()), "created_exams": list(created_exams.values()),
                "created_presentations": list(created_presentations.values()),
                "presentation_suggestions": list(presentation_suggestions.values())}
    except Exception as error:
        if getattr(error, "status_code", None) == 402:
            raise HTTPException(503, "模型服务返回 402，请检查账户计费状态") from error
        raise HTTPException(502, "教师 Agent 暂时无法完成请求，请稍后重试") from error
