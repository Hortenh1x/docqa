"""Query pipeline: retrieve → gate → context → LLM stream → citations → record.

Emits typed events consumed by the API layer (SSE or collected JSON):

    MetaEvent → [SourcesEvent → DeltaEvent…] → DoneEvent   (or ErrorEvent)

Design points, deliberate:
- The refusal gate runs BEFORE the LLM: an off-corpus question costs $0.
- Sources are emitted before the first token — the user sees where the answer will come
  from earlier than the answer itself.
- No DB connection is held while the LLM streams; retrieval and recording use their own
  short sessions.
- The query row is recorded no matter how the stream ends (client disconnects included):
  recording runs in a finally under a cancellation shield.
"""

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import anyio
import structlog

from app.config import Settings
from app.db.base import get_sessionmaker
from app.db.models import Query, QueryCitation
from app.embeddings.base import EmbeddingError
from app.generation.citations import finalize_answer
from app.generation.llm import GenerationError, StreamUsage, TextDelta, get_llm_provider
from app.generation.prompts import (
    SYSTEM_PROMPT,
    ContextBlock,
    build_context_blocks,
    build_user_prompt,
)
from app.generation.sentinel import SentinelBuffer
from app.retrieval.service import retrieve
from app.usage.costs import cost_usd

log = structlog.get_logger("docqa.query")

REFUSAL_REASON = "not_in_documents"
EMPTY_COMPLETION_REASON = "empty_completion"


@dataclass(frozen=True)
class MetaEvent:
    query_id: uuid.UUID


@dataclass(frozen=True)
class SourcesEvent:
    sources: list[dict[str, Any]]


@dataclass(frozen=True)
class DeltaEvent:
    text: str


@dataclass(frozen=True)
class DoneEvent:
    answer: str | None
    refused: bool
    reason: str | None
    confidence: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cost: Decimal | None
    latency_ms: int
    model: str | None


@dataclass(frozen=True)
class ErrorEvent:
    code: str
    message: str


QueryEvent = MetaEvent | SourcesEvent | DeltaEvent | DoneEvent | ErrorEvent


def _source_payload(block: ContextBlock) -> dict[str, Any]:
    chunk = block.chunk
    pages = [chunk.page_start, chunk.page_end] if chunk.page_start is not None else None
    return {
        "n": block.n,
        "document_id": str(chunk.document_id),
        "filename": chunk.filename,
        "pages": pages,
        "section": chunk.section_path,
        "snippet": chunk.content[:300],
        "score": round(chunk.score, 4),
    }


async def _record_query(
    *,
    query_id: uuid.UUID,
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID,
    question: str,
    answer: str | None,
    refused: bool,
    confidence: float | None,
    latency_ms: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cost: Decimal | None,
    model: str | None,
    blocks: list[ContextBlock],
) -> None:
    """Best-effort, shielded from cancellation: stats must survive client disconnects."""
    try:
        with anyio.CancelScope(shield=True):
            async with get_sessionmaker()() as session:
                session.add(
                    Query(
                        id=query_id,
                        tenant_id=tenant_id,
                        collection_id=collection_id,
                        question=question,
                        answer=answer,
                        refused=refused,
                        confidence=confidence,
                        latency_ms=latency_ms,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=cost,
                        model=model,
                    )
                )
                session.add_all(
                    QueryCitation(
                        query_id=query_id, rank=b.n, chunk_id=b.chunk.chunk_id, score=b.chunk.score
                    )
                    for b in blocks
                )
                await session.commit()
    except Exception:
        log.exception("query_record_failed", query_id=str(query_id))


