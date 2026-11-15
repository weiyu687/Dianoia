from base64 import b64decode
from itertools import groupby
from io import BytesIO
from math import isfinite
from typing import Annotated, Literal

from PIL import Image, UnidentifiedImageError
from lxml import etree
from pydantic import BaseModel, Field, StringConstraints, model_validator
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_CONNECTOR_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt

from .lessons import Source
from .exam_math import MATH_NS, MC_NS, SOURCE, equation_xml
from .models import identifier
from .presentation_templates import HEIGHT, WIDTH
from .presentation_effects import SlideTiming, add_native_media

DRAWING_2010_NS = "http://schemas.microsoft.com/office/drawing/2010/main"

Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Key = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Layout = Literal["blank", "cover", "body", "bullets", "two", "steps", "code", "table", "data", "cards", "agenda", "focus", "closing"]
TitleCell = Annotated[str, StringConstraints(max_length=160)]
ChartKind = Literal["column", "bar", "line", "area", "scatter", "pie", "donut", "radar"]
ChartValue = Annotated[float, Field(ge=-1e12, le=1e12)]


class Element(BaseModel):
    id: Key = Field(default_factory=identifier)
    kind: Literal["text", "shape", "image", "table", "chart", "formula", "audio", "video"]
    x: float = Field(default=80, ge=-WIDTH, le=WIDTH * 2)
    y: float = Field(default=80, ge=-HEIGHT, le=HEIGHT * 2)
    width: float = Field(default=280, ge=8, le=WIDTH * 2)
    height: float = Field(default=94, ge=8, le=HEIGHT * 2)
    rotation: float = Field(default=0, ge=-360, le=360)
    group: Key | None = None
    locked: bool = False
    fill: Color = "#436790"
    color: Color = "#172b42"
    stroke: Color | None = None
    header_fill: Color = "#e4ebf4"
    header_color: Color | None = None
    text: str = Field(default="", max_length=4000)
    latex: str = Field(default="", max_length=1600)
    font: Literal["Microsoft YaHei", "SimSun", "SimHei", "Arial", "Consolas"] = "Microsoft YaHei"
    size: float = Field(default=24, ge=8, le=144)
    bold: bool = False
    italic: bool = False
    underline: bool = False
    line_height: float = Field(default=1.18, ge=1, le=2.4)
    spacing: float = Field(default=0, ge=0, le=10)
    align: Literal["left", "center", "right"] = "left"
    role: Literal["title", "body"] | None = None
    shape: Literal["rect", "round", "ellipse", "triangle", "arrow", "line", "diamond", "hexagon",
                   "parallelogram", "trapezoid", "chevron", "pentagon", "star", "callout",
                   "arrowLeft", "arrowUp", "arrowDown", "connector", "connectorArrow"] = "rect"
    line_style: Literal["solid", "dash", "dot"] = "solid"
    line_width: float = Field(default=2, ge=1, le=20)
    image: str | None = Field(default=None, max_length=1_400_000)
    media_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")] | None = None
    rows: list[Annotated[list[TitleCell], Field(min_length=1, max_length=10)]] = Field(default_factory=list, max_length=14)
    labels: list[TitleCell] = Field(default_factory=list, max_length=16)
    values: list[ChartValue] = Field(default_factory=list, max_length=16)
    chart: ChartKind = "column"
    chart_title: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def check_content(self):
        if (self.media_id is not None) != (self.kind in {"audio", "video"}):
            raise ValueError("请为音视频对象选择已上传的文件")
        if self.kind == "formula":
            try:
                equation_xml(self.latex)
            except ValueError as error:
                raise ValueError("公式无法转换，请检查 LaTeX 表达式") from error
        if self.kind == "image":
            try:
                prefix, data = self.image.split(",", 1) if self.image else ("", "")
                if prefix not in {"data:image/png;base64", "data:image/jpeg;base64"}:
                    raise ValueError
                with Image.open(BytesIO(b64decode(data, validate=True))) as image:
                    if image.format not in {"JPEG", "PNG"} or image.width * image.height > 6_000_000:
                        raise ValueError
                    image.verify()
            except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
                raise ValueError("请选择有效的 PNG 或 JPEG 图片，且像素不超过 600 万") from error
        if self.kind == "table" and (not self.rows or any(len(row) != len(self.rows[0]) for row in self.rows)):
            raise ValueError("表格各行必须具有相同列数")
        if self.kind == "chart":
            if not self.labels or len(self.labels) != len(self.values) or not all(label.strip() for label in self.labels):
                raise ValueError("图表需要等量的标签和数据")
            if self.chart in {"pie", "donut", "radar"} and (min(self.values) < 0 or max(self.values) <= 0):
                raise ValueError("饼图、环形图和雷达图需要非负值，且至少有一个正值")
            if self.chart == "radar" and len(self.values) < 3:
                raise ValueError("雷达图至少需要三项")
            if self.chart == "scatter":
                try:
                    valid_x = all(isfinite(float(label)) and abs(float(label)) <= 1e12 for label in self.labels)
                except ValueError:
                    valid_x = False
                if not valid_x:
                    raise ValueError("散点图的横坐标必须是有效数字")
        return self


