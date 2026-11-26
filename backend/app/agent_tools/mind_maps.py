from threading import Lock

from ..mind_maps import MapGeneration, generate_map, get_map, list_maps


def make_tools(run_tool, course_id):
    created_maps = {}
    creation_lock = Lock()

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

    tools = [
        find_mind_maps,
        mind_map_contents,
        create_mind_map,
    ]
    return tools, {"created_mind_maps": created_maps}
