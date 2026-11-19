"""Agent tools share the same owner/course checks and authoring services as pages."""
import json
from threading import Lock

from fastapi import HTTPException

from ..models import identifier
from .router import generate_questions, get_bank, list_banks, list_questions, new_bank
from .schemas import BankCreate, Generate, Question
from .service import create_question, owned, question_owned, question_view, save_question


def make_tools(run_tool, course_id):
    links, drafts, jobs, writes = {}, {}, {}, {}
    lock = Lock()

    def scoped(db, teacher, bank_id):
        bank = owned(db, teacher, bank_id)
        if bank.course_id != course_id:
            raise HTTPException(404, "当前课程没有该题库")
        return bank

    def find_question_banks() -> list:
        """列出当前课程里自己的在线题库：ID、名称、题量与发布状态。"""
        return run_tool(lambda db, teacher: [{k: b[k] for k in ("id", "title", "question_count", "status", "revision")}
                                            for b in list_banks(course_id, db, teacher)])

    def question_bank_contents(bank_id: str, question_id: str = "", page: int = 1) -> dict:
        """读取当前课程题库的章节与题目摘要，或按 question_id 读取完整题干、答案与解析。page 从1开始，每页30题。"""
        def read(db, teacher):
            bank = scoped(db, teacher, bank_id)
            if question_id:
                return question_view(db, question_owned(db, bank, question_id))
            if not 1 <= page <= 1000:
                raise HTTPException(422, "请检查题目页码")
            return {"id": bank.id, "title": bank.title, "sections": bank.sections, "sources": bank.sources,
                    "questions": list_questions(bank_id, db, teacher, page, 30, None, None, "", False),
                    "editor": f"/#/question-banks/{bank_id}"}
        return run_tool(read)

    def create_question_bank_draft(title: str) -> dict:
        """明确要求时，在当前课程创建带默认封面的自主练习题库草稿。不发布、不设置成绩。"""
        try:
            data = BankCreate(course_id=course_id, title=title)
        except ValueError:
            return {"error": "题库名称应为1至160个字符"}
        def create(db, teacher):
            with lock:
                if title not in drafts:
                    item = new_bank(data, db, teacher)
                    drafts[title] = {"id": item["id"], "title": item["title"], "editor": f"/#/question-banks/{item['id']}"}
                    links[item["id"]] = drafts[title]
                return drafts[title]
        return run_tool(create)

    def generate_question_bank_questions(bank_id: str, groups: list[dict], sources: list[dict] | None = None,
                                         instruction: str = "", knowledge: str = "", difficulty: str = "适中") -> dict:
        """为题库提交异步生成任务。groups项是kind(single/multiple/judge/blank/written)、count；总量最多20题。
        sources项为resource_id,start,end，页码从1开始。生成包括答案与解析，仅保存待确认草稿。
        """
        payload = {"groups": groups, "sources": sources or [], "instruction": instruction, "knowledge": knowledge, "difficulty": difficulty}
        key = bank_id + json.dumps(payload, sort_keys=True)
        with lock:
            request_key = jobs.setdefault(key, identifier())
        try:
            data = Generate(request_key=request_key, **payload)
        except ValueError:
            return {"error": "请检查题型、数量、难度与资料页码，每批最多20题"}
        def create(db, teacher):
            bank = scoped(db, teacher, bank_id)
            result = generate_questions(bank_id, data, db, teacher)
            links[bank_id] = {"id": bank.id, "title": bank.title, "editor": f"/#/question-banks/{bank_id}"}
            return {**result, "editor": links[bank_id]["editor"], "notice": "后台生成后需教师核对，不代表已发布"}
        return run_tool(create)

    def save_question_bank_question(bank_id: str, question: dict, question_id: str = "", revision: int = 0) -> dict:
        """新建或更新自主练习题目草稿。question采用受控富文本JSON，字段见Skill。更新需提供读取时的revision。
        所有Agent写入均待教师确认；不能直接发布或标记已审核。
        """
        try:
            data = Question.model_validate({**question, "confirmed": False})
        except ValueError:
            return {"error": "题目结构不正确，请按在线题库Skill中的字段与JSON文档结构填写"}
        def write(db, teacher):
            bank = scoped(db, teacher, bank_id)
            fingerprint = bank_id + data.model_dump_json()
            if not question_id and fingerprint in writes:
                return writes[fingerprint]
            if question_id:
                row = question_owned(db, bank, question_id)
                save_question(db, teacher, bank, row, revision, data)
            else:
                row = create_question(db, teacher, bank, data)
            db.commit()
            links[bank_id] = {"id": bank.id, "title": bank.title, "editor": f"/#/question-banks/{bank_id}"}
            result = question_view(db, row) | {"editor": links[bank_id]["editor"]}
            if not question_id:
                writes[fingerprint] = result
            return result
        return run_tool(write)

    def question_bank_generation_status(bank_id: str) -> dict:
        """查看指定题库的生成进度、失败原因及已完成题数。"""
        def read(db, teacher):
            scoped(db, teacher, bank_id)
            value = get_bank(bank_id, db, teacher)
            return {"id": bank_id, "jobs": value["jobs"], "question_count": value["question_count"]}
        return run_tool(read)

    return [find_question_banks, question_bank_contents, create_question_bank_draft, generate_question_bank_questions,
            save_question_bank_question, question_bank_generation_status], links
