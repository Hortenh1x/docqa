"""Celery ingestion pipeline: parse → chunk → embed → store.

Status machine: pending → processing → ready | failed.

- The task is idempotent: at-least-once delivery re-runs are no-ops unless the document
  is pending or its processing lease expired. Terminal rows require explicit reprocess.
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
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from celery import Task
from sqlalchemy import and_, delete, func, or_, select

from app.billing.errors import BudgetExceededError, BudgetUnavailableError
from app.billing.jobs import attributed, collection_billing
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
MAX_ATTEMPTS = 4
LEASE_SECONDS = 660  # longer than Celery hard time limit (600s)


def _run_async(coro: Coroutine[Any, Any, list[list[float]]]) -> list[list[float]]:
    """asyncio.run, but safe under Celery eager mode where a loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _mark_failed(document_id: uuid.UUID, error: str, token: uuid.UUID) -> None:
    with sync_session() as session:
        document = session.get(Document, document_id, with_for_update=True)
        if document is None or document.processing_token != token:
            return
        document.status = DocumentStatus.FAILED
        document.processing_token = None
        document.lease_expires_at = None
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
            select(Document, Collection)
            .join(Collection, Document.collection_id == Collection.id)
            .where(Document.id == document_id)
            .with_for_update(of=Collection)
        ).first()
        if row is None:
            return
        trigger, collection = row
        collection_id, existing = collection.id, collection.suggested_questions
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
        # Persist the request that actually triggered this draft, not a guess based
        # on whichever upload happens to remain newest when the task executes.
        collection.suggestion_billing_user_id = trigger.billing_user_id
        collection.suggestion_billing_ip_digest = trigger.billing_ip_digest
        collection.suggestion_revision += 1
        revision = collection.suggestion_revision
    try:
        suggest_questions.delay(str(collection_id), revision)
    except Exception:
        log.warning("suggestions_enqueue_failed", collection_id=str(collection_id))


def _store_chunks(
    document_id: uuid.UUID,
    parsed: ParsedDocument,
    drafts: list[ChunkDraft],
    embeddings: list[list[float]],
    token: uuid.UUID,
) -> bool:
    with sync_session() as session:
        document = session.get(Document, document_id, with_for_update=True)
        if document is None or document.processing_token != token:
            log.warning("document_vanished_or_reclaimed", document_id=str(document_id))
            return False
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
        document.processing_token = None
        document.lease_expires_at = None
        document.error = None
        document.page_count = max(
            (page.number for page in parsed.pages if page.number is not None), default=None
        )
        document.processed_at = datetime.now(UTC)

    return True


