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
from celery.exceptions import MaxRetriesExceededError

from app.config import get_settings
from app.db.models import Collection
from app.db.sync import sync_session
from app.embeddings.base import EmbeddingError
from app.generation.llm import GenerationError
from app.generation.suggestions import draft_candidates, rank_questions, sample_excerpts
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
def suggest_questions(self: Task, collection_id: str) -> None:
    settings = get_settings()
    if not settings.suggested_questions_enabled:
        return
    coll_id = uuid.UUID(collection_id)
    log_ctx = log.bind(collection_id=collection_id)

    with sync_session() as session:
        if session.get(Collection, coll_id) is None:
            return  # deleted while the task sat in the queue
        excerpts = sample_excerpts(session, coll_id)

    if not excerpts:
        with sync_session() as session:
            collection = session.get(Collection, coll_id)
            if collection is not None and collection.suggested_questions is not None:
                collection.suggested_questions = None
        log_ctx.info("suggestions_cleared", reason="no_ready_chunks")
        return

    # provider calls happen outside any DB session
    try:
        questions, embeddings = _run_async(draft_candidates(settings, excerpts))
    except (EmbeddingError, GenerationError) as exc:
        log_ctx.warning(
            "suggestions_provider_unavailable", error=str(exc), attempt=self.request.retries
        )
        try:
            raise self.retry(exc=exc, countdown=RETRY_BASE_SECONDS * 2**self.request.retries)
        except MaxRetriesExceededError:
            log_ctx.warning("suggestions_gave_up")
            return
    except Exception:
        log_ctx.exception("suggestions_unexpected_error")
        return

    if not questions:
        # both attempts came back empty/garbled (DeepSeek hidden-reasoning quirk)
        log_ctx.warning("suggestions_empty_completion")
        return

    with sync_session() as session:
        top = rank_questions(
            session, coll_id, questions, embeddings, settings.suggested_questions_count, settings
        )
        collection = session.get(Collection, coll_id)
        if collection is None:
            return
        collection.suggested_questions = [dict(q) for q in top]
    log_ctx.info(
        "suggestions_stored",
        count=len(top),
        questions=[f"{q['question']} [{q['min_role']}]" for q in top],
    )
