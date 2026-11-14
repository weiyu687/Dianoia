from .models import identifier

WIDTH = 960
HEIGHT = 540

# Each teaching scenario has a sequence and a palette of its own.
PRESETS = {
    "lecture": ("高校理论课", "#17375d", "#166b73", (
        ("课程导入", "cover"), ("学习目标", "bullets"), ("核心概念", "two"), ("例题讲解", "body"), ("课堂小结", "bullets"),
    )),
    "lab": ("实验指导", "#174843", "#0e766e", (
        ("实验任务", "cover"), ("实验目的与原理", "two"), ("操作步骤", "steps"), ("数据记录", "table"), ("结果与讨论", "two"),
    )),
    "practice": ("编程与实训", "#24334c", "#375f9a", (
        ("实训课题", "cover"), ("任务与交付", "two"), ("代码演示", "code"), ("操作流程", "steps"), ("验收标准", "table"),
    )),
    "exercise": ("习题讲评", "#453357", "#755397", (
        ("习题讲评", "cover"), ("题干与条件", "body"), ("思路与解法", "two"), ("典型错误", "table"), ("变式练习", "body"),
    )),
    "case": ("案例教学", "#584037", "#9c4f32", (
        ("案例导入", "cover"), ("背景与问题", "two"), ("证据与分析", "data"), ("方案比较", "table"), ("讨论结论", "body"),
    )),
    "seminar": ("专题研讨", "#3d3557", "#6553a2", (
        ("研讨主题", "cover"), ("阅读线索", "bullets"), ("分组讨论", "two"), ("成果交流", "steps"), ("延伸阅读", "body"),
    )),
    "review": ("章节复习", "#164453", "#14718e", (
        ("复习专题", "cover"), ("知识脉络", "steps"), ("易混概念", "table"), ("自测与反馈", "two"), ("考前清单", "bullets"),
    )),
    "micro": ("微课与慕课", "#36405e", "#4f65aa", (
        ("微课主题", "cover"), ("问题导入", "body"), ("单个知识点", "two"), ("即时测验", "body"), ("回顾与拓展", "bullets"),
    )),
    "orientation": ("课程导学", "#204430", "#46753f", (
        ("课程名称", "cover"), ("学习安排", "steps"), ("资源与任务", "two"), ("考核构成", "table"), ("第一周任务", "bullets"),
    )),
    "field": ("项目汇报与答辩", "#283950", "#38759b", (
        ("项目主题", "cover"), ("问题与目标", "two"), ("方案实施", "steps"), ("结果展示", "data"), ("反思与下一步", "two"),
    )),
}

EXAMPLE = {
    "cover": ("课程名称 · 任课教师 · 教学班",),
    "body": ("在此填写本页要讲授的内容。",),
    "bullets": ("明确本节课要掌握的知识", "说明课堂练习与学习要求", "记录一个待讨论的问题"),
    "two": ("在此填写基础概念或背景条件。", "在此填写例子、对比或应用。"),
    "steps": ("准备与明确任务", "完成操作或分析", "核对结果并记录问题"),
    "code": ("# 在此填写课堂演示代码",),
    "table": ("记录项目、标准与结果。",),
    "data": ("用图表呈现关键结果。此页数据仅用于示例。",),
}


def graphic(kind, x, y, width, height, **values):
    return {"id": identifier(), "kind": kind, "x": x, "y": y, "width": width, "height": height, **values}


def make_slide(title="", layout="blank", palette=("#17375d", "#166b73"), points=None):
    ink, accent = palette
    slide = {"id": identifier(), "background": "#ffffff", "layout": layout, "elements": [], "notes": "", "citations": []}
    if layout == "blank":
        return slide
    text = graphic
    items = slide["elements"]
    points = EXAMPLE[layout] if points is None else points
    if layout == "cover":
        slide["background"] = ink
        items.extend([
            graphic("shape", 72, 145, 72, 8, fill="#d2b567", locked=True),
            text("text", 72, 185, 812, 128, text=title, size=46, color="#ffffff", bold=True, role="title"),
            text("text", 73, 342, 800, 78, text="\n".join(points), size=22, color="#e0e8f0", role="body"),
        ])
        return slide
    items.extend([
        graphic("shape", 55, 112, 850, 8, fill=accent, locked=True),
        text("text", 55, 40, 850, 70, text=title, size=36, color=ink, bold=True, role="title"),
    ])
    if layout == "two":
        for index in range(2):
            x = 55 + index * 440
            items.append(graphic("shape", x, 152, 410, 315, fill="#edf2f7", locked=True))
            body = "\n".join(points[index::2])
            items.append(text("text", x + 20, 175, 370, 260, text=body, size=24, color=ink, role="body"))
    elif layout == "steps":
        for index, body in enumerate(points[:4]):
            y = 149 + index * 80
            items.extend([graphic("shape", 58, y + 6, 8, 43, fill=accent, locked=True),
                          text("text", 84, y, 810, 65, text=f"{index + 1:02d}   {body}", size=24, color=ink, role="body")])
    elif layout == "table":
        items.extend([text("text", 56, 142, 848, 70, text="\n".join(points), size=22, color=ink, role="body"),
                      graphic("table", 56, 239, 848, 195, rows=[["项目", "要求", "记录"], ["项目一", "", ""], ["项目二", "", ""]])])
    elif layout == "data":
        items.extend([text("text", 56, 143, 306, 318, text="\n".join(points), size=22, color=ink, role="body"),
                      graphic("chart", 395, 142, 510, 318, labels=["样例一", "样例二", "样例三"], values=[35, 52, 43], fill=accent)])
    else:
        body = "\n".join(f"•  {point}" if layout == "bullets" else point for point in points)
        items.append(text("text", 55, 152, 850, 317, text=body, size=23 if layout == "code" else 27,
                          font="Consolas" if layout == "code" else "Microsoft YaHei", color=ink, role="body"))
    return slide


def builtin(identifier_):
    title, ink, accent, sections = PRESETS[identifier_]
    return {"id": identifier_, "title": title, "builtin": True, "accent": accent,
            "document": {"slides": [make_slide(label, layout, (ink, accent)) for label, layout in sections], "sources": []}}