@celery_app.task(name="ingestion.ingest_document", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def ingest_document(self: Task, document_id: str) -> None:
    doc_id = uuid.UUID(document_id)
    log_ctx = log.bind(document_id=document_id)
    token = uuid.uuid4()
    exhausted = False

    with sync_session() as session:
        row = session.execute(
            select(Document, Collection.tenant_id)
            .join(Collection, Document.collection_id == Collection.id)
            .where(Document.id == doc_id)
            .with_for_update(of=Document)
        ).first()
        if row is None:
            log_ctx.warning("document_not_found")
            return
        document, tenant_id = row
        now = datetime.now(UTC)
        if document.status in (DocumentStatus.READY, DocumentStatus.FAILED):
            return
        if (
            document.status == DocumentStatus.PROCESSING
            and document.lease_expires_at
            and document.lease_expires_at > now
        ):
            return
        if (
            document.status == DocumentStatus.PENDING
            and document.next_attempt_at
            and document.next_attempt_at > now
            and not self.request.is_eager
        ):
            return
        if document.ingestion_attempts >= MAX_ATTEMPTS:
            document.status = DocumentStatus.FAILED
            document.error = "Ingestion recovery exhausted after repeated interrupted attempts."
            document.processing_token = None
            document.lease_expires_at = None
            document.processed_at = now
            exhausted = True
        else:
            document.processing_token = token
            document.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            document.ingestion_attempts += 1
            attempt = document.ingestion_attempts
            document.status = DocumentStatus.PROCESSING
            document.error = None

    if exhausted:
        _refresh_suggestions_if_settled(doc_id, corpus_changed=False)
        return

    # heavy work happens outside any transaction
    try:
        path = get_storage().path_for(
            str(tenant_id), document.sha256, EXT_BY_MIME[document.mime_type]
        )
        parsed = get_parser(document.mime_type).parse(path)
        drafts = chunk_document(parsed)
        provider = get_embedding_provider(get_settings())
        payer, operator = collection_billing(document.collection_id, doc_id)
        embeddings = _run_async(
            attributed(provider.embed([draft.content for draft in drafts]), payer, operator)
        )
        if not _store_chunks(doc_id, parsed, drafts, embeddings, token):
            return
    except (BudgetExceededError, BudgetUnavailableError) as exc:
        log_ctx.warning("ingest_budget_blocked", code=exc.code)
        _mark_failed(doc_id, f"{exc.code}: {exc.detail}", token)
        return
    except ParserError as exc:
        log_ctx.warning("ingest_parse_failed", error_type=type(exc).__name__)
        _mark_failed(doc_id, f"parse error: {exc}", token)
        return
    except EmbeddingError as exc:
        log_ctx.warning(
            "ingest_embeddings_unavailable",
            error_type=type(exc).__name__,
            attempt=self.request.retries,
        )
        if attempt >= MAX_ATTEMPTS:
            _mark_failed(doc_id, "Embedding provider unavailable after all attempts.", token)
            return
        delay = RETRY_BASE_SECONDS * 2 ** (attempt - 1)
        with sync_session() as session:
            current = session.get(Document, doc_id, with_for_update=True)
            if current is None or current.processing_token != token:
                return
            current.status = DocumentStatus.PENDING
            current.processing_token = None
            current.lease_expires_at = None
            current.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
        # If retry publication itself fails, the durable pending row is picked up
        # by the periodic recovery task. Attempts are counted in DB, across task IDs.
        raise self.retry(exc=exc, countdown=delay) from exc
    except Exception:
        log_ctx.error("ingest_unexpected_error")
        _mark_failed(doc_id, "Ingestion failed. See worker logs with the document ID.", token)
        return

    log_ctx.info("ingest_done", chunks=len(drafts))
    _refresh_suggestions_if_settled(doc_id, corpus_changed=True)


@celery_app.task(name="ingestion.recover")  # type: ignore[untyped-decorator]
def recover_ingestion() -> int:
    """Republish committed uploads and expired claims, including legacy processing rows.

    Reservations throttle duplicate publication. Their expiry also repairs a crash
    between reserving a row here and publishing it; the worker owns actual claiming.
    Run Celery beat alongside the worker (one scheduler per deployment).
    """
    now = datetime.now(UTC)
    due = or_(
        and_(
            Document.status == DocumentStatus.PENDING,
            or_(Document.next_attempt_at.is_(None), Document.next_attempt_at <= now),
        ),
        and_(
            Document.status == DocumentStatus.PROCESSING,
            or_(Document.lease_expires_at.is_(None), Document.lease_expires_at <= now),
        ),
    )
    with sync_session() as session:
        documents = session.scalars(
            select(Document)
            .where(
                due,
                or_(
                    Document.last_enqueued_at.is_(None),
                    Document.last_enqueued_at <= now - timedelta(seconds=60),
                ),
            )
            .order_by(Document.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        ids = [str(document.id) for document in documents]
        for document in documents:
            document.last_enqueued_at = now
    for document_id in ids:
        try:
            ingest_document.delay(document_id)
        except Exception:
            log.warning("ingestion_recovery_publish_failed", document_id=document_id)
    if ids:
        log.info("ingestion_recovery_dispatched", count=len(ids))
    return len(ids)
