from threading import Lock
from typing import Literal

from sqlalchemy import select

from ..learning_analytics.models import SharedLearningResource
from ..learning_analytics.router import dashboard, generate_plan as generate_analytics_plan
from ..learning_analytics.schemas import GeneratePlan


def make_tools(run_tool, course_id):
    created_learning_plans = {}
    creation_lock = Lock()

    def find_learning_analytics(batch_id: str | None = None, class_code: str | None = None,
                                metric: str | None = None) -> dict:
        """读取当前课程最近一批学情分析的聚合指标和历史变化，不返回原始表格行。"""
        def read(session, teacher):
            result = dashboard(course_id, session, teacher, batch_id=batch_id, class_code=class_code, metric=metric)
            batch = result["batch"]
            if not batch:
                return {"message": "所选范围没有已入库的学情数据"}
            return {"batch": {"id": batch["id"], "title": batch["title"], "term": batch["term_label"],
                               "valid_rows": batch["valid_count"], "review_rows": batch["invalid_count"]},
                    **{key: result[key] for key in ("metrics", "selected_metric", "summary", "history")}}
        return run_tool(read)

    def create_learning_plan_draft(scope: Literal["class", "student"] = "class", class_code: str | None = None,
                                   student_code: str | None = None, focus: str = "", batch_id: str | None = None,
                                   resource_ids: list[str] | None = None) -> dict:
        """按已导入数据创建待教师编辑的教学/学习计划草稿。学生姓名和原始表格行不会发送给模型。"""
        try:
            data = GeneratePlan(course_id=course_id, class_code=class_code, scope=scope,
                                student_code=student_code, focus=focus, batch_ids=[batch_id] if batch_id else [],
                                resource_ids=resource_ids or [])
        except ValueError:
            return {"error": "请核对计划范围、班级和数据批次"}
        def create(session, teacher):
            key = data.model_dump_json()
            with creation_lock:
                if key not in created_learning_plans:
                    row = generate_analytics_plan(data, session, teacher)
                    created_learning_plans[key] = {"id": row["id"], "title": row["title"],
                        "scope": row["scope"], "generation_source": row["generation_source"],
                        "editor": f"/#/learning-analytics?plan={row['id']}"}
                return created_learning_plans[key]
        return run_tool(create)

    def find_shared_learning_resources(query: str = "", resource_type: str | None = None) -> list:
        """在平台已发布资源池搜索课件、思维导图、数字课程或在线题库。"""
        def read(session, teacher):
            statement = select(SharedLearningResource).where(SharedLearningResource.status == "published")
            if resource_type in {"presentation", "mind_map", "digital_course", "question_bank"}:
                statement = statement.where(SharedLearningResource.source_type == resource_type)
            if query.strip():
                term = f"%{query.strip()[:80]}%"
                statement = statement.where((SharedLearningResource.title.ilike(term)) |
                    (SharedLearningResource.summary.ilike(term)) | (SharedLearningResource.section.ilike(term)) |
                    (SharedLearningResource.subject.ilike(term)))
            return [{"id": row.id, "title": row.title, "type": row.source_type, "subject": row.subject,
                     "section": row.section, "keywords": row.keywords, "published_at": row.published_at}
                    for row in session.scalars(statement.order_by(SharedLearningResource.published_at.desc()).limit(40))]
        return run_tool(read)

    tools = [
        find_learning_analytics,
        create_learning_plan_draft,
        find_shared_learning_resources,
    ]
    return tools, {"created_learning_plans": created_learning_plans}