async def run_query(
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID,
    question: str,
    settings: Settings,
) -> AsyncIterator[QueryEvent]:
    query_id = uuid.uuid4()
    started = time.perf_counter()
    log_ctx = log.bind(query_id=str(query_id))

    def latency_ms() -> int:
        return round((time.perf_counter() - started) * 1000)

    try:
        retrieval = await retrieve(collection_id, question, settings)
    except EmbeddingError as exc:
        log_ctx.warning("query_embedding_unavailable", error=str(exc))
        yield ErrorEvent(code="provider_unavailable", message="Embedding provider unavailable.")
        return

    yield MetaEvent(query_id=query_id)

    # retrieval gate: an off-corpus question is refused before the LLM — it costs nothing
    if not retrieval.chunks or (
        retrieval.top_score is not None and retrieval.top_score < settings.refusal_threshold
    ):
        log_ctx.info("query_refused_at_gate", top_score=retrieval.top_score)
        # record BEFORE the final yield: a JSON-mode collector stops consuming at `done`,
        # so code after this yield would never run
        await _record_query(
            query_id=query_id,
            tenant_id=tenant_id,
            collection_id=collection_id,
            question=question,
            answer=None,
            refused=True,
            confidence=retrieval.top_score,
            latency_ms=latency_ms(),
            prompt_tokens=None,
            completion_tokens=None,
            cost=None,
            model=None,
            blocks=[],
        )
        yield DoneEvent(
            answer=None,
            refused=True,
            reason=REFUSAL_REASON,
            confidence=retrieval.top_score,
            prompt_tokens=None,
            completion_tokens=None,
            cost=None,
            latency_ms=latency_ms(),
            model=None,
        )
        return

    blocks = build_context_blocks(
        retrieval.chunks, settings.context_token_budget, settings.context_chunk_max_tokens
    )
    yield SourcesEvent(sources=[_source_payload(b) for b in blocks])

    llm = get_llm_provider(settings)
    sentinel = SentinelBuffer()
    parts: list[str] = []
    usage: StreamUsage | None = None
    recorded = False

    async def record_once(
        *, answer: str | None, refused: bool, cost: Decimal | None, model: str | None
    ) -> None:
        nonlocal recorded
        if recorded:
            return
        recorded = True
        await _record_query(
            query_id=query_id,
            tenant_id=tenant_id,
            collection_id=collection_id,
            question=question,
            answer=answer,
            refused=refused,
            confidence=retrieval.top_score,
            latency_ms=latency_ms(),
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            cost=cost,
            model=model,
            blocks=blocks,
        )

    try:
        try:
            async for event in llm.stream(SYSTEM_PROMPT, build_user_prompt(blocks, question)):
                if isinstance(event, TextDelta):
                    releasable = sentinel.feed(event.text)
                    if releasable:
                        parts.append(releasable)
                        yield DeltaEvent(text=releasable)
                elif isinstance(event, StreamUsage):
                    usage = event
            tail = sentinel.flush()
            if tail:
                parts.append(tail)
                yield DeltaEvent(text=tail)
        except GenerationError as exc:
            log_ctx.warning("query_generation_failed", error=str(exc))
            yield ErrorEvent(code="provider_unavailable", message="LLM provider unavailable.")
            return

        model = llm.model_name
        cost = cost_usd(
            model,
            usage.prompt_tokens if usage else None,
            usage.completion_tokens if usage else None,
        )

        if sentinel.refused:
            # generation gate: the model saw the context and said NO_ANSWER
            log_ctx.info("query_refused_by_model")
            await record_once(answer=None, refused=True, cost=cost, model=model)
            yield DoneEvent(
                answer=None,
                refused=True,
                reason=REFUSAL_REASON,
                confidence=retrieval.top_score,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                cost=cost,
                latency_ms=latency_ms(),
                model=model,
            )
            return

        raw = "".join(parts)
        if not raw.strip():
            # empty completion: the provider spent the whole budget on hidden reasoning
            # or returned a zero-token stream — a blank non-refusal would reach the
            # client as an empty answer, so convert it to an honest refusal
            log_ctx.warning(
                "query_empty_completion",
                completion_tokens=usage.completion_tokens if usage else None,
            )
            await record_once(answer=None, refused=True, cost=cost, model=model)
            yield DoneEvent(
                answer=None,
                refused=True,
                reason=EMPTY_COMPLETION_REASON,
                confidence=retrieval.top_score,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                cost=cost,
                latency_ms=latency_ms(),
                model=model,
            )
            return

        answer, citations = finalize_answer(raw, blocks)
        log_ctx.info(
            "query_answered",
            citations=[c.n for c in citations],
            latency_ms=latency_ms(),
        )
        await record_once(answer=answer, refused=False, cost=cost, model=model)
        yield DoneEvent(
            answer=answer,
            refused=False,
            reason=None,
            confidence=retrieval.top_score,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            cost=cost,
            latency_ms=latency_ms(),
            model=model,
        )
    finally:
        # client disconnected mid-stream (or an unexpected error): keep the stats anyway
        await record_once(
            answer="".join(parts) or None,
            refused=False,
            cost=cost_usd(
                llm.model_name,
                usage.prompt_tokens if usage else None,
                usage.completion_tokens if usage else None,
            ),
            model=llm.model_name,
        )
