import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..lessons import Source, Title
from ..models import identifier
from .content import asset_ids, empty_doc, plain, validate_doc
from ..exam_math import has_supported_formula

Kind = Literal["single", "multiple", "judge", "blank", "written"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cover(Strict):
    theme: Literal["academic", "blue", "paper", "nature", "purple", "grid"] = "academic"
    accent: str = Field(default="#7759ce", pattern=r"^#[0-9a-fA-F]{6}$")
    layout: Literal["left", "center"] = "left"
    asset_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class Section(Strict):
    id: str = Field(default_factory=identifier, pattern=r"^[a-f0-9]{32}$")
    title: Title
    parent_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class Material(Strict):
    id: str = Field(default_factory=identifier, pattern=r"^[a-f0-9]{32}$")
    title: Title
    body: dict = Field(default_factory=empty_doc)
    _doc = field_validator("body")(validate_doc)


class BankCreate(Strict):
    course_id: int
    title: Title


class BankUpdate(Strict):
    revision: int = Field(ge=1)
    title: Title
    description: str = Field(default="", max_length=3000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    cover: Cover = Field(default_factory=Cover)
    sections: list[Section] = Field(default_factory=list, max_length=200)
    materials: list[Material] = Field(default_factory=list, max_length=100)
    sources: list[Source] = Field(default_factory=list, max_length=12)
    archived: bool = False

    @model_validator(mode="after")
    def check_tree(self):
        nodes = {item.id: item for item in self.sections}
        if len(nodes) != len(self.sections) or len({item.id for item in self.materials}) != len(self.materials):
            raise ValueError("章节或材料标识重复")
        for item in self.sections:
            seen, parent = {item.id}, item.parent_id
            while parent:
                if parent in seen or parent not in nodes or len(seen) > 8:
                    raise ValueError("章节不能循环引用，最多支持八层子章节")
                seen.add(parent)
                parent = nodes[parent].parent_id
        if any(not item.strip() or len(item) > 40 for item in self.tags):
            raise ValueError("每个标签应为 1–40 个字符")
        return self


class Option(Strict):
    id: str = Field(default_factory=identifier, pattern=r"^[a-f0-9]{32}$")
    body: dict = Field(default_factory=empty_doc)
    _doc = field_validator("body")(validate_doc)


class Blank(Strict):
    id: str = Field(default_factory=identifier, pattern=r"^[a-f0-9]{32}$")
    answers: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("answers")
    @classmethod
    def valid_answers(cls, values):
        if any(len(item) > 1000 or not has_supported_formula(item) for item in values):
            raise ValueError("请为每个空位填写参考答案，每项最多 1000 字")
        return values


class Answer(Strict):
    body: dict = Field(default_factory=empty_doc)
    explanation: dict = Field(default_factory=empty_doc)
    correct_options: list[str] = Field(default_factory=list, max_length=8)
    judgment: bool | None = None
    blanks: list[Blank] = Field(default_factory=list, max_length=20)
    _doc = field_validator("body", "explanation")(validate_doc)


class Question(Strict):
    kind: Kind = "written"
    body: dict = Field(default_factory=empty_doc)
    options: list[Option] = Field(default_factory=list, max_length=8)
    answer: Answer = Field(default_factory=Answer)
    section_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    material_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    tags: list[str] = Field(default_factory=list, max_length=12)
    difficulty: Literal["基础", "适中", "较难"] = "适中"
    sources: list[Source] = Field(default_factory=list, max_length=12)
    confirmed: bool = False
    included: bool = True
    _doc = field_validator("body")(validate_doc)

    @model_validator(mode="after")
    def valid_question(self):
        ids = [item.id for item in self.options]
        if len(set(ids)) != len(ids) or len({b.id for b in self.answer.blanks}) != len(self.answer.blanks):
            raise ValueError("选项或空位标识重复")
        keys = self.answer.correct_options
        if len(keys) != len(set(keys)) or set(keys) - set(ids):
            raise ValueError("正确答案必须对应当前选项")
        if self.kind not in {"single", "multiple"} and (self.options or keys):
            raise ValueError("当前题型不应包含选择题选项")
        if self.kind != "blank" and self.answer.blanks:
            raise ValueError("当前题型不应包含填空答案")
        if self.kind != "judge" and self.answer.judgment is not None:
            raise ValueError("当前题型不应包含判断答案")
        if any(not tag.strip() or len(tag) > 40 for tag in self.tags):
            raise ValueError("每个标签应为 1–40 个字符")
        if self.confirmed and self.problems():
            raise ValueError("；".join(self.problems()))
        return self

    def problems(self):
        issues = []
        if not plain(self.body).strip():
            issues.append("题干不能为空")
        if self.kind in {"single", "multiple"}:
            texts = [plain(option.body).strip() for option in self.options]
            if len(texts) < 2 or any(not value for value in texts):
                issues.append("至少填写两个非空选项")
            signatures = [(text, tuple(sorted(asset_ids(option.body)))) for text, option in zip(texts, self.options)]
            if len(set(signatures)) != len(signatures):
                issues.append("选项内容不能重复")
            if (self.kind == "single" and len(self.answer.correct_options) != 1) or (self.kind == "multiple" and len(self.answer.correct_options) < 2):
                issues.append("请设置正确选项，单选一道、多选至少两项")
        elif self.kind == "judge" and self.answer.judgment is None:
            issues.append("请选择正确或错误")
        elif self.kind == "blank" and (not self.answer.blanks or any(not any(a.strip() for a in b.answers) for b in self.answer.blanks)):
            issues.append("请填写空位及对应参考答案")
        elif self.kind == "written" and not plain(self.answer.body).strip():
            issues.append("请填写参考答案")
        return issues


class QuestionSave(Strict):
    revision: int = Field(ge=1)
    question: Question


class Revision(Strict):
    revision: int = Field(ge=1)


class Publish(Revision):
    request_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")
    class_codes: list[str] = Field(default_factory=list, max_length=200)


class Group(Strict):
    kind: Kind
    count: int = Field(ge=1, le=20)


class Generate(Strict):
    request_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")
    groups: list[Group] = Field(min_length=1, max_length=5)
    section_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    sources: list[Source] = Field(default_factory=list, max_length=12)
    knowledge: str = Field(default="", max_length=1000)
    difficulty: Literal["基础", "适中", "较难"] = "适中"
    language: Literal["中文", "英文", "中英双语"] = "中文"
    explanation: Literal["简明", "详细"] = "详细"
    instruction: str = Field(default="", max_length=3000)

    @model_validator(mode="after")
    def limits(self):
        if sum(group.count for group in self.groups) > 20 or len({g.kind for g in self.groups}) != len(self.groups):
            raise ValueError("每批最多 20 题，每种题型填写一次")
        return self


class Revise(Strict):
    revision: int = Field(ge=1)
    mode: Literal["改写题干", "优化干扰项", "调整难度", "补充答案与解析", "替换本题"] = "改写题干"
    instruction: str = Field(default="", max_length=3000)


class ImportExam(Strict):
    exam_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    question_ids: list[str] = Field(min_length=1, max_length=100)
    section_id: str | None = None


class Bulk(Strict):
    bank_revision: int = Field(ge=1)
    ids: list[str] = Field(min_length=1, max_length=200)
    action: Literal["move", "tags", "exclude", "include", "delete", "reorder"]
    section_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=12)
