"""Generate synthetic CSV/XLSX fixtures for the teacher learning-analytics importer."""

import csv
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "frontend" / "public" / "test-data" / "learning-analytics"
STUDENTS = [(f"DEMO-{index:03d}", f"示例学生{index:02d}") for index in range(1, 13)]
START = date(2026, 9, 7)


def write_csv(path, headers, rows, encoding):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=encoding) as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def build_csvs():
    grade_rows = []
    for index, (student_id, name) in enumerate(STUDENTS):
        grade_rows.append([
            student_id, name, f"{START + timedelta(days=14)}", "函数与参数",
            61 + (index * 7 % 37), 58 + (index * 11 % 41), 72 + (index * 5 % 29),
            "" if index == 4 else 80 + (index * 9 % 21),
        ])
    write_csv(OUTPUT / "成绩示例-UTF8.csv",
              ["考生号", "学生姓名", "测验日期", "课程单元", "随堂测验", "第一次作业", "阶段测验", "补充测验"],
              grade_rows, "utf-8-sig")

    homework_rows = []
    statuses = ["已提交", "按时完成", "未提交", "已提交", "迟交", "完成"]
    for index, (student_id, name) in enumerate(STUDENTS):
        homework_rows.append([
            student_id, name, f"作业 {index % 3 + 1}", statuses[index % len(statuses)],
            "" if index in {2, 9} else 6 + (index * 3 % 5), 10,
            ("函数定义" if index % 2 else "参数与返回值"), f"{START + timedelta(days=7 + index)}",
        ])
    write_csv(OUTPUT / "作业示例-GB18030.csv",
              ["学号", "姓名", "作业名称", "提交状态", "批阅得分", "满分", "知识点", "提交时间"],
              homework_rows, "gb18030")


def style_sheet(sheet):
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4E3B81")
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 25
    for column in sheet.columns:
        values = [str(cell.value or "") for cell in list(column)[:20]]
        width = min(max(max((len(value) for value in values), default=10) + 3, 12), 24)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = width


def build_xlsx():
    workbook = Workbook()
    grades = workbook.active
    grades.title = "阶段成绩"
    grades.append(["学生编号", "学生姓名", "班级名称", "考试日期", "单元测验", "期中考试", "期中满分", "知识点"])
    for index, (student_id, name) in enumerate(STUDENTS):
        grades.append([student_id, name, "Python 设计 1 班", START + timedelta(days=14),
                       62 + index * 3, 55 + (index * 9 % 46), 100, "函数调用" if index % 2 else "返回值"])
    tasks = workbook.create_sheet("作业提交")
    tasks.append(["StudentID", "姓名", "作业名称", "完成状态", "分数", "满分", "章节", "截止日期"])
    status = ["已提交", "未提交", "迟交", "按时完成"]
    for index, (student_id, name) in enumerate(STUDENTS):
        tasks.append([student_id, name, f"实验作业 {index % 3 + 1}", status[index % len(status)],
                      None if index == 5 else 5 + (index * 7 % 11), 20, "循环控制", START + timedelta(days=21)])
    attendance = workbook.create_sheet("课堂考勤")
    attendance.append(["签到日期", "课程班", "学生学号", "学生姓名", "课堂活动", "签到结果"])
    attendance_values = ["出勤", "出勤", "迟到", "请假", "出勤", "缺勤"]
    for index, (student_id, name) in enumerate(STUDENTS):
        attendance.append([START + timedelta(days=28), "Python 设计 1 班", student_id, name,
                           "循环结构练习", attendance_values[index % len(attendance_values)]])
    for sheet in workbook.worksheets:
        style_sheet(sheet)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    workbook.save(OUTPUT / "课程学情综合示例.xlsx")


if __name__ == "__main__":
    build_csvs()
    build_xlsx()
    print(f"Synthetic fixtures written to {OUTPUT}")
