import os
import unittest
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas


class WorkflowTest(unittest.TestCase):
    def test_import_authorization_documents_and_writing(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "DIANOIA_DATA_DIR": directory,
            "DIANOIA_DATABASE_URL": f"sqlite:///{directory}/workflow.db",
            "DIANOIA_SEED_PASSWORD": "Synthetic-test-password!",
            "DIANOIA_SECURE_COOKIE": "false",
        }):
            from app.admin import SHEETS
            from app.main import app
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
                canvas.bookmarkPage("second")
                canvas.addOutlineEntry("Isolation", "second", level=1)
                canvas.drawString(40, 500, "Repeatable read is an isolation level.")
                canvas.save()
                resource = client.post("/api/resources", data={"course_id": course}, files={
                    "file": ("transactions.pdf", file.getvalue(), "application/pdf"),
                }).raise_for_status().json()
                self.assertEqual(resource["outline"][0]["children"][0]["start"], 2)
                client.patch(f"/api/resources/{resource['id']}", json={
                    "title": "事务讲义", "outline": resource["outline"], "status": "ready",
                }).raise_for_status()
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

                second_teacher = login("t02", "teacher")
                self.assertNotEqual(second_teacher["courses"][0]["id"], course)
                self.assertEqual(client.get(route).status_code, 404)
                self.assertEqual(client.get(f"/api/resources/{resource['id']}/file").status_code, 404)


if __name__ == "__main__":
    unittest.main()
