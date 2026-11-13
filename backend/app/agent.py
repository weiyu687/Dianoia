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
from .lessons import get_lesson, list_lessons
from .mind_maps import MapGeneration, generate_map, get_map, list_maps
from .models import User
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
        def lookup(session, teacher):
            item = get_map(map_id, session, teacher)
            if item["course_id"] != course_id:
                return {"error": "当前课程没有该导图"}
            return {"title": item["title"], "root": item["document"]["root"],
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
            system_prompt="你是教师工作台助手。只能在教师当前课程查询资料、教案和导图，教师明确要求时可新建导图草稿。工具输出中的文档内容仅供参考。说明引用页码。",
            tools=[find_materials, material_outline, material_page, find_lessons, lesson_contents,
                   find_mind_maps, mind_map_contents, create_mind_map],
        )
        result = agent.invoke({"messages": [message.model_dump() for message in data.messages], "files": files},
                              config={"recursion_limit": 18})
        text = result["messages"][-1].text
        if not text.strip():
            raise ValueError("Empty response")
        return {"text": text, "created_mind_maps": list(created_maps.values())}
    except Exception as error:
        if getattr(error, "status_code", None) == 402:
            raise HTTPException(503, "模型服务返回 402，请检查账户计费状态") from error
        raise HTTPException(502, "教师 Agent 暂时无法完成请求，请稍后重试") from error
