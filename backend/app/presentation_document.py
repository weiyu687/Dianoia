from base64 import b64decode
from itertools import groupby
from io import BytesIO
from typing import Annotated, Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, StringConstraints, model_validator
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt

from .lessons import Source
from .models import identifier
from .presentation_templates import HEIGHT, WIDTH

Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Key = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Layout = Literal["blank", "cover", "body", "bullets", "two", "steps", "code", "table", "data"]
TitleCell = Annotated[str, StringConstraints(max_length=160)]


class Element(BaseModel):
    id: Key = Field(default_factory=identifier)
    kind: Literal["text", "shape", "image", "table", "chart"]
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
    text: str = Field(default="", max_length=4000)
    font: Literal["Microsoft YaHei", "SimSun", "SimHei", "Arial", "Consolas"] = "Microsoft YaHei"
    size: float = Field(default=24, ge=8, le=144)
    bold: bool = False
    italic: bool = False
    underline: bool = False
    align: Literal["left", "center", "right"] = "left"
    role: Literal["title", "body"] | None = None
    shape: Literal["rect", "round", "ellipse", "triangle", "arrow", "line"] = "rect"
    image: str | None = Field(default=None, max_length=1_400_000)
    rows: list[Annotated[list[TitleCell], Field(min_length=1, max_length=10)]] = Field(default_factory=list, max_length=14)
    labels: list[TitleCell] = Field(default_factory=list, max_length=16)
    values: list[Annotated[float, Field(ge=0, le=1e12)]] = Field(default_factory=list, max_length=16)
    chart: Literal["column", "line", "pie"] = "column"

    @model_validator(mode="after")
    def check_content(self):
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
        if self.kind == "chart" and (not self.labels or len(self.labels) != len(self.values) or not any(self.values)):
            raise ValueError("图表需要等量的标签和数据，且至少有一个正值")
        return self


class Slide(BaseModel):
    id: Key = Field(default_factory=identifier)
    background: Color = "#ffffff"
    layout: Layout = "blank"
    elements: list[Element] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=8000)
    citations: list[Source] = Field(default_factory=list, max_length=12)


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
          "arrow": MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW, "line": MSO_AUTO_SHAPE_TYPE.RECTANGLE}
CHARTS = {"column": XL_CHART_TYPE.COLUMN_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS, "pie": XL_CHART_TYPE.PIE}


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
        paragraph.line_spacing = 1.18
        run = paragraph.add_run()
        run.text = line
        run.font.name = item.font
        run.font.size = px(item.size)
        run.font.bold, run.font.italic, run.font.underline = item.bold, item.italic, item.underline
        run.font.color.rgb = rgb(item.color)
        props = run._r.get_or_add_rPr()
        east_asia = OxmlElement("a:ea")
        east_asia.set("typeface", item.font)
        props.append(east_asia)


def deck_pptx(title, deck):
    document = Presentation()
    document.core_properties.title = title
    document.slide_width, document.slide_height = px(WIDTH), px(HEIGHT)
    for source in deck.slides:
        slide = document.slides.add_slide(document.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = rgb(source.background)
        for item in source.elements:
            position = [px(value) for value in (item.x, item.y, item.width, item.height)]
            if item.kind == "text":
                shape = slide.shapes.add_textbox(*position)
                format_text(shape.text_frame, item)
            elif item.kind == "image":
                shape = slide.shapes.add_picture(BytesIO(b64decode(item.image.split(",", 1)[1])), *position)
            elif item.kind == "table":
                shape = slide.shapes.add_table(len(item.rows), len(item.rows[0]), *position)
                for i, row in enumerate(item.rows):
                    for j, value in enumerate(row):
                        cell = shape.table.cell(i, j)
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = rgb("#e4ebf4" if i == 0 else "#f5f7fa")
                        format_text(cell.text_frame, item.model_copy(update={"size": min(item.size, 20), "bold": i == 0}), value)
                        cell.margin_left, cell.margin_top = Pt(5), Pt(4)
            elif item.kind == "chart":
                data = CategoryChartData()
                data.categories = item.labels
                data.add_series("数据", item.values)
                shape = slide.shapes.add_chart(CHARTS[item.chart], *position, data)
                chart = shape.chart
                chart.has_title = False
                chart.has_legend = item.chart == "pie"
                if chart.has_legend:
                    chart.legend.font.color.rgb = rgb(item.color)
                else:
                    for axis in (chart.category_axis, chart.value_axis):
                        axis.tick_labels.font.color.rgb = rgb(item.color)
                if item.chart == "column":
                    chart.series[0].format.fill.solid()
                    chart.series[0].format.fill.fore_color.rgb = rgb(item.fill)
                elif item.chart == "line":
                    chart.series[0].format.line.color.rgb = rgb(item.fill)
            else:
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
        # Consecutive objects can share a native PowerPoint group without disturbing other layers.
        for group, entries in groupby(zip(source.elements, list(slide.shapes)), key=lambda entry: entry[0].group):
            members = list(entries)
            if group and len(members) > 1 and all(item.kind not in {"table", "chart"} for item, _ in members):
                shapes = [shape for _, shape in members]
                anchor = shapes[-1]._element.getnext()
                native = slide.shapes.add_group_shape(shapes)
                if anchor is not None:
                    anchor.addprevious(native._element)
        if source.notes:
            slide.notes_slide.notes_text_frame.text = source.notes
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
