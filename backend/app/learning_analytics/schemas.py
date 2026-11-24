from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetricMapping(Strict):
    column: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["score", "homework", "attendance", "number", "category"] = "score"
    maximum: float | None = Field(default=None, ge=0, le=100000)


class MappingConfig(Strict):
    student_code: str = Field(min_length=1, max_length=160)
    student_name: str | None = Field(default=None, max_length=160)
    occurred_at: str | None = Field(default=None, max_length=160)
    activity: str | None = Field(default=None, max_length=160)
    knowledge_tag: str | None = Field(default=None, max_length=160)
    maximum_column: str | None = Field(default=None, max_length=160)
    metrics: list[MetricMapping] = Field(min_length=1, max_length=12)


class SaveMappingTemplate(Strict):
    title: str = Field(min_length=1, max_length=100)
    category: Literal["score", "homework", "attendance", "custom"] = "custom"
    config: MappingConfig


class SaveDashboardTemplate(Strict):
    title: str = Field(min_length=1, max_length=100)
    config: dict = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def validate_panels(cls, value):
        allowed = {"metrics", "trend", "distribution", "categories", "students", "score", "attendance"}
        panels = value.get("panels", [])
        if not isinstance(panels, list) or len(panels) > 7 or any(panel not in allowed for panel in panels):
            raise ValueError("大屏模板仅能配置允许的统计面板")
        return {"panels": list(dict.fromkeys(panels))}


class SheetSelection(Strict):
    sheet_name: str = Field(default="", max_length=160)


class UpdateImport(Strict):
    title: str = Field(min_length=1, max_length=160)
    class_code: str | None = Field(default=None, max_length=64)
    term_label: str = Field(default="", max_length=64)


class GeneratePlan(Strict):
    course_id: int
    class_code: str | None = None
    scope: Literal["class", "student"] = "class"
    student_code: str | None = None
    focus: str = Field(default="", max_length=1000)
    batch_ids: list[str] = Field(default_factory=list, max_length=20)
    resource_ids: list[str] = Field(default_factory=list, max_length=20)


class UpdatePlan(Strict):
    title: str = Field(min_length=1, max_length=160)
    focus: str = Field(default="", max_length=1000)
    content: str = Field(min_length=1, max_length=20000)
    resource_ids: list[str] = Field(default_factory=list, max_length=20)


class PublishResource(Strict):
    course_id: int
    source_type: Literal["presentation", "mind_map", "digital_course", "question_bank"]
    source_id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=1200)
    subject: str = Field(default="", max_length=100)
    academic_level: str = Field(default="", max_length=80)
    term_label: str = Field(default="", max_length=64)
    section: str = Field(default="", max_length=160)
    keywords: list[str] = Field(default_factory=list, max_length=30)