class Animation(BaseModel):
    id: Key = Field(default_factory=identifier)
    target_id: Key
    effect: Literal["fade_in", "fly_in", "emphasis", "fade_out"] = "fade_in"
    trigger: Literal["click", "after"] = "click"
    duration_ms: int = Field(default=500, ge=100, le=5000)


class Slide(BaseModel):
    id: Key = Field(default_factory=identifier)
    background: Color = "#ffffff"
    layout: Layout = "blank"
    theme: Key | None = None
    transition: Literal["none", "fade", "push"] = "none"
    elements: list[Element] = Field(default_factory=list, max_length=100)
    animations: list[Animation] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=8000)
    citations: list[Source] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def check_animations(self):
        if len({animation.id for animation in self.animations}) != len(self.animations):
            raise ValueError("动画编号重复")
        targets = {item.id for item in self.elements}
        if any(animation.target_id not in targets for animation in self.animations):
            raise ValueError("动画目标必须是当前页上的对象")
        return self


class Deck(BaseModel):
    slides: list[Slide] = Field(min_length=1, max_length=80)
    sources: list[Source] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def check_document(self):
        if len({slide.id for slide in self.slides}) != len(self.slides):
            raise ValueError("页面编号重复")
        image_size = 0
        for slide in self.slides:
            if len({element.id for element in slide.elements}) != len(slide.elements):
                raise ValueError("同一页存在重复对象")
            image_size += sum(len(element.image or "") for element in slide.elements)
            for citation in slide.citations:
                if not any(source.resource_id == citation.resource_id and source.start <= citation.start <= citation.end <= source.end
                           for source in self.sources):
                    raise ValueError("单页引用必须在课件已挂载的资料范围内")
        if image_size > 12_000_000:
            raise ValueError("课件中的图片总量超过限制")
        return self


SHAPES = {"rect": MSO_AUTO_SHAPE_TYPE.RECTANGLE, "round": MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
          "ellipse": MSO_AUTO_SHAPE_TYPE.OVAL, "triangle": MSO_AUTO_SHAPE_TYPE.ISOSCELES_TRIANGLE,
          "arrow": MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW, "line": MSO_AUTO_SHAPE_TYPE.RECTANGLE,
          "diamond": MSO_AUTO_SHAPE_TYPE.DIAMOND, "hexagon": MSO_AUTO_SHAPE_TYPE.HEXAGON,
          "parallelogram": MSO_AUTO_SHAPE_TYPE.PARALLELOGRAM, "trapezoid": MSO_AUTO_SHAPE_TYPE.TRAPEZOID,
          "chevron": MSO_AUTO_SHAPE_TYPE.CHEVRON, "pentagon": MSO_AUTO_SHAPE_TYPE.PENTAGON,
          "star": MSO_AUTO_SHAPE_TYPE.STAR_5_POINT, "callout": MSO_AUTO_SHAPE_TYPE.RECTANGULAR_CALLOUT,
          "arrowLeft": MSO_AUTO_SHAPE_TYPE.LEFT_ARROW, "arrowUp": MSO_AUTO_SHAPE_TYPE.UP_ARROW,
          "arrowDown": MSO_AUTO_SHAPE_TYPE.DOWN_ARROW}
CHARTS = {"column": XL_CHART_TYPE.COLUMN_CLUSTERED, "bar": XL_CHART_TYPE.BAR_CLUSTERED,
          "line": XL_CHART_TYPE.LINE_MARKERS, "area": XL_CHART_TYPE.AREA, "scatter": XL_CHART_TYPE.XY_SCATTER,
          "pie": XL_CHART_TYPE.PIE, "donut": XL_CHART_TYPE.DOUGHNUT, "radar": XL_CHART_TYPE.RADAR_MARKERS}


