from fastapi import HTTPException

from ..digital_courses import find_project, list_projects, project_view


def make_tools(run_tool, course_id):
    links = {}

    def find_digital_courses() -> list:
        """列出当前课程的数字课程项目，包括页数、视频是否已生成和当前任务状态。"""
        def read(db, teacher):
            fields = ("id", "title", "page_count", "has_video", "video_is_previous")
            return [{**{field: row[field] for field in fields},
                     "job_status": row["job"]["status"] if row["job"] else None}
                    for row in list_projects(course_id, db, teacher)[:30]]
        return run_tool(read)

    def digital_course_status(project_id: str) -> dict:
        """查看当前课程指定数字课程的生产状态、阶段、完成页数，以及是否有可播放视频。返回制作页面入口。"""
        def read(db, teacher):
            project = find_project(db, teacher, project_id)
            if project.course_id != course_id:
                raise HTTPException(404, "当前课程没有该数字课程")
            row = project_view(db, project, detail=False)
            # Only expose status and progress. Media and voice assets are managed in the editor.
            fields = ("id", "title", "page_count", "has_video", "video_is_previous")
            link = {"id": project.id, "title": project.title, "editor": f"/#/digital-courses/{project.id}"}
            links[project.id] = link
            job = row["job"]
            return {**{field: row[field] for field in fields}, "editor": link["editor"],
                    "job": {field: job[field] for field in ("kind", "status", "stage", "completed", "total")} if job else None}
        return run_tool(read)

    return [find_digital_courses, digital_course_status], {"digital_courses": links}
