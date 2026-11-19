"""CPU/API worker: python -m app.question_banks.worker [--once]."""

import argparse
import logging
from datetime import timedelta
from threading import Event, Thread
from time import sleep

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import engine
from ..models import User, identifier, now
from ..migrate import initialize_database
from .content import plain
from .generation import generate_batch
from .models import BankGenerationJob, BankQuestion, QuestionBank
from .service import create_question, question_rows, owned, question_content

log = logging.getLogger(__name__)
LEASE = timedelta(minutes=2)


class LostLease(Exception):
    pass


def claim_job():
    with Session(engine) as db:
        db.execute(update(BankGenerationJob).where(BankGenerationJob.status == "running", BankGenerationJob.updated_at < now() - LEASE)
                   .values(status="queued", lease=None, stage="正在恢复中断任务"))
        job_id = db.scalar(select(BankGenerationJob.id).where(BankGenerationJob.status == "queued")
                           .order_by(BankGenerationJob.created_at, BankGenerationJob.id).limit(1))
        token = identifier()
        claimed = job_id and db.execute(update(BankGenerationJob).where(BankGenerationJob.id == job_id, BankGenerationJob.status == "queued")
                         .values(status="running", lease=token, updated_at=now(), error=""))
        db.commit()
        return (job_id, token) if claimed and claimed.rowcount else None


def heartbeat(job_id, token):
    with Session(engine) as db:
        result = db.execute(update(BankGenerationJob).where(BankGenerationJob.id == job_id, BankGenerationJob.lease == token,
                            BankGenerationJob.status == "running").values(updated_at=now()))
        db.commit()
        if not result.rowcount:
            raise LostLease()


def process(claim):
    job_id, token = claim
    stopped, lost = Event(), Event()

    def keep_alive():
        while not stopped.wait(10):
            try:
                heartbeat(job_id, token)
            except Exception:
                lost.set()
                return

    thread = Thread(target=keep_alive, daemon=True)
    thread.start()
    try:
        while True:
            with Session(engine) as db:
                job = db.get(BankGenerationJob, job_id)
                if not job or job.lease != token or job.status != "running" or lost.is_set():
                    raise LostLease()
                if job.completed >= job.total:
                    job.status, job.stage, job.lease, job.updated_at = "succeeded", "题目已生成，请核对答案后确认发布", None, now()
                    db.commit()
                    return
                spec, offset = job.config, job.completed
                bank = db.get(QuestionBank, job.bank_id)
                user = db.get(User, bank.owner_id)
                if not user or not user.enabled or user.role != "teacher":
                    raise HTTPException(403, "教师账号不可用")
                owned(db, user, bank.id)
                existing = [plain(question_content(db, q)["body"])
                            for q in db.scalars(question_rows(db, bank.id).order_by(BankQuestion.position.desc()).limit(40))]
                spec = {**spec, "existing": [text[:180] for text in existing]}
                job.stage = f"正在生成第 {offset + 1}–{min(offset + 3, job.total)} 题"
                job.updated_at = now()
                db.commit()
            questions = generate_batch(spec, spec["kinds"][offset:offset + 3])
            with Session(engine) as db:
                result = db.execute(update(BankGenerationJob).where(BankGenerationJob.id == job_id, BankGenerationJob.lease == token,
                                    BankGenerationJob.status == "running", BankGenerationJob.completed == offset).values(updated_at=now()))
                if not result.rowcount or lost.is_set():
                    raise LostLease()
                job = db.get(BankGenerationJob, job_id)
                bank = db.get(QuestionBank, job.bank_id)
                user = db.get(User, bank.owner_id)
                owned(db, user, bank.id)
                seen = {"".join(text.split()).casefold() for text in existing}
                for index, question in enumerate(questions, offset):
                    text = "".join(plain(question.body).split()).casefold()
                    if text in seen:
                        raise HTTPException(502, "模型生成了重复题干，请调整要求后重试；已完成题目保留")
                    seen.add(text)
                    create_question(db, user, bank, question, job_id=job_id, slot=index)
                job.completed = offset + len(questions)
                job.updated_at = now()
                db.commit()
    except LostLease:
        log.info("Question bank job %s cancelled or reassigned", job_id)
    except Exception as error:
        log.exception("Question bank generation failed: %s", job_id)
        with Session(engine) as db:
            message = str(error.detail) if isinstance(error, HTTPException) else "生成失败，请重试；已生成题目已保留"
            db.execute(update(BankGenerationJob).where(BankGenerationJob.id == job_id, BankGenerationJob.lease == token, BankGenerationJob.status == "running")
                       .values(status="failed", lease=None, stage="生成失败", error=message[:500], updated_at=now()))
            db.commit()
    finally:
        stopped.set()
        thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    initialize_database()
    while True:
        if claim := claim_job():
            process(claim)
        if args.once:
            return
        if not claim:
            sleep(2)


if __name__ == "__main__":
    main()
