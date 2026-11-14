import json
import os
import unittest
from base64 import b64decode
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pptx import Presentation
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.orm import Session


class WorkflowTest(unittest.TestCase):
    def test_import_authorization_documents_and_writing(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "DIANOIA_DATA_DIR": directory,
            "DIANOIA_DATABASE_URL": f"sqlite:///{directory}/workflow.db",
            "DIANOIA_SEED_PASSWORD": "Synthetic-test-password!",
            "DIANOIA_SECURE_COOKIE": "false",
        }):
            from app.admin import SHEETS
            from app.db import engine
            from app.documents import FILES
            from app.main import app
            from app.models import Resource, identifier
            from app.seed import main as seed

            seed()
            with TestClient(app, headers={"X-Dianoia-Client": "web"}) as client:
                password = os.environ["DIANOIA_SEED_PASSWORD"]

                def login(username, role, expected=200, secret=password):
                    response = client.post("/api/auth/login", json={
                        "username": username, "password": secret, "role": role,
                    })
                    self.assertEqual(response.status_code, expected, response.text)
                    return response.json()

                self.assertEqual(client.get("/api/auth/me").status_code, 401)
                login("teacher", "admin", 401)
                login("admin", "admin")
                workbook = Workbook()
                workbook.remove(workbook.active)
                rows = {
                    "教师": [("T02", "虚拟教师")],
                    "学生": [("S02", "虚拟学生")],
                    "课程": [("DB102", "虚拟课程")],
                    "教学班": [("C02", "二班", "DB102")],
                    "任课": [("T02", "DB102")],
                    "名单": [("S02", "C02")],
                }
                for name, fields in SHEETS.items():
                    sheet = workbook.create_sheet(name)
                    sheet.append(fields)
                    for row in rows[name]:
                        sheet.append(row)
                contents = BytesIO()
                workbook.save(contents)

                def upload_sheet(apply):
                    response = client.post("/api/admin/import", data={"apply": str(apply).lower()}, files={
                        "file": ("sample.xlsx", contents.getvalue()),
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    return response.json()

                preview = upload_sheet(False)
                self.assertFalse(preview["applied"])
                self.assertEqual(preview["errors"], [])
                self.assertTrue(upload_sheet(True)["applied"])
                self.assertEqual(upload_sheet(True)["rows"]["任课"]["unchanged"], 1)
                accounts = client.get("/api/admin/overview").json()["accounts"]
                second = next(account for account in accounts if account["username"] == "t02")
                self.assertFalse(second["enabled"])
                client.put(f"/api/admin/teachers/{second['id']}/account", json={"enabled": True, "password": password}).raise_for_status()

                teacher = login("teacher", "teacher")
                course = teacher["courses"][0]["id"]
                self.assertEqual(client.get("/api/admin/overview").status_code, 403)
                file = BytesIO()
                canvas = Canvas(file)
                canvas.bookmarkPage("first")
                canvas.addOutlineEntry("Transactions", "first")
                canvas.drawString(40, 500, "Transactions have clear boundaries.")
                canvas.showPage()
                canvas.bookmarkPage("isolation")
                canvas.addOutlineEntry("Isolation", "isolation", level=1)
                canvas.bookmarkPage("unnamed")
                canvas.addOutlineEntry("", "unnamed", level=1)
                canvas.bookmarkPage("example")
                canvas.addOutlineEntry("Shared example", "example", level=2)
                canvas.bookmarkPage("next")
                canvas.addOutlineEntry("Next chapter", "next")
                canvas.drawString(40, 500, "Repeatable read is an isolation level.")
                canvas.save()
                self.check_word_preview(client, teacher, course, file.getvalue(), engine, FILES, Resource, identifier)
                resource = client.post("/api/resources", data={"course_id": course}, files={
                    "file": ("transactions.pdf", file.getvalue(), "application/pdf"),
                }).raise_for_status().json()
                self.assertEqual(resource["outline"][0]["children"][0]["start"], 2)
                self.assertEqual([node["title"] for node in resource["outline"][0]["children"]], ["Isolation", "Shared example"])
                self.assertEqual(resource["outline"][0]["end"], 2)
                self.assertEqual(resource["outline"][1]["start"], 2)
                resource_path = f"/api/resources/{resource['id']}"
                stale_outline = resource["outline"]
                stale_outline[0]["end"] = 1
                invalid = client.patch(resource_path, json={
                    "title": "事务讲义", "outline": stale_outline, "status": "ready",
                })
                self.assertEqual(invalid.status_code, 422)
                shared_example = stale_outline[0]["children"].pop()
                stale_outline[0]["children"].append({"title": "", "start": 2, "end": 2, "children": [shared_example]})
                stale_outline[0]["end"] = 2
                blank = client.patch(resource_path, json={"title": "事务讲义", "outline": stale_outline})
                self.assertEqual(blank.json()["detail"], "请填写所有章节名称")
                stale_outline[0]["end"] = 1
                with Session(engine) as db:
                    db.get(Resource, resource["id"]).outline = stale_outline
                    db.commit()
                self.assertEqual(client.get(resource_path).json()["outline"][0]["end"], 2)
                saved = client.patch(resource_path, json={
                    "title": "事务讲义", "outline": stale_outline, "status": "ready",
                }).raise_for_status().json()
                self.assertEqual(saved["outline"][0]["end"], 2)
                self.assertEqual(saved["outline"][0]["children"][1]["title"], "Shared example")
                client.get(f"/api/resources/{resource['id']}/preview").raise_for_status()
                plan = client.post("/api/lessons", json={
                    "course_id": course, "title": "事务教案",
                    "sources": [{"resource_id": resource["id"], "start": 2, "end": 2}],
                }).raise_for_status().json()
                route = f"/api/lessons/{plan['id']}"
                plan["sections"][0]["content"] = "教学对象：计算机专业二年级学生。"
                updated = client.put(route, json=plan).raise_for_status().json()
                self.assertEqual(updated["revision"], 2)
                self.assertEqual(client.put(route, json=plan).status_code, 409)
                docx = client.get(f"{route}/export/docx").raise_for_status()
                pdf = client.get(f"{route}/export/pdf?inline=true").raise_for_status()
                self.assertTrue(docx.content.startswith(b"PK"))
                self.assertIn("计算机", PdfReader(BytesIO(pdf.content)).pages[0].extract_text())

                with patch("app.ai.generate", return_value="安排并发实验。") as model:
                    suggestion = client.post("/api/ai/writing", json={
                        "lesson_id": plan["id"], "section": "授课信息", "mode": "continue",
                        "before": "教学对象", "after": "",
                    }).raise_for_status().json()
                    self.assertEqual(suggestion["text"], "安排并发实验。")
                    self.assertEqual(suggestion["blocks"], [{"type": "paragraph", "text": "安排并发实验。"}])
                    self.assertIn("教学对象", model.call_args.args[1])
                    reference = json.loads(model.call_args.args[1])["资料"]
                    self.assertIn("Repeatable read", reference)
                    self.assertNotIn("Transactions have clear boundaries", reference)
                    self.assertEqual(suggestion["sources_used"], [{"title": "事务讲义", "pages": [2]}])
                    self.assertEqual(client.get(route).json()["revision"], 2)

                with patch("app.ai.generate", return_value="数据安全是目前函数设计的重要要求。下一段的已有文字"):
                    suggestion = client.post("/api/ai/writing", json={
                        "lesson_id": plan["id"], "section": "正文", "mode": "continue",
                        "before": "数据安全是目前", "after": "下一段的已有文字",
                    }).raise_for_status().json()
                self.assertEqual(suggestion["text"], "函数设计的重要要求。")

                private_template = self.check_lesson_templates(client, course, route)
                presentation, slide_template = self.check_presentations(client, course, resource["id"])
                mind_map, map_template = self.check_mind_maps(client, course, resource["id"])
                exam = self.check_exams(client, course)
                second_teacher = login("t02", "teacher")
                self.assertNotEqual(second_teacher["courses"][0]["id"], course)
                self.assertEqual(client.get(route).status_code, 404)
                self.assertEqual(client.get(f"/api/resources/{resource['id']}/file").status_code, 404)
                self.assertEqual(client.get("/api/lesson-templates").json(), [])
                self.assertEqual(client.get(f"/api/lesson-templates/{private_template}/preview").status_code, 404)
                self.assertEqual(client.get(f"/api/mind-maps/{mind_map}").status_code, 404)
                self.assertEqual(client.get(f"/api/mind-map-templates/{map_template}").status_code, 404)
                self.assertEqual(client.get(f"/api/exams/{exam}").status_code, 404)
                self.assertEqual(client.get(f"/api/presentations/{presentation}").status_code, 404)
                self.assertEqual(client.get(f"/api/presentation-templates/{slide_template}").status_code, 404)
                self.assertEqual(client.post("/api/lessons", json={
                    "course_id": second_teacher["courses"][0]["id"], "title": "未授权模板",
                    "template_id": private_template,
                }).status_code, 404)

    def check_presentations(self, client, course, resource_id):
        from app.presentation_document import Deck
        from app.presentation_templates import builtin, template_keys

        decks, templates = "/api/presentations", "/api/presentation-templates"
        for key in template_keys():
            Deck.model_validate(builtin(key)["document"])
        self.assertEqual(len(client.get(templates).raise_for_status().json()), len(template_keys()))
        source = {"resource_id": resource_id, "start": 2, "end": 2}
        outline = [{"title": title} for title in ("隔离级别", "概念", "实验")]
        pages = [{"layout": "body", "points": ["阅读实验记录"], "notes": "比较事务隔离效果",
                  "citations": [source], **entry} for entry in outline]
        pages[1].update(layout="table", table=[["隔离级别", "特点"], ["Repeatable read", "同一事务内可重复读取"]])
        pages[2].update(layout="code", code="def run():\n    return 42")
        data = {"course_id": course, "title": "事务实训", "template_id": "practice", "sources": [source], "page_count": 3}
        with patch("app.presentations.generate", side_effect=[json.dumps({"pages": outline}), json.dumps({"pages": pages})]) as model:
            data["outline"] = client.post(f"{decks}/outline", json=data).raise_for_status().json()
            deck = client.post(f"{decks}/generate", json=data).raise_for_status().json()
            for call in model.call_args_list:
                self.assertIn("Repeatable read", call.args[1])
                self.assertNotIn("Transactions have clear boundaries", call.args[1])
        detail = f"{decks}/{deck['id']}"
        first = deck["document"]["slides"][0]
        title = next(item for item in first["elements"] if item["role"] == "title")
        self.assertEqual(title["text"], "隔离级别")
        self.assertEqual(first["citations"], [source])
        with patch("app.presentations.generate", return_value="补充一个实验步骤") as model:
            candidate = client.post(f"{detail}/suggest", json={
                "revision": deck["revision"], "slide_id": first["id"], "mode": "text", "element_id": title["id"],
            }).raise_for_status().json()
            self.assertIn("Repeatable read", model.call_args.args[1])
        self.assertEqual(candidate["text"], "补充一个实验步骤")
        self.assertEqual(client.get(detail).json()["revision"], 1)
        title["text"] = candidate["text"]
        matrix = r"\begin{bmatrix}1&2\\3&4\end{bmatrix}+\frac{1}{x}"
        self.assertEqual(client.post(f"{detail}/formula", json={"latex": matrix}).status_code, 200)
        self.assertEqual(client.post(f"{detail}/formula", json={"latex": r"\unknown{a}"}).status_code, 422)
        deck["document"]["slides"][2]["elements"].append({"kind": "formula", "latex": matrix})
        saved = client.put(detail, json=deck).raise_for_status().json()
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(client.put(detail, json=deck).status_code, 409)
        template = client.post(f"{detail}/template", json={
            "revision": saved["revision"], "title": "实训样式", "layout_only": True,
        }).raise_for_status().json()
        new = client.post(decks, json={
            "course_id": course, "title": "复用实训版式", "template_id": template["id"],
        }).raise_for_status().json()
        self.assertEqual(new["document"]["sources"], [])
        self.assertTrue(all(not slide["citations"] for slide in new["document"]["slides"]))
        pptx = Presentation(BytesIO(client.get(f"{detail}/export/pptx").raise_for_status().content))
        self.assertEqual(len(pptx.slides), 3)
        self.assertEqual(pptx.slides[0].shapes[1].text, candidate["text"])
        self.assertEqual(pptx.slides[0].notes_slide.notes_text_frame.text, first["notes"])
        table = next(shape.table for shape in pptx.slides[1].shapes if shape.has_table)
        self.assertEqual(table.cell(1, 0).text, "Repeatable read")
        self.assertTrue(any(shape.has_text_frame and "    return 42" in shape.text for shape in pptx.slides[2].shapes))
        self.assertIn("a14:m", pptx.slides[2].shapes[-1]._element.xml)
        return deck["id"], template["id"]

    def check_mind_maps(self, client, course, resource_id):
        maps, templates = "/api/mind-maps", "/api/mind-map-templates"
        source = {"resource_id": resource_id, "start": 2, "end": 2}
        self.assertGreaterEqual(len(client.get(templates).raise_for_status().json()["builtin"]), 8)

        def model(_, prompt, structured):
            self.assertTrue(structured)
            pages = json.loads(prompt)["资料"]
            self.assertEqual([page["页码"] for page in pages], [2])
            self.assertIn("Repeatable read", pages[0]["正文"])
            return '```json\n' + json.dumps({"root": {"text": "中心主题", "children": [
                {"text": "隔离级别", "pages": ["P1", "P1", "P2"], "children": [{"text": "可重复读"}]},
            ]}}) + '\n```'

        with patch("app.mind_maps.generate", side_effect=model):
            row = client.post(f"{maps}/generate", json={
                "course_id": course, "title": "数据库事务", "sources": [source],
            }).raise_for_status().json()
        path = f"{maps}/{row['id']}"
        document = row["document"]
        branch = document["root"]["children"][0]
        self.assertEqual(branch["sources"], [source])
        self.assertEqual(branch["children"][0]["text"], "可重复读")
        branch["style"] = {"shape": "diamond"}
        child_id = branch["children"][0]["id"]
        branch.update({
            "labels": ["重点"], "summary": "事务隔离", "frame": {"group_id": "frame", "text": "专题"},
            "lines": [{"target": child_id, "text": "示例"}, {"target": "deleted"}],
            "node_links": [child_id, child_id, "deleted"],
            "formula": r"\frac{a}{b}", "table": {"rows": [["模式", "现象"], ["隔离", "可重复读"]]},
            "code": "select * from lessons",
        })
        payload = {"title": row["title"], "revision": row["revision"], "document": document}
        branch["hyperlink"] = {"url": "javascript:alert(1)"}
        self.assertEqual(client.put(path, json=payload).status_code, 422)
        branch["hyperlink"] = {"url": "https://example.com/docs", "label": "教程 <原文>"}
        updated = client.put(path, json=payload).raise_for_status().json()
        self.assertEqual(updated["revision"], 2)
        updated_branch = updated["document"]["root"]["children"][0]
        self.assertEqual(updated_branch["lines"], [{"target": child_id, "text": "示例"}])
        self.assertEqual(updated_branch["node_links"], [child_id])
        self.assertEqual(updated_branch["hyperlink"], branch["hyperlink"])
        self.assertEqual(updated_branch["table"], branch["table"])
        self.assertEqual(client.put(path, json=payload).status_code, 409)
        key = {"Idempotency-Key": str(uuid4())}
        copy = client.post(f"{path}/copy", headers=key).raise_for_status().json()
        self.assertEqual(client.post(f"{path}/copy", headers=key).raise_for_status().json()["id"], copy["id"])
        template = client.post(templates, json={"title": "个人结构", "map_id": row["id"]}).raise_for_status().json()
        self.assertEqual(template["document"]["sources"], [])
        self.assertEqual(template["document"]["root"]["children"][0]["sources"], [])
        derived = client.post(maps, json={
            "course_id": course, "title": "模板副本", "template_id": template["id"],
        }).raise_for_status().json()
        self.assertEqual(derived["document"]["root"]["children"][0]["style"]["shape"], "diamond")
        self.assertEqual(derived["document"]["root"]["children"][0]["summary"], branch["summary"])
        self.assertEqual(derived["document"]["root"]["text"], "模板副本")
        self.assertEqual(client.get(f"{templates}/{template['id']}").json()["document"]["root"]["text"], "数据库事务")
        client.delete(f"/api/resources/{resource_id}").raise_for_status()
        payload.update(revision=updated["revision"], title="已更新的导图")
        self.assertEqual(client.put(path, json=payload).status_code, 200)
        return row["id"], template["id"]

    def check_exams(self, client, course):
        blank = client.post("/api/exams", json={"course_id": course, "title": "默认空白卷",
                                              "class_code": "DB101-01"}).raise_for_status().json()
        blank_route = f"/api/exams/{blank['id']}"
        blank_doc = Document(BytesIO(client.get(f"{blank_route}/document").raise_for_status().content))
        self.assertIn("计算机一班", blank_doc.tables[0].cell(2, 3).text)
        self.assertEqual(blank_doc.tables[1].cell(1, 0).text, "得　分")
        self.assertEqual(blank_doc.tables[2].cell(1, 0).text, "评分人")
        self.assertEqual(blank_doc.paragraphs[-1].text, "")
        self.assertFalse(client.get(f"{blank_route}/sheet").raise_for_status().json()["can_build"])
        self.assertEqual(client.post("/api/exams", json={"course_id": course, "title": "非法班级",
                                                       "class_code": "unrelated"}).status_code, 422)
        table_only = Document()
        table_only.add_table(rows=1, cols=1).cell(0, 0).text = "卷头信息"
        table_file = BytesIO()
        table_only.save(table_file)
        table_exam = client.post("/api/exams/import", data={"course_id": course, "title": "表格收尾"}, files={
            "file": ("exam.docx", table_file.getvalue()),
        }).raise_for_status().json()
        imported_doc = Document(BytesIO(client.get(f"/api/exams/{table_exam['id']}/document").raise_for_status().content))
        self.assertEqual(imported_doc.tables[0].cell(0, 0).text, "卷头信息")
        self.assertEqual([p.text for p in imported_doc.paragraphs], [""])
        original = Document()
        original.add_paragraph("某课程试卷")
        original.sections[0].header.paragraphs[0].text = "保留的页眉"
        original.add_heading("一、解答题", 1)
        first = original.add_paragraph()
        first.add_run("1. 原题（5分）").bold = True
        original.add_paragraph("2. 相邻题（10分）")
        original.add_paragraph("参考答案：原卷答案")
        data = BytesIO()
        original.save(data)
        row = client.post("/api/exams/import", data={"course_id": course, "title": "原卷改编"}, files={
            "file": ("exam.docx", data.getvalue()),
        }).raise_for_status().json()
        self.assertEqual(len(row["questions"]), 2)
        self.assertTrue(row["answer_markers"])
        route = f"/api/exams/{row['id']}"
        key = row["questions"][0]["id"]
        self.assertEqual(client.get(f"{route}/export/paper/docx?inline=true").status_code, 422)
        self.assertEqual(client.put(f"{route}/review", json={"revision": row["revision"], "reviewed": True}).status_code, 422)
        row = client.put(f"{route}/questions/{key}", json={
            "revision": row["revision"], "kind": "written", "points": 5,
        }).raise_for_status().json()
        replacement = {"kind": "written", "stem": "请编写函数", "points": 25,
                       "answer": "单独保存的答案", "tags": ["编程"]}
        with patch("app.exams.generate", return_value=json.dumps(replacement)):
            candidate = client.post(f"{route}/questions/{key}/revise", json={
                "revision": row["revision"], "mode": "replace",
            }).raise_for_status().json()
        self.assertEqual(candidate["question"]["points"], 5)
        updated = client.post(f"{route}/questions/{key}/adopt", json={
            "revision": candidate["revision"], "question": candidate["question"],
        }).raise_for_status().json()
        self.assertEqual(updated["questions"][1]["text"], "2. 相邻题（10分）")
        self.assertEqual(updated["questions"][0]["id"], key)
        self.assertEqual(client.post(f"{route}/questions/{key}/adopt", json={
            "revision": candidate["revision"], "question": candidate["question"],
        }).status_code, 409)
        paper = Document(BytesIO(client.get(f"{route}/document").raise_for_status().content))
        self.assertEqual(paper.sections[0].header.paragraphs[0].text, "保留的页眉")
        self.assertEqual(paper.paragraphs[2].text, "1. 请编写函数（5分）")
        self.assertTrue(paper.paragraphs[2].runs[0].bold)
        self.assertFalse(any(replacement["answer"] in p.text for p in paper.paragraphs))
        answers = Document(BytesIO(client.get(f"{route}/export/answers/docx").raise_for_status().content))
        self.assertTrue(any(replacement["answer"] in p.text for p in answers.paragraphs))
        answers.add_paragraph("教师自定义评分说明")
        edited = BytesIO()
        answers.save(edited)
        answer_state = client.put(f"{route}/answers/document", data={"revision": updated["revision"]}, files={
            "file": ("answers.docx", edited.getvalue()),
        }).raise_for_status().json()
        self.assertTrue(answer_state["saved"])
        self.assertFalse(answer_state["stale"])
        self.assertEqual(client.get(f"{route}/export/answers/docx").raise_for_status().content, edited.getvalue())
        self.assertNotEqual(client.get(f"{route}/document").raise_for_status().content, edited.getvalue())
        client.patch(route, json={"title": "更新后的试卷"}).raise_for_status()
        self.assertTrue(client.get(f"{route}/answers").raise_for_status().json()["stale"])
        self.assertEqual(client.get(f"{route}/export/answers/docx").raise_for_status().content, edited.getvalue())
        self.check_answer_sheet(client, course)
        return row["id"]

    def check_answer_sheet(self, client, course):
        from app.exam_tex import text as latex_text

        payload = {"course_id": course, "title": "作答区验收", "class_code": "DB101-01",
                   "groups": [{"kind": kind, "count": 1, "points": 5} for kind in ("single", "blank", "written")]}
        questions = [
            {"kind": "single", "stem": "比较数值", "options": ["甲", "乙", "丙"], "answer": "B", "points": 5},
            {"kind": "blank", "stem": "填写 ____ 与 ____", "answer": "教师答案填空", "points": 5},
            {"kind": "written", "stem": r"计算 $\frac{1}{2}$，输出结果", "answer": "教师答案主观题",
             "points": 5, "tags": ["编程"]},
        ]
        with patch("app.exams.generate", return_value=json.dumps({"questions": questions})):
            row = client.post("/api/exams/generate", json=payload).raise_for_status().json()
        path = f"/api/exams/{row['id']}"
        state = client.get(f"{path}/sheet").raise_for_status().json()
        self.assertTrue(state["can_build"])
        self.assertEqual(state["questions"][0]["option_count"], 3)
        self.assertEqual(state["questions"][1]["area"]["blanks"], 2)
        areas = {q["id"]: q["area"] for q in state["questions"]}
        areas[state["questions"][2]["id"]].update(lines=8, line_mm=10, width_mm=120)
        body = {"revision": state["revision"], "areas": areas}
        generated = client.put(f"{path}/sheet", json=body).raise_for_status().json()
        sheet = client.get(f"{path}/export/sheet/docx").raise_for_status().content
        doc = Document(BytesIO(sheet))
        self.assertEqual([c.text for c in doc.tables[1].rows[0].cells], ["1.", "［A］", "［B］", "［C］"])
        self.assertAlmostEqual(doc.tables[-1].rows[0].height.mm, 80, delta=0.1)
        self.assertNotIn("教师答案", "".join(p.text for p in doc.paragraphs))
        tex = client.get(f"{path}/export/paper/tex").raise_for_status().content.decode()
        self.assertIn(r"\(\frac{1}{2}\)", tex)
        self.assertIn(r"\textbackslash{}input\{example\}", latex_text(r"$\input{example}$"))
        self.assertNotIn("教师答案", tex)
        tex_sheet = client.get(f"{path}/export/sheet/tex").raise_for_status().content.decode()
        self.assertIn("80mm", tex_sheet)
        self.assertNotIn("教师答案", tex_sheet)
        self.assertIn("教师答案主观题", client.get(f"{path}/export/answers/tex").raise_for_status().content.decode())
        self.check_exam_formulas(client, course)
        doc.add_paragraph("补充作答须知")
        changed = BytesIO()
        doc.save(changed)
        body["revision"] = generated["revision"]
        saved = client.put(f"{path}/sheet/document", data={"revision": generated["revision"]}, files={
            "file": ("sheet.docx", changed.getvalue()),
        }).raise_for_status().json()
        self.assertTrue(saved["edited"])
        self.assertFalse(saved["stale"])
        self.assertEqual(client.get(f"{path}/export/sheet/docx").raise_for_status().content, changed.getvalue())
        body["revision"] = saved["revision"]
        self.assertEqual(client.put(f"{path}/sheet", json=body).status_code, 409)
        copy = client.post(f"{path}/copy").raise_for_status().json()
        copied = client.get(f"/api/exams/{copy['id']}/export/sheet/docx").raise_for_status().content
        self.assertEqual(copied, changed.getvalue())
        client.patch(path, json={"title": "卷头已调整"}).raise_for_status()
        self.assertTrue(client.get(f"{path}/sheet").raise_for_status().json()["stale"])
        self.assertEqual(client.get(f"{path}/export/sheet/tex").status_code, 409)
        latest = client.get(f"{path}/sheet").raise_for_status().json()
        rebuilt = client.put(f"{path}/sheet", json=body | {
            "revision": latest["revision"], "replace_edits": True,
        }).raise_for_status().json()
        self.assertFalse(rebuilt["edited"])
        self.assertFalse(rebuilt["stale"])

    def check_exam_formulas(self, client, course):
        from app.exam_math import SOURCE, equation_source

        calculus = r"\int_0^1\frac{1}{1+x^2}\,dx"
        matrix = r"\begin{bmatrix}1&2\\3&4\end{bmatrix}"
        derivation = r"\begin{aligned}\det A&=4-6\\&=-2\end{aligned}"
        for latex in (calculus, matrix, derivation):
            result = client.post("/api/exams/equation", json={"latex": latex}).raise_for_status().json()["omml"]
            self.assertIn("<m:oMath", result)
        self.assertEqual(client.post("/api/exams/equation", json={"latex": r"\input{test}"}).status_code, 422)
        self.assertEqual(client.post("/api/exams/equation", json={"latex": r"\frac{1}"}).status_code, 422)
        word = Document()
        first = word.add_paragraph("1. 求 ")
        first.add_run(r"\(\int_0^1")
        first.add_run(r"\frac{1}{1+x^2}\,dx\)（4分）").bold = True
        word.add_paragraph(f"2. 求 {matrix.join(['$', '$'])} 的行列式（6分）")
        buf = BytesIO()
        word.save(buf)
        exam = client.post("/api/exams/import", data={"course_id": course}, files={
            "file": ("calculus.docx", buf.getvalue()),
        }).raise_for_status().json()
        path = f"/api/exams/{exam['id']}"
        doc = Document(BytesIO(client.get(f"{path}/document").raise_for_status().content))
        equations = list(doc.element.body.iter(qn("m:oMath")))
        self.assertEqual([equation_source(node) for node in equations], [calculus, matrix])
        self.assertIsNotNone(equations[1].find(".//" + qn("m:m")))
        self.assertTrue(doc.paragraphs[0].runs[-1].bold)
        generated = [
            {"kind": "written", "points": 10, "stem": f"求 \\({calculus}\\)", "answer": r"\(\frac{\pi}{4}\)"},
            {"kind": "written", "points": 10, "stem": f"求 \\({matrix}\\) 的行列式", "answer": r"\(-2\)", "explanation": f"计算 \\({derivation}\\)"},
        ]
        with patch("app.exams.generate", return_value=json.dumps({"questions": generated})):
            exam = client.post("/api/exams/generate", json={"course_id": course, "title": "数学试卷",
                               "groups": [{"kind": "written", "count": 2, "points": 10}]}).raise_for_status().json()
        path = f"/api/exams/{exam['id']}"
        answer = Document(BytesIO(client.get(f"{path}/answers/document", params={
            "revision": exam["revision"],
        }).raise_for_status().content))
        self.assertIn(derivation, [node.get(SOURCE) for node in answer.element.body.iter(qn("m:oMath"))])
        self.assertIn(matrix, client.get(f"{path}/export/paper/tex").raise_for_status().text)

    def check_lesson_templates(self, client, course, legacy_route):
        templates = "/api/lesson-templates"
        legacy = Document(BytesIO(client.get(f"{legacy_route}/document").raise_for_status().content))
        self.assertTrue(any("计算机" in paragraph.text for paragraph in legacy.paragraphs))

        def save_word(document):
            buffer = BytesIO()
            document.save(buffer)
            return buffer.getvalue()

        word = Document()
        word.add_heading("教学设计", level=1)
        word.add_table(rows=1, cols=1).cell(0, 0).text = "模板占位文字"
        word.add_page_break()
        word.add_paragraph("第二页正文")
        original = save_word(word)

        def upload():
            return client.post(templates, data={"title": "学校模板"}, files={
                "file": ("school.docx", original),
            }).raise_for_status().json()

        template = upload()
        template_route = f"{templates}/{template['id']}"
        self.assertEqual(client.patch(template_route, json={"title": "新名称"}).raise_for_status().json()["title"], "新名称")
        blank = client.post("/api/lessons", json={
            "course_id": course, "title": "空白教案", "blank_document": True,
        }).raise_for_status().json()
        blank_doc = Document(BytesIO(client.get(f"/api/lessons/{blank['id']}/document").raise_for_status().content))
        self.assertEqual([paragraph.text for paragraph in blank_doc.paragraphs], [""])
        def fill_generated_sections(_, prompt, structured):
            self.assertTrue(structured)
            expected = json.loads(prompt)["预期 JSON"]
            expected["sections"][0]["content"] = (
                "模型生成的教学内容\n| 教学环节 | 示例 |\n| --- | --- |\n| 练习 | A\\|B |"
            )
            return json.dumps(expected, ensure_ascii=False)

        with patch("app.ai.generate", side_effect=fill_generated_sections):
            generated = client.post("/api/ai/lessons", json={
                "course_id": course, "title": "模型草稿",
            }).raise_for_status().json()
        generated_path = f"/api/lessons/{generated['id']}/document"
        generated_doc = Document(BytesIO(client.get(generated_path).raise_for_status().content))
        self.assertIn("模型生成的教学内容", [paragraph.text for paragraph in generated_doc.paragraphs])
        for name, family in (("Normal", "宋体"), ("Normal Table", "宋体"), ("Title", "黑体"),
                             ("Heading 1", "黑体"), ("Heading 2", "黑体")):
            fonts = generated_doc.styles[name].element.xpath("./w:rPr/w:rFonts")[0]
            self.assertEqual([fonts.get(qn(f"w:{slot}")) for slot in ("ascii", "hAnsi", "eastAsia", "cs")], [family] * 4)
            self.assertIsNone(fonts.get(qn("w:eastAsiaTheme")))
        self.assertEqual(generated_doc.settings.element.xpath("./w:themeFontLang")[0].get(qn("w:eastAsia")), "zh-CN")
        self.assertEqual(generated_doc.tables[0].cell(1, 1).text, "A|B")
        self.assertTrue(generated_doc.tables[0]._tbl.xpath("./w:tblPr/w:tblBorders/w:insideH"))
        marked = Document()
        marked.add_heading("学校教案表单", level=1)
        marked.add_paragraph("课程名称：{{课程名称}}")
        label = marked.add_paragraph("目标：")
        label.add_run("{{教学").bold = True
        label.add_run("目标}}")
        arrangement = marked.add_paragraph()
        arrangement.paragraph_format.line_spacing = 1.5
        arrangement.paragraph_format.space_after = Pt(6)
        run = arrangement.add_run("{{课堂安排}}")
        run.font.name = "仿宋_GB2312;仿宋"
        run.font.size = Pt(12)
        run._r.rPr.rFonts.set(qn("w:eastAsia"), "仿宋_GB2312;仿宋")
        marked.add_paragraph("固定栏目说明")
        marked_template = client.post(templates, files={
            "file": ("marked.docx", save_word(marked)),
        }).raise_for_status().json()

        def fill_fields(_, prompt, structured):
            self.assertTrue(structured)
            self.assertEqual(set(json.loads(prompt)["预期 JSON"]["fields"]), {"教学目标", "课堂安排"})
            return json.dumps({"fields": {
                "教学目标": "理解数据校验",
                "课堂安排": "第一段\n第二段\n| 环节 | 内容 |\n| --- | --- |\n| 练习 | 校验输入 |\n表后说明",
                "固定栏目说明": "模型多返回的栏目",
            }})

        with patch("app.ai.generate", side_effect=fill_fields):
            filled = client.post("/api/ai/lessons", json={
                "course_id": course, "title": "基于模板", "template_id": marked_template["id"],
            }).raise_for_status().json()
        filled_doc = Document(BytesIO(client.get(f"/api/lessons/{filled['id']}/document").raise_for_status().content))
        self.assertIn("目标：理解数据校验", [paragraph.text for paragraph in filled_doc.paragraphs])
        self.assertTrue(filled_doc.paragraphs[2].runs[1].bold)
        self.assertEqual(filled_doc.paragraphs[-1].text, "固定栏目说明")
        self.assertEqual(filled_doc.tables[0].cell(1, 1).text, "校验输入")
        body = [paragraph for paragraph in filled_doc.paragraphs if paragraph.text in {"第一段", "第二段", "表后说明"}]
        self.assertEqual(len(body), 3)
        body.append(filled_doc.tables[0].cell(1, 1).paragraphs[0])
        for paragraph in body:
            self.assertEqual(paragraph.paragraph_format.line_spacing, 1.5)
            self.assertEqual(paragraph.paragraph_format.space_after, Pt(6))
            self.assertEqual(paragraph.runs[0].font.size, Pt(12))
            self.assertEqual(paragraph.runs[0]._r.rPr.rFonts.get(qn("w:eastAsia")), "仿宋")

        with patch("app.ai.generate", side_effect=fill_generated_sections):
            appended = client.post("/api/ai/lessons", json={
                "course_id": course, "title": "无栏目模板", "template_id": template["id"],
            }).raise_for_status().json()
        appended_doc = Document(BytesIO(client.get(f"/api/lessons/{appended['id']}/document").raise_for_status().content))
        self.assertEqual(appended_doc.tables[0].cell(0, 0).text, "模板占位文字")
        self.assertIn("模型生成的教学内容", [paragraph.text for paragraph in appended_doc.paragraphs])
        with patch("app.ai.generate", return_value="| 环节 | 内容 |\n| --- | --- |\n| 练习 | A |"):
            suggestion = client.post("/api/ai/writing", json={
                "lesson_id": generated["id"], "section": "正文", "mode": "continue",
                "formatting": {"font_family": "仿宋", "font_size": 14, "line_rule": "multiple", "line_spacing": 1.5},
            }).raise_for_status().json()
        self.assertEqual(suggestion["blocks"], [
            {"type": "table", "header": ["环节", "内容"], "rows": [["练习", "A"]]},
        ])
        fragment = Document(BytesIO(b64decode(suggestion["fragment"])))
        sample = fragment.tables[0].cell(1, 1).paragraphs[0]
        self.assertEqual(sample.paragraph_format.line_spacing, 1.5)
        self.assertEqual(sample.runs[0].font.size, Pt(14))
        self.assertEqual(sample.runs[0]._r.rPr.rFonts.get(qn("w:eastAsia")), "仿宋")
        plan = client.post("/api/lessons", json={
            "course_id": course, "title": "模板教案", "template_id": template["id"],
        }).raise_for_status().json()
        path = f"/api/lessons/{plan['id']}"
        self.assertEqual(client.get(f"{path}/document?revision=1").raise_for_status().content, original)
        client.delete(template_route).raise_for_status()

        word.tables[0].cell(0, 0).text = "已修改的表格"
        edited = save_word(word)
        data = {"title": "修改后", "revision": 1}
        files = {"file": ("lesson.docx", edited)}
        updated = client.put(f"{path}/document", data=data, files=files).raise_for_status().json()
        self.assertEqual(updated["revision"], 2)
        self.assertIn("已修改的表格", updated["sections"][0]["content"])
        self.assertEqual(client.put(f"{path}/document", data=data, files=files).status_code, 409)
        self.assertEqual(client.get(f"{path}/document?revision=1").status_code, 409)
        self.assertEqual(client.get(f"{path}/export/docx").raise_for_status().content, edited)
        list_path = f"/api/lessons?course_id={course}"
        count_before = len(client.get(list_path).raise_for_status().json())
        status_path = f"{path}/status"
        archived = client.patch(status_path, json={"status": "archived"}).raise_for_status().json()
        self.assertEqual((archived["id"], archived["status"]), (plan["id"], "archived"))
        renamed = client.put(path, json={"title": "已归档教案", "revision": archived["revision"]}).raise_for_status().json()
        self.assertEqual(renamed["status"], "archived")
        restored = client.patch(status_path, json={"status": "draft"}).raise_for_status().json()
        self.assertEqual((restored["id"], restored["status"]), (plan["id"], "draft"))
        retry = client.patch(status_path, json={"status": "draft"}).raise_for_status().json()
        self.assertEqual(retry["revision"], restored["revision"])
        self.assertEqual(len(client.get(list_path).raise_for_status().json()), count_before)
        self.assertEqual(client.get(f"{path}/document").raise_for_status().content, edited)

        key = {"Idempotency-Key": str(uuid4())}
        duplicate = client.post(f"{path}/copy", headers=key).raise_for_status().json()
        self.assertNotEqual(duplicate["id"], plan["id"])
        for _ in range(2):
            retried = client.post(f"{path}/copy", headers=key).raise_for_status().json()
            self.assertEqual(retried["id"], duplicate["id"])
        self.assertEqual(len(client.get(list_path).raise_for_status().json()), count_before + 1)
        self.assertEqual(client.get(f"/api/lessons/{duplicate['id']}/document").raise_for_status().content, edited)
        return upload()["id"]

    def check_word_preview(self, client, teacher, course, converted_pdf, engine, files, resource_model, new_id):
        buffer = BytesIO()
        word = Document()
        word.add_heading("Transactions", level=1)
        word.save(buffer)
        original = buffer.getvalue()
        with patch("app.documents.office_executable", return_value=None):
            response = client.post("/api/resources", data={"course_id": course}, files={
                "file": ("legacy.docx", original),
            })
        self.assertEqual(response.status_code, 503)
        self.assertEqual(client.get(f"/api/resources?course_id={course}").json(), [])

        resource_id = new_id()
        folder = files / resource_id
        folder.mkdir()
        (folder / "original.docx").write_bytes(original)
        with Session(engine) as db:
            db.add(resource_model(
                id=resource_id, owner_id=teacher["id"], course_id=course, title="旧 Word 讲义",
                filename="legacy.docx", extension="docx", size=len(original), pages=["旧的整篇文本"],
            ))
            db.commit()
        self.assertEqual(client.get(f"/api/resources/{resource_id}/pages/1").status_code, 409)

        def convert(_, filter_spec, output):
            self.assertIn("ExportBookmarks", filter_spec)
            result = output / "converted.pdf"
            result.write_bytes(converted_pdf)
            return result

        with patch("app.documents.office_executable", return_value="test-office"), patch(
            "app.documents.convert_with_office", side_effect=convert,
        ):
            row = client.post(f"/api/resources/{resource_id}/process").raise_for_status().json()
            uploaded = client.post("/api/resources", data={"course_id": course}, files={
                "file": ("new.docx", original),
            }).raise_for_status().json()
        self.assertEqual(row["title"], "旧 Word 讲义")
        for entry in (row, uploaded):
            self.assertTrue(entry["has_preview"])
            self.assertEqual(entry["page_count"], 2)
            self.assertEqual(entry["outline"][0]["children"][0]["start"], 2)
            preview = client.get(f"/api/resources/{entry['id']}/preview").raise_for_status()
            self.assertEqual(preview.content, converted_pdf)
        second_page = client.get(f"/api/resources/{resource_id}/pages/2").raise_for_status().json()
        self.assertIn("Repeatable read", second_page["text"])


if __name__ == "__main__":
    unittest.main()
