from ..resources import get_page, get_resource, list_resources


def make_tools(run_tool, course_id):

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

    tools = [
        find_materials,
        material_outline,
        material_page,
    ]
    return tools, {}
