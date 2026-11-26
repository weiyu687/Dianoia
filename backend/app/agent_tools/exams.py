from threading import Lock

from ..exams import ExamGenerate, SheetBuild, build_sheet, generate_exam, get_exam, list_exams, sheet_state


def make_tools(run_tool, course_id):
    created_exams = {}
    answer_sheets = {}
    creation_lock = Lock()

    def find_exams() -> list:
        """列出当前课程中教师自己的试卷名称、ID 与版本。"""
        return run_tool(lambda session, teacher: list_exams(course_id, session, teacher)[:50])

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
            link = {"id": exam_id, "title": exam["title"], "stale": state["stale"], "editor": f"/#/exams/{exam_id}"}
            answer_sheets[exam_id] = link
            return link
        return run_tool(create)

    tools = [
        find_exams,
        create_exam_draft,
        create_answer_sheet,
    ]
    return tools, {"created_exams": created_exams, "answer_sheets": answer_sheets}
