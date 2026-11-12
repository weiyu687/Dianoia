"""Create development-only accounts and an example course in the selected database."""
import os
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import passwords
from .db import Base, engine
from .models import ClassGroup, Course, Enrollment, Student, TeachingAssignment, User

SAMPLE_COURSE_NAME = "python语言与程序设计"


def main():
    password = os.getenv("DIANOIA_SEED_PASSWORD") or getpass("本地虚拟账号密码（至少 10 字符）: ")
    if len(password) < 10:
        raise SystemExit("密码至少需要 10 字符")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        accounts = {}
        for username, name, role in (("admin", "学校管理员", "admin"), ("teacher", "林老师", "teacher")):
            account = db.scalar(select(User).where(User.username == username))
            if not account:
                account = User(username=username, name=name, role=role, password_hash=passwords.hash(password))
                db.add(account)
            if account.role != role:
                raise SystemExit(f"{username} 已被其他角色使用")
            accounts[role] = account
        course = db.scalar(select(Course).where(Course.code == "DB101"))
        if not course:
            course = Course(code="DB101", name=SAMPLE_COURSE_NAME)
            db.add(course)
        elif course.name == "数据库原理":
            course.name = SAMPLE_COURSE_NAME
        db.flush()
        assignment = (accounts["teacher"].id, course.id)
        if not db.get(TeachingAssignment, assignment):
            db.add(TeachingAssignment(teacher_id=assignment[0], course_id=assignment[1]))
        if not db.get(ClassGroup, "DB101-01"):
            db.add(ClassGroup(code="DB101-01", name="计算机一班", course_id=course.id))
        for index in range(1, 7):
            code = f"V{index:03}"
            if not db.get(Student, code):
                db.add(Student(code=code, name=f"虚拟学生 {index}"))
            db.flush()
            if not db.get(Enrollment, (code, "DB101-01")):
                db.add(Enrollment(student_code=code, class_code="DB101-01"))
        db.commit()
    print("虚拟账号已就绪。教师账号 teacher，管理员账号 admin。已存在账号的密码保持原值。")


if __name__ == "__main__":
    main()
