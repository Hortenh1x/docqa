"""Celery ingestion pipeline: parse → chunk → embed → store.

Status machine: pending → processing → ready | failed.

- The task is idempotent: at-least-once delivery re-runs are no-ops unless the document
  is pending or failed.
- ParserError never retries — the file will not become more valid.
- EmbeddingError (network/provider) retries with exponential backoff, then fails.
- Existing chunks are deleted before insert, so reprocessing a failed document never
  duplicates rows.
- Every terminal state (ready or failed) may settle the collection — when nothing is
  left in flight, a suggested-questions refresh is enqueued (best-effort, decoupled).
"""

import asyncio
import concurrent.futures
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

import structlog
from celery import Task
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db.models import Chunk, Collection, Document, DocumentStatus
from app.db.sync import sync_session
from app.embeddings import get_embedding_provider
from app.embeddings.base import EmbeddingError
from app.generation.tasks import suggest_questions
from app.ingestion.chunking import ChunkDraft, chunk_document
from app.ingestion.mime import EXT_BY_MIME
from app.ingestion.parsers import ParsedDocument, ParserError, get_parser
from app.storage import get_storage
from app.workers.celery_app import celery_app

log = structlog.get_logger("docqa.ingestion")

RETRY_BASE_SECONDS = 10


def _run_async(coro: Coroutine[Any, Any, list[list[float]]]) -> list[list[float]]:
    """asyncio.run, but safe under Celery eager mode where a loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _mark_failed(document_id: uuid.UUID, error: str) -> None:
    with sync_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            return
        document.status = DocumentStatus.FAILED
        document.error = error[:500]
        document.processed_at = datetime.now(UTC)
    # a terminal failure can be the last in-flight document of its collection
    _refresh_suggestions_if_settled(document_id, corpus_changed=False)


def _refresh_suggestions_if_settled(document_id: uuid.UUID, *, corpus_changed: bool) -> None:
    """Enqueue a suggested-questions refresh once the collection has nothing in flight.

    ``corpus_changed=False`` (a failed ingest adds no chunks) skips the refresh when
    questions already exist — nothing changed, no LLM call to spend.
    """
    if not get_settings().suggested_questions_enabled:
        return
    with sync_session() as session:
        row = session.execute(
            select(Document.collection_id, Collection.suggested_questions)
            .join(Collection, Document.collection_id == Collection.id)
            .where(Document.id == document_id)
        ).first()
        if row is None:
            return
        collection_id, existing = row
        in_flight = session.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.collection_id == collection_id,
                Document.status.in_((DocumentStatus.PENDING, DocumentStatus.PROCESSING)),
            )
        ).scalar_one()
        # two workers can settle the collection near-simultaneously — let only the
        # latest terminal document enqueue, so one settle spends one LLM call
        latest = session.execute(
            select(Document.id)
            .where(
                Document.collection_id == collection_id,
                Document.processed_at.isnot(None),
            )
            .order_by(Document.processed_at.desc(), Document.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    if in_flight or latest != document_id:
        return
    if not corpus_changed and existing is not None:
        return
    suggest_questions.delay(str(collection_id))


def _store_chunks(
    document_id: uuid.UUID,
    parsed: ParsedDocument,
    drafts: list[ChunkDraft],
    embeddings: list[list[float]],
) -> None:
    with sync_session() as session:
        document = session.get(Document, document_id)
        if document is None:  # deleted while we were working
            log.warning("document_vanished", document_id=str(document_id))
            return
        # reprocessing must not duplicate chunks
        session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        session.add_all(
            Chunk(
                document_id=document_id,
                chunk_index=draft.chunk_index,
                content=draft.content,
                token_count=draft.token_count,
                page_start=draft.page_start,
                page_end=draft.page_end,
                section_path=draft.section_path,
                access_label=draft.access_label,
                embedding=embedding,
            )
            for draft, embedding in zip(drafts, embeddings, strict=True)
        )
        document.status = DocumentStatus.READY
        document.error = None
        document.page_count = max(
            (page.number for page in parsed.pages if page.number is not None), default=None
        )
        document.processed_at = datetime.now(UTC)


@celery_app.task(name="ingestion.ingest_document", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def ingest_document(self: Task, document_id: str) -> None:
    doc_id = uuid.UUID(document_id)
    log_ctx = log.bind(document_id=document_id)

    with sync_session() as session:
        row = session.execute(
            select(Document, Collection.tenant_id)
            .join(Collection, Document.collection_id == Collection.id)
            .where(Document.id == doc_id)
        ).first()
        if row is None:
            log_ctx.warning("document_not_found")
            return
        document, tenant_id = row
        if document.status not in (DocumentStatus.PENDING, DocumentStatus.FAILED):
            # at-least-once delivery: a concurrent/duplicate run is a no-op
            log_ctx.info("ingest_skipped", status=document.status)
            return
        document.status = DocumentStatus.PROCESSING
        document.error = None

    # heavy work happens outside any transaction
    try:
        path = get_storage().path_for(
            str(tenant_id), document.sha256, EXT_BY_MIME[document.mime_type]
        )
        parsed = get_parser(document.mime_type).parse(path)
        drafts = chunk_document(parsed)
        provider = get_embedding_provider(get_settings())
        embeddings = _run_async(provider.embed([draft.content for draft in drafts]))
    except ParserError as exc:
        log_ctx.warning("ingest_parse_failed", error=str(exc))
        _mark_failed(doc_id, f"parse error: {exc}")
        return
    except EmbeddingError as exc:
        log_ctx.warning(
            "ingest_embeddings_unavailable", error=str(exc), attempt=self.request.retries
        )
        try:
            raise self.retry(exc=exc, countdown=RETRY_BASE_SECONDS * 2**self.request.retries)
        except MaxRetriesExceededError:
            _mark_failed(doc_id, f"embedding provider unavailable: {exc}")
            return
    except Exception as exc:
        log_ctx.exception("ingest_unexpected_error")
        _mark_failed(doc_id, f"ingestion error: {exc}")
        return

    _store_chunks(doc_id, parsed, drafts, embeddings)
    log_ctx.info("ingest_done", chunks=len(drafts))
    _refresh_suggestions_if_settled(doc_id, corpus_changed=True)
