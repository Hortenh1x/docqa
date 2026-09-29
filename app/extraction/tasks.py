"""Celery task: run one extraction."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from celery import Task
from sqlalchemy import or_, select

from app.db.models import Extraction, ExtractionStatus
from app.db.sync import sync_session
from app.extraction.service import run_extraction
from app.workers.celery_app import celery_app

log = structlog.get_logger("docqa.extraction")


@celery_app.task(name="extraction.run", bind=True, max_retries=0)  # type: ignore[untyped-decorator]
def extract(self: Task, extraction_id: str) -> None:
    run_extraction(uuid.UUID(extraction_id))


def enqueue_extraction(extraction_id: uuid.UUID) -> None:
    try:
        extract.delay(str(extraction_id))
    except Exception:
        log.warning("extraction_publish_deferred", extraction_id=str(extraction_id))


@celery_app.task(name="extraction.recover")  # type: ignore[untyped-decorator]
def recover_extractions() -> int:
    """Republish lost pending work; fail abandoned claims without repeating paid calls."""
    now = datetime.now(UTC)
    # Exceeds Celery's 600-second hard limit, so a live worker cannot lose its claim.
    expired = now - timedelta(seconds=660)
    with sync_session() as session:
        rows = session.scalars(
            select(Extraction)
            .where(
                or_(
                    (Extraction.status == ExtractionStatus.PENDING)
                    & (Extraction.updated_at < now - timedelta(seconds=60)),
                    (Extraction.status == ExtractionStatus.PROCESSING)
                    & (Extraction.updated_at < expired),
                )
            )
            .order_by(Extraction.updated_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        ids = []
        for extraction in rows:
            extraction.updated_at = now
            if extraction.status == ExtractionStatus.PROCESSING:
                extraction.status = ExtractionStatus.FAILED
                extraction.processing_token = None
                extraction.error = "Worker stopped before extraction completed. Re-run to retry."
            else:
                ids.append(extraction.id)
    for extraction_id in ids:
        enqueue_extraction(extraction_id)
    return len(ids)
