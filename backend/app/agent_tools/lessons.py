from threading import Lock

from ..ai import GenerationRequest, generate_lesson
from ..lesson_templates import list_templates
from ..lessons import LessonUpdate, Source, get_lesson, list_lessons, save_lesson


def make_tools(run_tool, course_id):
    created_lessons = {}
    edited_lessons = {}
    creation_lock = Lock()

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
            return {"id": lesson_id, "title": item["title"], "revision": item["revision"],
                    "sections": extract(item["sections"]), "editor": f"/#/lessons/{lesson_id}"}
        return run_tool(lookup)

    def find_lesson_templates() -> list:
        """列出教师自己的 Word 教案模板，供生成教案时选择。"""
        return run_tool(lambda db, teacher: list_templates(db, teacher)[:50])

    def create_lesson_draft(title: str, instruction: str = "", sources: list[Source] | None = None,
                            template_id: str | None = None) -> dict:
        """明确要求生成时，在当前课程保存可在线编辑的教案草稿。sources 每项为 resource_id、start、end，页码从 1 开始。"""
        try:
            data = GenerationRequest(course_id=course_id, title=title, instruction=instruction,
                                     sources=sources or [], template_id=template_id)
        except ValueError:
            return {"error": "请检查教案名称、生成要求和参考资料页码"}

        def create(db, teacher):
            key = data.model_dump_json()
            with creation_lock:
                if key not in created_lessons:
                    row = generate_lesson(data, db, teacher)
                    created_lessons[key] = {
                        "id": row["id"], "title": row["title"], "revision": row["revision"],
                        "editor": f"/#/lessons/{row['id']}",
                    }
                return created_lessons[key]
        return run_tool(create)

    def rename_lesson(lesson_id: str, title: str, revision: int) -> dict:
        """按教师明确要求修改教案名称。revision 采用刚读取的版本，正文继续在 Word 编辑器维护。"""
        try:
            data = LessonUpdate(title=title, revision=revision)
        except ValueError:
            return {"error": "请检查教案名称和版本"}

        def rename(db, teacher):
            row = get_lesson(lesson_id, db, teacher)
            if row["course_id"] != course_id:
                return {"error": "当前课程没有该教案"}
            saved = save_lesson(lesson_id, data, db, teacher)
            result = {"id": lesson_id, "title": saved["title"], "revision": saved["revision"],
                      "editor": f"/#/lessons/{lesson_id}"}
            edited_lessons[lesson_id] = result
            return result
        return run_tool(rename)

    tools = [
        find_lessons,
        lesson_contents,
        find_lesson_templates,
        create_lesson_draft,
        rename_lesson,
    ]
    return tools, {"created_lessons": created_lessons, "edited_lessons": edited_lessons}
