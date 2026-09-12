"""Suggested-questions Celery task.

Enqueued by the ingestion pipeline when a collection has no documents left in
flight, and by the document-delete route. Best-effort by design: any failure keeps
the previous questions — nothing here may break ingestion or the worker.
"""

import asyncio
import concurrent.futures
import uuid
from collections.abc import Coroutine
from typing import Any

import structlog
from celery import Task

from app.billing.errors import BudgetExceededError, BudgetUnavailableError
from app.billing.jobs import attributed, collection_billing
from app.config import get_settings
from app.db.models import Collection
from app.db.sync import sync_session
from app.embeddings.base import EmbeddingError
from app.generation.llm import GenerationError
from app.generation.suggestions import (
    draft_candidates,
    locked_document_hint,
    rank_questions,
    sample_excerpts,
)
from app.workers.celery_app import celery_app

log = structlog.get_logger("docqa.suggestions")

RETRY_BASE_SECONDS = 10


def _run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """asyncio.run, but safe under Celery eager mode where a loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@celery_app.task(name="generation.suggest_questions", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def suggest_questions(self: Task, collection_id: str, expected_revision: int | None = None) -> None:
    settings = get_settings()
    if not settings.suggested_questions_enabled:
        return
    coll_id = uuid.UUID(collection_id)
    log_ctx = log.bind(collection_id=collection_id)

    with sync_session() as session:
        snapshot = session.get(Collection, coll_id)
        if snapshot is None:
            return  # deleted while the task sat in the queue
        if expected_revision is not None and snapshot.suggestion_revision != expected_revision:
            return  # this queued trigger was superseded before execution
        data_version = snapshot.data_version
        excerpts = sample_excerpts(session, coll_id)
        locked_hint = locked_document_hint(session, coll_id, settings)

    if not excerpts:
        with sync_session() as session:
            collection = session.get(Collection, coll_id, with_for_update=True)
            if (
                collection is not None
                and collection.data_version == data_version
                and (
                    expected_revision is None or collection.suggestion_revision == expected_revision
                )
            ):
                collection.suggested_questions = [dict(locked_hint)] if locked_hint else None
        log_ctx.info("suggestions_cleared", reason="no_ready_chunks")
        return

    # provider calls happen outside any DB session
    try:
        payer, operator = collection_billing(
            coll_id, data_version=data_version, expected_revision=expected_revision
        )
        questions, embeddings = _run_async(
            attributed(draft_candidates(settings, excerpts), payer, operator)
        )
    except (BudgetExceededError, BudgetUnavailableError) as exc:
        log_ctx.warning("suggestions_budget_blocked", code=exc.code)
        return
    except (EmbeddingError, GenerationError) as exc:
        log_ctx.warning(
            "suggestions_provider_unavailable",
            error_type=type(exc).__name__,
            attempt=self.request.retries,
        )
        if self.request.retries >= self.max_retries:
            log_ctx.warning("suggestions_gave_up")
            return
        raise self.retry(exc=exc, countdown=RETRY_BASE_SECONDS * 2**self.request.retries) from exc
    except Exception:
        log_ctx.error("suggestions_unexpected_error")
        return

    if not questions:
        # both attempts came back empty/garbled (DeepSeek hidden-reasoning quirk)
        log_ctx.warning("suggestions_empty_completion")
        return

    with sync_session() as session:
        top = rank_questions(
            session, coll_id, questions, embeddings, settings.suggested_questions_count, settings
        )
        collection = session.get(Collection, coll_id, with_for_update=True)
        if (
            collection is None
            or collection.data_version != data_version
            or (
                expected_revision is not None
                and collection.suggestion_revision != expected_revision
            )
        ):
            return
        if locked_hint and not any(q["min_role"] != settings.access_default_role for q in top):
            top = top[: max(0, settings.suggested_questions_count - 1)] + [locked_hint]
        collection.suggested_questions = [dict(q) for q in top]
    log_ctx.info(
        "suggestions_stored",
        count=len(top),
    )
