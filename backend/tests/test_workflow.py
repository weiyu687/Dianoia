import json
import os
import unittest
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient
from openpyxl import Workbook
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
                    self.assertIn("教学对象", model.call_args.args[1])
                    self.assertEqual(client.get(route).json()["revision"], 2)

                private_template = self.check_lesson_templates(client, course, route)
                second_teacher = login("t02", "teacher")
                self.assertNotEqual(second_teacher["courses"][0]["id"], course)
                self.assertEqual(client.get(route).status_code, 404)
                self.assertEqual(client.get(f"/api/resources/{resource['id']}/file").status_code, 404)
                self.assertEqual(client.get("/api/lesson-templates").json(), [])
                self.assertEqual(client.get(f"/api/lesson-templates/{private_template}/preview").status_code, 404)
                self.assertEqual(client.post("/api/lessons", json={
                    "course_id": second_teacher["courses"][0]["id"], "title": "未授权模板",
                    "template_id": private_template,
                }).status_code, 404)

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
            expected["sections"][0]["content"] = "模型生成的教学内容"
            return json.dumps(expected, ensure_ascii=False)

        with patch("app.ai.generate", side_effect=fill_generated_sections):
            generated = client.post("/api/ai/lessons", json={
                "course_id": course, "title": "模型草稿",
            }).raise_for_status().json()
        generated_path = f"/api/lessons/{generated['id']}/document"
        generated_doc = Document(BytesIO(client.get(generated_path).raise_for_status().content))
        self.assertIn("模型生成的教学内容", [paragraph.text for paragraph in generated_doc.paragraphs])
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
        duplicate = client.post(f"{path}/copy").raise_for_status().json()
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
