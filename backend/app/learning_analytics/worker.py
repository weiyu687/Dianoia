"""Recoverable CPU worker: python -m app.learning_analytics.worker [--once]."""

import argparse
import logging
import os
from datetime import timedelta
from time import sleep

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..db import engine
from ..models import now
from .models import LearningImportBatch, LearningObservation
from .parser import read_parsed
from .schemas import MappingConfig
from .service import observation_rows, preview_rows, validate_mapping

log = logging.getLogger(__name__)


def claim_batch():
    with Session(engine) as db:
        db.execute(update(LearningImportBatch)
                   .where(LearningImportBatch.status == "processing", LearningImportBatch.updated_at < now() - timedelta(minutes=5))
                   .values(status="failed", error="导入服务中断，请重新提交", updated_at=now()))
        batch_id = db.scalar(select(LearningImportBatch.id).where(LearningImportBatch.status == "queued")
                             .order_by(LearningImportBatch.created_at, LearningImportBatch.id).limit(1))
        claimed = batch_id and db.execute(
            update(LearningImportBatch).where(LearningImportBatch.id == batch_id, LearningImportBatch.status == "queued")
            .values(status="processing", updated_at=now(), error="")
        ).rowcount == 1
        db.commit()
        return batch_id if claimed else None


def process(batch_id):
    with Session(engine) as db:
        batch = db.get(LearningImportBatch, batch_id)
        if not batch or batch.status != "processing":
            return
        path = batch.parsed_path
        try:
            rows = read_parsed(path)
            mapping = MappingConfig.model_validate(batch.mapping)
            validate_mapping(mapping, batch.columns)
            counts = preview_rows(rows, mapping)
            db.execute(delete(LearningObservation).where(LearningObservation.batch_id == batch.id))
            db.commit()
            chunk, processed = [], 0
            for observation in observation_rows(rows, mapping, batch):
                chunk.append(observation)
                if len(chunk) >= 1200:
                    db.add_all(chunk)
                    processed += len(chunk)
                    db.execute(update(LearningImportBatch).where(
                        LearningImportBatch.id == batch.id, LearningImportBatch.status == "processing"
                    ).values(processed_count=processed, updated_at=now()))
                    db.commit()
                    chunk = []
            if chunk:
                db.add_all(chunk)
                processed += len(chunk)
            db.execute(update(LearningImportBatch).where(
                LearningImportBatch.id == batch.id, LearningImportBatch.status == "processing"
            ).values(status="ready", valid_count=counts["valid_count"], invalid_count=counts["invalid_count"],
                     processed_count=processed, updated_at=now(), error=""))
            db.commit()
        except Exception as error:
            db.rollback()
            log.exception("Learning analytics import %s failed", batch_id)
            db.execute(delete(LearningObservation).where(LearningObservation.batch_id == batch_id))
            db.execute(update(LearningImportBatch).where(LearningImportBatch.id == batch_id)
                       .values(status="failed", error=str(error)[:500] or "导入失败，请重新检查字段映射",
                               processed_count=0, updated_at=now()))
            db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one queued import")
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("DIANOIA_ANALYTICS_LOG_LEVEL", "INFO"))
    while True:
        batch_id = claim_batch()
        if batch_id:
            process(batch_id)
        elif args.once:
            return
        else:
            sleep(2)


if __name__ == "__main__":
    main()
