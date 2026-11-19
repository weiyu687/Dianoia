import copy
import json
import os
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from docx import Document
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.auth import passwords
from app.db import engine
from app.migrate import migrate
from app.models import Resource, TeachingAssignment, User, identifier
from app.seed import main as seed
from app.question_banks.content import empty_doc, plain, text_doc
from app.question_banks.models import BankRelease, QuestionBank
from app.question_banks.schemas import Answer, Option, Question
from app.question_banks.worker import claim_job, process


def ok(response, status=200):
    assert response.status_code == status, (response.status_code, response.text[:2000])
    return response.json() if status != 204 else None


def body(bank, **changes):
    return {**{key: bank[key] for key in ("revision", "title", "description", "tags", "cover", "sections", "materials", "sources", "archived")}, **changes}


seed()
multiline = text_doc("计算如下：\n\\[\n\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}\n\\]\n再求行列式。")
assert multiline["content"][1]["content"][0]["type"] == "formula" and multiline["content"][1]["content"][0]["attrs"]["display"]
assert text_doc("| 量 | 公式 |\n| --- | --- |\n| 绝对值 | \\(\\left|x\\right|\\) |")['content'][0]['type'] == 'table'
with Session(engine) as db:
    baseline_users = db.scalar(select(func.count()).select_from(User))
migrate()
migrate()
with Session(engine) as db:
    assert db.scalar(select(func.count()).select_from(User)) == baseline_users