def rgb(value):
    return RGBColor.from_string(value[1:].upper())


def px(value):
    return Pt(value * 0.75)


def format_text(frame, item, value=None):
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = Pt(0)
    for index, line in enumerate((item.text if value is None else value).split("\n")):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[item.align]
        paragraph.space_after = Pt(0)
        paragraph.line_spacing = item.line_height
        run = paragraph.add_run()
        run.text = line
        run.font.name = item.font
        run.font.size = px(item.size)
        run.font.bold, run.font.italic, run.font.underline = item.bold, item.italic, item.underline
        run.font.color.rgb = rgb(item.color)
        props = run._r.get_or_add_rPr()
        if item.spacing:
            props.set("spc", str(round(item.spacing * 75)))
        east_asia = OxmlElement("a:ea")
        east_asia.set("typeface", item.font)
        props.append(east_asia)


def format_equation(frame, item):
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = Pt(0)
    paragraph = frame.paragraphs[0]
    paragraph.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[item.align]
    paragraph.font.size = px(item.size)
    paragraph.font.color.rgb = rgb(item.color)
    equation = etree.fromstring(equation_xml(item.latex).encode())
    equation.attrib.pop(SOURCE, None)
    equation.attrib.pop(f"{{{MC_NS}}}Ignorable", None)
    for run in equation.iter(f"{{{MATH_NS}}}r"):
        run_style = OxmlElement("a:rPr")
        run_style.set("sz", str(round(item.size * 75)))
        fill = etree.SubElement(run_style, qn("a:solidFill"))
        etree.SubElement(fill, qn("a:srgbClr"), val=item.color[1:].upper())
        etree.SubElement(run_style, qn("a:latin"), typeface="Cambria Math")
        run.insert(1 if len(run) and run[0].tag == f"{{{MATH_NS}}}rPr" else 0, run_style)
    node = etree.SubElement(paragraph._p, f"{{{DRAWING_2010_NS}}}m", nsmap={"a14": DRAWING_2010_NS})
    etree.cleanup_namespaces(equation)
    node.append(equation)


