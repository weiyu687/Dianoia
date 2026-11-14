from math import ceil
from unicodedata import category, east_asian_width

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

THEMES = {
    "editorial": ("简报白", "#142b3a", "#00645f", "#f7f7f2", "#e3eeeb", "#152e3a"),
    "studio": ("深靛科技", "#e9efff", "#9fb4ff", "#121a32", "#233252", "#182545"),
    "paper": ("暖纸刊物", "#38271d", "#99402d", "#fbf4e8", "#f1e3d2", "#efe0c8"),
    "modern": ("石墨与青绿", "#1f2e29", "#175842", "#f3f8f4", "#deece4", "#142a23"),
}


def theme_name(key):
    return THEMES[key][0] if key in THEMES else PRESETS[key][0]


def template_keys():
    return (*THEMES, *PRESETS)


def graphic(kind, x, y, width, height, **values):
    return {"id": identifier(), "kind": kind, "x": x, "y": y, "width": width, "height": height, **values}


def fit_text(value, width, height, size, *, monospace=False):
    def unit(char):
        if category(char).startswith("M"):
            return 0
        if east_asian_width(char) in {"W", "F", "A"}:
            return 1
        return 0.61 if monospace else 0.57

    lines = [sum(unit(char) for char in line) for line in value.expandtabs(4).splitlines()] or [0]
    for candidate in range(size, 13, -1):
        columns = width / candidate * 0.94
        wrapped = sum(max(1, ceil(line / columns)) for line in lines)
        if wrapped * candidate * 1.2 <= height:
            return candidate
    return 14