with TestClient(app, headers={"X-Dianoia-Client": "web"}) as client:
    assert client.get("/api/question-banks?course_id=1").status_code == 401
    profile = ok(client.post("/api/auth/login", json={"username": "teacher", "role": "teacher", "password": os.environ["DIANOIA_SEED_PASSWORD"]}))
    course_id = profile["courses"][0]["id"]
    bank = ok(client.post("/api/question-banks", json={"course_id": course_id, "title": "函数自主练习"}), 201)
    path = "/api/question-banks/" + bank["id"]
    parent = bank["sections"][0]["id"]
    child = {"id": identifier(), "title": "参数传递", "parent_id": parent}
    sections = [*bank["sections"], child]
    bank = ok(client.put(path, json=body(bank, sections=sections)))
    bad_sections = copy.deepcopy(sections)
    bad_sections[0]["parent_id"] = child["id"]
    ok(client.put(path, json=body(bank, sections=bad_sections)), 422)

    left, right = Option(body=text_doc("可复用的代码单元")), Option(body=text_doc("只能执行一次的语句"))
    question = Question(kind="single", section_id=child["id"], body=text_doc("函数的主要作用是？"), options=[left, right],
                        answer=Answer(correct_options=[left.id], explanation=text_doc("函数将重复的操作封装，便于复用。")))
    saved = ok(client.post(path + "/questions", json=question.model_dump()), 201)
    bank = ok(client.get(path))
    check = ok(client.get(path + "/preflight"))
    assert not check["ready"] and check["issues"][0]["question_id"] == saved["id"]
    publish_request = {"revision": bank["revision"], "request_key": uuid4().hex, "class_codes": []}
    ok(client.post(path + "/publish", json=publish_request), 422)
    question.confirmed = True
    saved = ok(client.put(path + "/questions/" + saved["id"], json={"revision": saved["revision"], "question": question.model_dump()}))
    ok(client.put(path + "/questions/" + saved["id"], json={"revision": 1, "question": question.model_dump()}), 409)
    filtered = ok(client.get(path + "/questions", params={"section_id": parent}))
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == saved["id"]
    bank = ok(client.get(path))
    publish_request["revision"] = bank["revision"]
    released = ok(client.post(path + "/publish", json=publish_request), 201)
    replay = ok(client.post(path + "/publish", json=publish_request), 201)
    assert released["release"]["id"] == replay["release"]["id"]
    release_id = released["release"]["id"]
    frozen = ok(client.get(path + "/preview", params={"release_id": release_id}))
    assert frozen["questions"][0]["question"]["answer"]["correct_options"] == [left.id]
    bank = released["bank"]
    assert bank["status"] == "published" and not bank["has_unpublished_changes"]
    bank = ok(client.put(path, json=body(bank, title="新版草稿")))
    assert bank["has_unpublished_changes"] and ok(client.get(path + "/preview", params={"release_id": release_id}))["title"] == "函数自主练习"
    ok(client.delete(path), 409)

    image = BytesIO()
    Image.new("RGB", (900, 900), "#55aa88").save(image, "PNG")
    cover = ok(client.post(path + "/assets", data={"kind": "cover", "x": .1, "y": .2, "width": .8, "height": .45}, files={"file": ("cover.png", image.getvalue())}), 201)
    assert (cover["width"], cover["height"]) == (1200, 675)
    assert client.get(cover["url"]).headers["content-type"] == "image/webp"
    bank = ok(client.get(path))
    bank = ok(client.put(path, json=body(bank, cover={**bank["cover"], "asset_id": cover["id"]})))
    assert client.get(path + "/cover").headers["content-type"] == "image/webp"
    assert "svg" in client.get(path + "/cover", params={"release_id": release_id}).headers["content-type"]

    math = Question(kind="written", body=text_doc(r"计算 \(\begin{bmatrix}1&2\\3&4\end{bmatrix}\) 的行列式。"),
                    answer=Answer(body=text_doc(r"\(1\times4-2\times3=-2\)"), explanation=text_doc("| 项 | 值 |\n| --- | --- |\n| 行列式 | -2 |")), confirmed=True)
    multiline = text_doc("推导如下：\n\\[\n\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}\n\\]\n结果为 -2。")
    assert multiline['content'][1]['content'][0]['type'] == 'formula'
    assert multiline['content'][1]['content'][0]['attrs']['display'] is True
    math_saved = ok(client.post(path + "/questions", json=math.model_dump()), 201)
    assert ok(client.get(path + "/questions/" + math_saved["id"]))["question"]["body"] == math.model_dump()["body"]
    unsafe = math.model_dump()
    unsafe["body"] = {"type": "doc", "content": [{"type": "html", "text": "<script>alert(1)</script>"}]}
    ok(client.post(path + "/questions", json=unsafe), 422)

    doc = Document()
    doc.add_paragraph("一、单项选择题")
    doc.add_paragraph("1. Python 中哪个关键字定义函数？")
    doc.add_paragraph("A. def")
    doc.add_paragraph("B. while")
    source = BytesIO(); doc.save(source)
    imported = ok(client.post(path + "/imports/word", files={"file": ("练习.docx", source.getvalue())}))
    assert imported["count"] == 1
    adoption = {"questions": [imported["candidates"][0]["question"]], "request_key": uuid4().hex}
    ok(client.post(path + "/imports/adopt", json=adoption), 201)
    count = ok(client.get(path))["question_count"]
    ok(client.post(path + "/imports/adopt", json=adoption), 201)
    assert ok(client.get(path))["question_count"] == count

    with Session(engine) as db:
        resource_id = identifier()
        db.add(Resource(id=resource_id, owner_id=profile["id"], course_id=course_id, title="函数讲义", filename="functions.pdf", extension="pdf", size=100,
                        pages=["Python 使用 def 定义函数。形参接收调用时传入的实参，return 返回结果。"], outline=[], page_count=1, status="ready"))
        db.commit()
    generation = {"request_key": uuid4().hex, "groups": [{"kind": "single", "count": 5}], "sources": [{"resource_id": resource_id, "start": 1, "end": 1}]}
    job = ok(client.post(path + "/jobs", json=generation), 202)
    assert ok(client.post(path + "/jobs", json=generation), 202)["id"] == job["id"]
    calls = [0]

    def model(system, prompt, structured=False):
        data = json.loads(prompt)
        assert "使用 def" in data["参考资料"]
        if calls[0] == 1:
            calls[0] += 1
            raise HTTPException(502, "模拟第二批失败")
        result = []
        for i, kind in enumerate(data["本批题型顺序"]):
            result.append({"kind": kind, "stem": f"生成题目 {calls[0]}-{i}：函数是什么？", "options": ["代码单元", "变量名"], "answer": "A",
                           "explanation": "参考讲义，函数是可调用的代码单元。", "sources": generation["sources"]})
        calls[0] += 1
        return json.dumps({"questions": result}, ensure_ascii=False)

    with patch("app.question_banks.generation.generate", model):
        process(claim_job())
        result = next(j for j in ok(client.get(path))["jobs"] if j["id"] == job["id"])
        assert result["status"] == "failed" and result["completed"] == 3, result
        ok(client.post(path + "/jobs/" + job["id"] + "/retry"))
        process(claim_job())
        result = next(j for j in ok(client.get(path))["jobs"] if j["id"] == job["id"])
        assert result["status"] == "succeeded" and result["completed"] == 5, result
    assert ok(client.get(path))["question_count"] == count + 5

    request_key = uuid4().hex
    unique = Question(kind="written", body=text_doc("说明默认参数的作用"), answer=Answer(body=text_doc("可省略调用中对应的实参。"))).model_dump()
    first = ok(client.post(path + "/questions", json=unique, headers={"Idempotency-Key": request_key}), 201)
    again = ok(client.post(path + "/questions", json=unique, headers={"Idempotency-Key": request_key}), 201)
    assert first["id"] == again["id"]

    bank = ok(client.get(path))
    copied = ok(client.post(path + "/copy", json={"request_key": "copy-" + uuid4().hex}), 201)
    assert copied["release"] is None and copied["question_count"] == bank["question_count"] and copied["cover"]["asset_id"] != bank["cover"]["asset_id"]
    assert client.get('/api/question-banks/assets/'+copied['cover']['asset_id']+'?thumbnail=true').status_code == 200
    ok(client.post(path + "/withdraw", json={"revision": bank["revision"], "release_id": release_id}))
    assert ok(client.get(path))["status"] == "offline"
    bank = ok(client.get(path))
    archived = ok(client.patch(path+'/status', json={'revision':bank['revision'],'archived':True}))
    assert archived['status'] == 'archived'
    ok(client.patch(path+'/status', json={'revision':archived['revision'],'archived':False}))

    from app.question_banks.tools import make_tools
    def run_tool(operation):
        with Session(engine) as db:
            return operation(db, db.get(User, profile['id']))
    tools, links = make_tools(run_tool, course_id)
    functions = {tool.__name__:tool for tool in tools}
    draft = functions['create_question_bank_draft']('Agent 自主练习草稿')
    assert functions['create_question_bank_draft']('Agent 自主练习草稿')['id'] == draft['id']
    payload = math.model_dump()
    agent_saved = functions['save_question_bank_question'](draft['id'], payload)
    assert agent_saved['question']['confirmed'] is False
    assert functions['save_question_bank_question'](draft['id'], payload)['id'] == agent_saved['id']
    assert not any('publish' in name for name in functions)

    with Session(engine) as db:
        other = User(username="other-bank-teacher", name="另一位教师", role="teacher", password_hash=passwords.hash(os.environ["DIANOIA_SEED_PASSWORD"]))
        db.add(other);db.flush();db.add(TeachingAssignment(teacher_id=other.id, course_id=course_id));db.commit()
    ok(client.post("/api/auth/login", json={"username": "other-bank-teacher", "role": "teacher", "password": os.environ["DIANOIA_SEED_PASSWORD"]}))
    assert ok(client.get("/api/question-banks?course_id=" + str(course_id))) == []
    ok(client.get(path), 404)
    ok(client.get(cover["url"]), 404)
    ok(client.get(path + "/preview", params={"release_id": release_id}), 404)
print("Question bank integration passed: versions, authorization, imports, formulas, cover and retry")
