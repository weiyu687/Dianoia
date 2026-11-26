"""Register teacher tools and collect the results produced in one Agent turn."""

from urllib.parse import urlencode

from ..question_banks import tools as question_banks
from . import digital_courses, exams, learning_analytics, lessons, materials, mind_maps, presentations


def question_bank_tools(run_tool, course_id):
    tools, links = question_banks.make_tools(run_tool, course_id)
    return tools, {"question_banks": links}


# Each factory registers its callable tools and declares any result groups.
MODULES = (
    ("teaching-materials", materials.make_tools),
    ("teaching-materials", lessons.make_tools),
    ("mind-maps", mind_maps.make_tools),
    ("exams", exams.make_tools),
    ("presentations", presentations.make_tools),
    ("question-banks", question_bank_tools),
    ("learning-analytics", learning_analytics.make_tools),
    ("digital-courses", digital_courses.make_tools),
)
SKILLS = tuple(dict.fromkeys(skill for skill, _ in MODULES))


def artifact(kind, label, path):
    return lambda row: {
        "kind": kind, "label": label.format_map(row), "id": row["id"],
        "title": row["title"], "route": path(row),
    }


ARTIFACTS = {
    "created_lessons": artifact("lesson", "教案草稿", lambda row: f"/lessons/{row['id']}"),
    "edited_lessons": artifact("lesson", "已重命名教案", lambda row: f"/lessons/{row['id']}"),
    "created_mind_maps": artifact("mind_map", "思维导图", lambda row: f"/mind-maps/{row['id']}"),
    "created_exams": artifact("exam", "试卷草稿", lambda row: f"/exams/{row['id']}"),
    "answer_sheets": artifact("exam", "答题卡", lambda row: f"/exams/{row['id']}"),
    "created_presentations": artifact("presentation", "演示文稿", lambda row: f"/presentations/{row['id']}"),
    "presentation_suggestions": artifact(
        "presentation", "第 {page} 页修改候选",
        lambda row: f"/presentations/{row['presentation_id']}?" + urlencode({"page": row["page"], "candidate": row["id"]}),
    ),
    "question_banks": artifact("question_bank", "在线题库", lambda row: f"/question-banks/{row['id']}"),
    "created_learning_plans": artifact(
        "learning_plan", "学情计划", lambda row: "/learning-analytics?" + urlencode({"plan": row["id"]}),
    ),
    "digital_courses": artifact("digital_course", "数字课程", lambda row: f"/digital-courses/{row['id']}"),
}


def make_tools(run_tool, course_id):
    tools = []
    outputs = {}
    for _, factory in MODULES:
        registered, results = factory(run_tool, course_id)
        tools.extend(registered)
        outputs.update(results)
    return tools, outputs


def tool_results(outputs):
    groups = {key: list(entries.values()) for key, entries in outputs.items()}
    cards = [build(row) for group, build in ARTIFACTS.items() for row in groups.get(group, [])]
    return {**groups, "artifacts": cards}
