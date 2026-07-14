"""Celery ingestion tasks. The full parse→chunk→embed pipeline lands with day 7."""

import structlog

from app.workers.celery_app import celery_app

log = structlog.get_logger("docqa.ingestion")


@celery_app.task(name="ingestion.ingest_document", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def ingest_document(self: object, document_id: str) -> None:
    log.info("ingest_received", document_id=document_id)
