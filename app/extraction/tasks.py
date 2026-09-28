"""Celery task: run one extraction."""

import uuid

import structlog
from celery import Task

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