def deck_pptx(title, deck, *, for_pdf=False, media=None):
    document = Presentation()
    document.core_properties.title = title
    document.slide_width, document.slide_height = px(WIDTH), px(HEIGHT)
    for source in deck.slides:
        slide = document.slides.add_slide(document.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = rgb(source.background)
        timing = SlideTiming()
        if source.transition != "none" and not for_pdf:
            transition = OxmlElement("p:transition")
            transition.set("spd", "fast")
            effect = OxmlElement(f"p:{source.transition}")
            if source.transition == "push":
                effect.set("dir", "l")
            transition.append(effect)
            slide._element.insert_element_before(transition, "p:timing", "p:extLst")
        for item in source.elements:
            position = [px(value) for value in (item.x, item.y, item.width, item.height)]
            if item.kind in {"text", "formula"}:
                shape = slide.shapes.add_textbox(*position)
                if item.kind == "formula":
                    format_equation(shape.text_frame, item)
                    # Impress renders imported Office Math in black, including on dark slides.
                    background = rgb(source.background)
                    if for_pdf and sum(channel * weight for channel, weight in zip(background, (0.2126, 0.7152, 0.0722))) < 145:
                        shape.fill.solid()
                        shape.fill.fore_color.rgb = rgb("#f5f7fb")
                else:
                    format_text(shape.text_frame, item)
            elif item.kind in {"audio", "video"}:
                asset = (media or {}).get(item.media_id)
                if for_pdf:
                    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, *position)
                    shape.fill.solid()
                    shape.fill.fore_color.rgb = rgb("#ecf1fa")
                    shape.line.fill.background()
                    name = asset.filename if asset else (item.text or "").strip()
                    label = "音频" if item.kind == "audio" else "视频"
                    format_text(shape.text_frame, item.model_copy(update={"color": "#263754", "size": 18, "align": "center"}),
                                f"{label} · {name}")
                else:
                    shape = add_native_media(slide, item, asset, position)
                    timing.add_media(shape.shape_id, item.kind, asset.duration_ms)
            elif item.kind == "image":
                shape = slide.shapes.add_picture(BytesIO(b64decode(item.image.split(",", 1)[1])), *position)
            elif item.kind == "table":
                shape = slide.shapes.add_table(len(item.rows), len(item.rows[0]), *position)
                for i, row in enumerate(item.rows):
                    for j, value in enumerate(row):
                        cell = shape.table.cell(i, j)
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = rgb(item.header_fill if i == 0 else item.fill if item.header_color else "#f5f7fa")
                        format_text(cell.text_frame, item.model_copy(update={
                            "size": min(item.size, 20), "bold": i == 0,
                            "color": item.header_color if i == 0 and item.header_color else item.color,
                        }), value)
                        cell.margin_left, cell.margin_top = Pt(5), Pt(4)
            elif item.kind == "chart":
                if item.chart == "scatter":
                    data = XyChartData()
                    series = data.add_series("数据")
                    for label, value in zip(item.labels, item.values):
                        series.add_data_point(float(label), value)
                else:
                    data = CategoryChartData()
                    data.categories = item.labels
                    data.add_series("数据", item.values)
                shape = slide.shapes.add_chart(CHARTS[item.chart], *position, data)
                chart = shape.chart
                chart.has_title = bool(item.chart_title)
                if chart.has_title:
                    chart.chart_title.text_frame.text = item.chart_title
                    title_font = chart.chart_title.text_frame.paragraphs[0].font
                    title_font.size = Pt(12)
                    title_font.color.rgb = rgb(item.color)
                chart.has_legend = item.chart in {"pie", "donut"}
                if chart.has_legend:
                    chart.legend.font.color.rgb = rgb(item.color)
                else:
                    for axis in (chart.category_axis, chart.value_axis):
                        axis.tick_labels.font.color.rgb = rgb(item.color)
                if item.chart in {"column", "bar", "area"}:
                    chart.series[0].format.fill.solid()
                    chart.series[0].format.fill.fore_color.rgb = rgb(item.fill)
                elif item.chart == "scatter":
                    marker = chart.series[0].marker.format
                    marker.fill.solid()
                    marker.fill.fore_color.rgb = rgb(item.fill)
                    marker.line.color.rgb = rgb(item.fill)
                elif item.chart in {"line", "radar"}:
                    chart.series[0].format.line.color.rgb = rgb(item.fill)
            else:
                if item.shape in {"connector", "connectorArrow"}:
                    x, y, w, h = position
                    shape = slide.shapes.add_connector(MSO_CONNECTOR_TYPE.STRAIGHT, x, y, x + w, y + h)
                    shape.line.color.rgb = rgb(item.stroke or item.fill)
                    shape.line.width = px(item.line_width)
                    shape.line.dash_style = {"solid": MSO_LINE_DASH_STYLE.SOLID, "dash": MSO_LINE_DASH_STYLE.DASH,
                                             "dot": MSO_LINE_DASH_STYLE.ROUND_DOT}[item.line_style]
                    if item.shape == "connectorArrow":
                        end = OxmlElement("a:tailEnd")
                        end.set("type", "triangle")
                        shape.line._get_or_add_ln().append(end)
                    if item.rotation:
                        shape.rotation = item.rotation % 360
                    continue
                if item.shape == "line":
                    position[3] = px(min(3, item.height))
                shape = slide.shapes.add_shape(SHAPES[item.shape], *position)
                effect = shape._element.find(f".//{qn('a:effectRef')}")
                if effect is not None:
                    effect.set("idx", "0")
                shape.fill.solid()
                shape.fill.fore_color.rgb = rgb(item.fill)
                if item.stroke:
                    shape.line.color.rgb = rgb(item.stroke)
                else:
                    shape.line.fill.background()
            if item.rotation and item.kind not in {"table", "chart"}:
                shape.rotation = item.rotation % 360
        native_items = list(zip(source.elements, list(slide.shapes)))
        target_ids = {item.id: shape.shape_id for item, shape in native_items}
        for group, entries in groupby(native_items, key=lambda entry: entry[0].group):
            members = list(entries)
            if group and len(members) > 1 and all(item.kind not in {"table", "chart", "audio", "video"} for item, _ in members):
                shapes = [shape for _, shape in members]
                anchor = shapes[-1]._element.getnext()
                native = slide.shapes.add_group_shape(shapes)
                if anchor is not None:
                    anchor.addprevious(native._element)
        if not for_pdf:
            timing.write(slide, source.animations, target_ids)
        if source.notes:
            slide.notes_slide.notes_text_frame.text = source.notes
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