def compose_slide(title, layout, theme, points, *, summary="", sections=(), code="", table=(), formula="", page=None, total=None):
    _, ink, accent, background, panel, cover = THEMES.get(theme, THEMES["editorial"])
    dark_cover = theme != "paper"
    if theme in PRESETS:
        _, legacy_ink, accent, _ = PRESETS[theme]
        cover = legacy_ink
    slide = {"id": identifier(), "layout": layout, "theme": theme, "background": background, "elements": []}
    items = slide["elements"]

    def box(x, y, w, h, fill, radius=False):
        items.append(graphic("shape", x, y, w, h, fill=fill, shape="round" if radius else "rect", locked=True))

    def text(x, y, w, h, value, size, *, color=ink, bold=False, role=None, font="Microsoft YaHei"):
        if value:
            items.append(graphic("text", x, y, w, h, text=value, size=fit_text(value, w, h, size, monospace=font == "Consolas"),
                                 color=color, bold=bold, role=role, font=font))

    if layout in {"cover", "closing"}:
        slide["background"] = cover
        primary = "#ffffff" if dark_cover else "#38271d"
        muted = "#dce7ed" if dark_cover else "#684638"
        if theme == "studio":
            box(733, 0, 227, 540, "#233252")
            for x in (760, 818, 876):
                box(x, 104, 8, 306, "#3a4b7e")
        elif theme == "paper":
            box(0, 0, 960, 23, accent)
            box(61, 360, 838, 9, "#c08466")
        elif theme == "modern":
            box(690, 0, 270, 540, "#23583f")
            box(743, 100, 155, 340, "#2a6b4e", True)
        else:
            box(64, 124, 108, 8, "#e2b85c")
        text(64, 155, 632 if theme in {"studio", "modern"} else 830, 132, title, 46, color=primary, bold=True, role="title")
        text(66, 300 if layout == "cover" else 276, 620, 76 if layout == "cover" else 157,
             summary or "\n".join(points[:1] if layout == "cover" else points[:3]), 23, color=muted, role="body")
        if layout == "closing" and summary and points:
            text(66, 347, 620, 124, "\n".join(f"•  {point}" for point in points[:3]), 20, color=primary, role="body")
        return slide

    text(58, 42, 846, 65, title, 34, bold=True, role="title")
    box(58, 115, 844, 8, panel)
    box(58, 115, 72, 8, accent)
    text(58, 137, 844, 60, summary, 19, color=accent, role="body")
    start = 201 if summary else 159
    if page is not None:
        text(856, 499, 70, 24, f"{page:02d} / {total:02d}", 13, color=accent)
    if layout == "table":
        items.append(graphic("table", 58, start, 844, min(284, len(table) * 50), rows=[list(row) for row in table],
                             header_fill=cover, header_color="#ffffff" if dark_cover else ink,
                             fill=panel, color=ink, size=18 if len(table) < 6 else 16))
    elif layout == "code":
        code_w = 550 if points else 844
        box(58, start, code_w, 272, "#172035", True)
        text(78, start + 20, code_w - 40, 237, code, 17, color="#e8edf7", role="body", font="Consolas")
        text(636, start + 5, 265, 260, "\n\n".join(points), 18, role="body")
    elif layout in {"two", "cards", "agenda", "steps"}:
        groups = list(sections) or [(point, "") for point in points]
        if layout == "steps":
            groups = groups[:4]
            w = 196
            for i, (heading, detail) in enumerate(groups):
                x = 58 + i * 216
                box(x, start, w, 231, panel, True)
                text(x + 13, start + 14, w - 26, 27, f"{i + 1:02d}", 18, color=accent, bold=True)
                text(x + 13, start + 48, w - 26, 57, heading, 19, bold=True, role="body")
                text(x + 13, start + 108, w - 26, 112, detail, 16, role="body")
                if i + 1 < len(groups):
                    text(x + w + 2, start + 95, 18, 26, "→", 16, color=accent, bold=True)
        else:
            count = min(len(groups), 2 if layout == "two" else 6 if layout == "agenda" else 4)
            card_h = 235 if count <= 2 else 122 if count <= 4 else 89
            for i, (heading, detail) in enumerate(groups[:count]):
                x, y = 58 + i % 2 * 432, start + i // 2 * (card_h + 10)
                box(x, y, 412, card_h, panel, True)
                text(x + 16, y + 12, 380, 42, heading, 20, bold=True, role="body")
                text(x + 16, y + 53, 380, card_h - 56, detail, 17, role="body")
    elif formula:
        box(58, start, 844, 146, panel, True)
        items.append(graphic("formula", 79, start + 14, 801, 120, latex=formula, size=31, align="center", color=ink))
        text(58, start + 163, 844, 114, "\n\n".join(points[:2]), 19, role="body")
    else:
        for i, point in enumerate(points[:5]):
            y = start + i * 57
            box(58, y + 9, 8, 8, accent)
            text(80, y, 812, 53, point, 22, role="body")
    return slide


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
    if identifier_ in THEMES:
        name = theme_name(identifier_)
        previews = [
            compose_slide(name, "cover", identifier_, ["结构清晰的内容演示"]),
            compose_slide("内容概览", "agenda", identifier_, [], sections=[("背景与问题", "界定范围与目标"), ("核心内容", "逐项展示分析与证据"), ("示例与应用", "说明方法如何使用"), ("行动与回顾", "列出后续步骤")]),
            compose_slide("核心方法", "steps", identifier_, [], sections=[("界定问题", "说明需要解决什么"), ("验证方案", "列出步骤与输入"), ("核对结果", "说明如何判断完成")]),
            compose_slide("证据与对照", "table", identifier_, [], table=[["比较维度", "方案一", "方案二"], ["适用范围", "已有条件", "新增条件"], ["验证方式", "样本检查", "现场验证"]]),
            compose_slide("总结与行动", "closing", identifier_, ["记录重点并明确下一步。"]),
        ]
        return {"id": identifier_, "title": name, "builtin": True, "document": {"slides": previews, "sources": []}}
    title, ink, accent, sections = PRESETS[identifier_]
    return {"id": identifier_, "title": title, "builtin": True, "accent": accent,
            "document": {"slides": [make_slide(label, layout, (ink, accent)) for label, layout in sections], "sources": []}}
