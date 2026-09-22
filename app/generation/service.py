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
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import anyio
import structlog
from sqlalchemy import select

from app.access import Principal, resolve_principal
from app.billing.context import current_account_id, current_billing_actor
from app.billing.errors import BudgetExceededError, BudgetUnavailableError
from app.config import Settings
from app.conversations.context import ConversationContext
from app.conversations.normalizer import normalize_followup
from app.core.errors import NotFoundError
from app.db.base import get_sessionmaker
from app.db.models import Collection, Conversation, Query, QueryCitation
from app.embeddings.base import EmbeddingError
from app.generation.citations import finalize_answer
from app.generation.llm import (
    GenerationError,
    LLMProvider,
    StreamUsage,
    TextDelta,
    get_llm_provider,
)
from app.generation.prompts import (
    SYSTEM_PROMPT,
    ContextBlock,
    build_context_blocks,
    build_user_prompt,
)
from app.generation.quotes import Quote, QuoteSplitter, resolve_quotes
from app.generation.sentinel import SentinelBuffer
from app.retrieval.base import HiddenStats
from app.retrieval.planning import UsageAccumulator, plan_queries, round_robin_chunks
from app.retrieval.service import retrieve
from app.usage.costs import cost_usd

log = structlog.get_logger("docqa.query")

REFUSAL_REASON = "not_in_documents"
EMPTY_COMPLETION_REASON = "empty_completion"


@dataclass(frozen=True)
class MetaEvent:
    query_id: uuid.UUID
    # {"role", "hidden_passages", "hidden_labels", "hidden_documents", "hidden_outranking",
    # "hidden_truncated"} — hidden_* are null unless reveal mode
    access: dict[str, Any]
    context: dict[str, bool | int] | None = None


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
    # cited blocks only: {n, chunk_id, content, quotes: [{start, end, text}]} — the
    # pinpoint spans the client highlights (app/generation/quotes.py)
    citations: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "answered"
    context: dict[str, bool | int] = field(
        default_factory=lambda: {"reset": False, "turns_used": 0}
    )


@dataclass(frozen=True)
class ErrorEvent:
    code: str
    message: str
    headers: dict[str, str] | None = None
    extra: dict[str, Any] | None = None


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
        "access_label": chunk.access_label,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
    }


def citations_payload(
    blocks: list[ContextBlock], quotes: dict[int, list[Quote]]
) -> list[dict[str, Any]]:
    by_n = {b.n: b for b in blocks}
    return [
        {
            "n": n,
            "chunk_id": by_n[n].chunk.chunk_id,
            "content": by_n[n].chunk.content,
            "quotes": [
                {"start": q.start, "end": q.end, "text": by_n[n].chunk.content[q.start : q.end]}
                for q in spans
            ],
        }
        for n, spans in quotes.items()
        if n in by_n
    ]


def access_payload(principal: Principal, hidden: HiddenStats | None) -> dict[str, Any]:
    """What the client learns about access: its role, and — in reveal mode only — how many
    relevant passages it could not see and which labels would unlock them."""
    return {
        "role": principal.role,
        "hidden_passages": hidden.passages if hidden is not None else None,
        "hidden_labels": list(hidden.labels) if hidden is not None else None,
        "hidden_documents": hidden.documents if hidden is not None else None,
        "hidden_outranking": hidden.outranking if hidden is not None else None,
        "hidden_truncated": hidden.truncated if hidden is not None else None,
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
    role: str | None = None,
    data_version: int | None = None,
    quotes: dict[int, list[Quote]] | None = None,
    conversation_context: ConversationContext | None = None,
    outcome: str | None = None,
    outcome_reason: str | None = None,
    accepted_at: datetime | None = None,
) -> Literal["recorded", "source_changed", "failed"]:
    """Persist one terminal state in a short, cancellation-shielded transaction."""
    try:
        with anyio.CancelScope(shield=True):
            async with get_sessionmaker()() as session:
                if data_version is not None:
                    current = await session.scalar(
                        select(Collection.data_version)
                        .where(Collection.id == collection_id, Collection.tenant_id == tenant_id)
                        .with_for_update()
                    )
                    if current != data_version:
                        log.info("query_discarded_after_cleanup", query_id=str(query_id))
                        return "source_changed"
                owner_user_id = current_account_id.get()
                conversation: Conversation | None = None
                if conversation_context is not None:
                    conversation = await session.scalar(
                        select(Conversation)
                        .where(
                            Conversation.id == conversation_context.conversation_id,
                            Conversation.tenant_id == tenant_id,
                            Conversation.collection_id == collection_id,
                        )
                        .with_for_update()
                    )
                    if conversation is None:
                        log.error("query_conversation_missing", query_id=str(query_id))
                        return "failed"
                    owner_user_id = conversation.owner_user_id
                query_values: dict[str, Any] = {
                    "id": query_id,
                    "tenant_id": tenant_id,
                    "collection_id": collection_id,
                    "question": question,
                    "answer": answer,
                    "refused": refused,
                    "confidence": confidence,
                    "latency_ms": latency_ms,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost,
                    "model": model,
                    "role": role,
                    "conversation_id": (
                        conversation_context.conversation_id if conversation_context else None
                    ),
                    "parent_query_id": (
                        conversation_context.parent_query_id if conversation_context else None
                    ),
                    "outcome": outcome,
                    "outcome_reason": outcome_reason,
                    "source_generation": (
                        conversation_context.source_generation if conversation_context else None
                    ),
                    "access_fingerprint": (
                        conversation_context.access_fingerprint if conversation_context else None
                    ),
                    "context_reset": conversation_context.reset if conversation_context else False,
                    "user_id": owner_user_id,
                    "ip_digest": (
                        payer.ip_digest if (payer := current_billing_actor.get()) else None
                    ),
                }
                if conversation_context is not None and accepted_at is not None:
                    query_values["created_at"] = accepted_at
                session.add(Query(**query_values))
                session.add_all(
                    QueryCitation(
                        query_id=query_id,
                        rank=b.n,
                        chunk_id=b.chunk.chunk_id,
                        score=b.chunk.score,
                        quotes=(
                            [{"start": q.start, "end": q.end} for q in quotes[b.n]]
                            if quotes is not None and b.n in quotes
                            else None
                        ),
                    )
                    for b in blocks
                )
                if conversation is not None:
                    conversation.updated_at = datetime.now(UTC)
                await session.commit()
                return "recorded"
    except Exception as exc:
        log.error("query_record_failed", query_id=str(query_id), error_type=type(exc).__name__)
        return "failed"
    return "failed"


async def run_query(
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID,
    question: str,
    settings: Settings,
    principal: Principal | None = None,
    data_version: int | None = None,
    *,
    context_observer: Callable[[list[ContextBlock]], None] | None = None,
    conversation_context: ConversationContext | None = None,
) -> AsyncGenerator[QueryEvent, None]:
    if data_version is None:
        async with get_sessionmaker()() as session:
            data_version = await session.scalar(
                select(Collection.data_version).where(
                    Collection.id == collection_id, Collection.tenant_id == tenant_id
                )
            )
        if data_version is None:
            raise NotFoundError("Collection not found.")
    query_id = uuid.uuid4()
    accepted_at = datetime.now(UTC)
    started = time.perf_counter()
    principal = principal or resolve_principal(settings, None)
    log_ctx = log.bind(query_id=str(query_id), role=principal.role)

    def latency_ms() -> int:
        return round((time.perf_counter() - started) * 1000)

    llm: LLMProvider | None = None
    confidence: float | None = None
    blocks: list[ContextBlock] = []
    sentinel = SentinelBuffer()
    splitter = QuoteSplitter()
    parts: list[str] = []
    usage = UsageAccumulator()
    record_attempted = False
    recorded = False
    effective_question = question
    context_payload: dict[str, bool | int] = {
        "reset": conversation_context.reset if conversation_context else False,
        "turns_used": conversation_context.turns_used if conversation_context else 0,
    }
    meta_emitted = False

    async def record_once(
        *,
        answer: str | None,
        refused: bool,
        cost: Decimal | None,
        model: str | None,
        quotes: dict[int, list[Quote]] | None = None,
        outcome: str = "answered",
        reason: str | None = None,
    ) -> str | None:
        nonlocal record_attempted, recorded
        if record_attempted:
            return "recorded" if recorded else None
        record_attempted = True
        total_usage = usage.total
        result = await _record_query(
            query_id=query_id,
            tenant_id=tenant_id,
            collection_id=collection_id,
            data_version=data_version,
            question=question,
            answer=answer,
            refused=refused,
            confidence=confidence,
            latency_ms=latency_ms(),
            prompt_tokens=total_usage.prompt_tokens if total_usage else None,
            completion_tokens=total_usage.completion_tokens if total_usage else None,
            cost=cost,
            model=model,
            blocks=blocks,
            role=principal.role,
            quotes=quotes,
            conversation_context=conversation_context,
            outcome=outcome,
            outcome_reason=reason,
            accepted_at=accepted_at,
        )
        recorded = result == "recorded"
        return result

    def persistence_error(result: str | None) -> ErrorEvent | None:
        if conversation_context is None or result == "recorded":
            return None
        if result == "source_changed":
            return ErrorEvent(
                code="query_source_changed",
                message="Collection sources changed before the query could be saved. Please retry.",
            )
        return ErrorEvent(
            code="query_persistence_failed",
            message="The query could not be saved. Please retry.",
        )

    async def record_incomplete(outcome: str, reason: str) -> None:
        partial = "".join(parts)
        substantive_partial = partial if partial.strip() else None
        total_usage = usage.total
        model = llm.model_name if llm else None
        await record_once(
            answer=substantive_partial,
            refused=False,
            quotes=(
                resolve_quotes(splitter.section, substantive_partial, blocks)
                if substantive_partial
                else None
            ),
            cost=cost_usd(
                model,
                total_usage.prompt_tokens if total_usage else None,
                total_usage.completion_tokens if total_usage else None,
            ),
            model=model,
            outcome=outcome,
            reason=reason,
        )

    try:
        if conversation_context is not None and conversation_context.parent_query_id is not None:
            llm = get_llm_provider(settings)
            decision = await normalize_followup(
                llm,
                question,
                conversation_context,
                aggregate_usage=usage,
                max_output_chars=settings.conversation_normalizer_max_output_chars,
                max_question_chars=settings.conversation_normalizer_max_question_chars,
            )
            effective_question = decision.question
            if decision.action == "clarify":
                total_usage = usage.total
                model = llm.model_name
                cost = cost_usd(
                    model,
                    total_usage.prompt_tokens if total_usage else None,
                    total_usage.completion_tokens if total_usage else None,
                )
                yield MetaEvent(
                    query_id=query_id,
                    access=access_payload(principal, None),
                    context=context_payload,
                )
                meta_emitted = True
                yield SourcesEvent(sources=[])
                result = await record_once(
                    answer=decision.question,
                    refused=False,
                    cost=cost,
                    model=model,
                    outcome="clarification",
                    reason="context_clarification",
                )
                if error := persistence_error(result):
                    yield error
                    return
                yield DoneEvent(
                    answer=decision.question,
                    refused=False,
                    reason="context_clarification",
                    confidence=None,
                    prompt_tokens=total_usage.prompt_tokens if total_usage else None,
                    completion_tokens=total_usage.completion_tokens if total_usage else None,
                    cost=cost,
                    latency_ms=latency_ms(),
                    model=model,
                    outcome="clarification",
                    context=context_payload,
                )
                return
        try:
            retrieval = await retrieve(collection_id, effective_question, settings, principal)
        except EmbeddingError as exc:
            log_ctx.warning("query_embedding_unavailable", error_type=type(exc).__name__)
            await record_incomplete("failed", "provider_unavailable")
            if conversation_context is not None and not meta_emitted:
                yield MetaEvent(
                    query_id=query_id,
                    access=access_payload(principal, None),
                    context=context_payload,
                )
                meta_emitted = True
            yield ErrorEvent(code="provider_unavailable", message="Embedding provider unavailable.")
            return

        confidence = retrieval.top_score
        yield MetaEvent(
            query_id=query_id,
            access=access_payload(principal, retrieval.hidden),
            context=context_payload,
        )
        meta_emitted = True

        # retrieval gate: an off-corpus question is refused before the LLM — it costs nothing
        if not retrieval.chunks or (
            retrieval.top_score is not None and retrieval.top_score < settings.refusal_threshold
        ):
            log_ctx.info("query_refused_at_gate", top_score=retrieval.top_score)
            total_usage = usage.total
            gate_model: str | None = llm.model_name if llm is not None else None
            cost = cost_usd(
                gate_model,
                total_usage.prompt_tokens if total_usage else None,
                total_usage.completion_tokens if total_usage else None,
            )
            result = await record_once(
                answer=None,
                refused=True,
                cost=cost,
                model=gate_model,
                outcome="refused",
                reason=REFUSAL_REASON,
            )
            if error := persistence_error(result):
                yield error
                return
            yield DoneEvent(
                answer=None,
                refused=True,
                reason=REFUSAL_REASON,
                confidence=retrieval.top_score,
                prompt_tokens=total_usage.prompt_tokens if total_usage else None,
                completion_tokens=total_usage.completion_tokens if total_usage else None,
                cost=cost,
                latency_ms=latency_ms(),
                model=gate_model,
                outcome="refused",
                context=context_payload,
            )
            return

        facet_groups = []
        if settings.query_planning_enabled:
            llm = get_llm_provider(settings)
            try:
                planned, _ = await plan_queries(llm, effective_question, usage)
            except GenerationError as exc:
                log_ctx.warning("query_planning_failed", error_type=type(exc).__name__)
                planned = None
            if planned:
                for index, facet in enumerate(planned):
                    try:
                        facet_result = await retrieve(
                            collection_id,
                            facet,
                            settings,
                            principal,
                            reveal_hidden=False,
                        )
                    except EmbeddingError as exc:
                        log_ctx.warning(
                            "query_expansion_embedding_unavailable",
                            facet_index=index,
                            error_type=type(exc).__name__,
                        )
                        continue
                    facet_groups.append(facet_result.chunks)

        merged_chunks = round_robin_chunks([retrieval.chunks, *facet_groups], settings.rerank_top_n)
        blocks = build_context_blocks(
            merged_chunks, settings.context_token_budget, settings.context_chunk_max_tokens
        )
        # In-process eval only. HTTP callers never receive full context through this hook.
        if context_observer is not None:
            context_observer(blocks)
        yield SourcesEvent(sources=[_source_payload(b) for b in blocks])

        if llm is None:
            llm = get_llm_provider(settings)
        answer_prompt = build_user_prompt(
            blocks,
            question,
            effective_question if conversation_context is not None else None,
        )
        for attempt in range(2):
            sentinel = SentinelBuffer()
            splitter = QuoteSplitter()
            parts = []
            usage.start_attempt()
            answer_stream = llm.stream(SYSTEM_PROMPT, answer_prompt)
            try:
                try:
                    async for event in answer_stream:
                        if isinstance(event, TextDelta):
                            # head: NO_ANSWER interception; tail: the QUOTES section is kept
                            # for the citations and never reaches the client as answer text
                            visible = splitter.feed(sentinel.feed(event.text))
                            if visible:
                                parts.append(visible)
                                yield DeltaEvent(text=visible)
                        elif isinstance(event, StreamUsage):
                            usage.observe(event)
                finally:
                    close = getattr(answer_stream, "aclose", None)
                    if close is not None:
                        with anyio.CancelScope(shield=True):
                            await close()
                tail = splitter.feed(sentinel.flush()) + splitter.flush()
                if tail:
                    parts.append(tail)
                    yield DeltaEvent(text=tail)
            except GenerationError as exc:
                log_ctx.warning("query_generation_failed", error_type=type(exc).__name__)
                await record_incomplete("failed", "provider_unavailable")
                yield ErrorEvent(code="provider_unavailable", message="LLM provider unavailable.")
                return

            model = llm.model_name
            total_usage = usage.total
            cost = cost_usd(
                model,
                total_usage.prompt_tokens if total_usage else None,
                total_usage.completion_tokens if total_usage else None,
            )

            if sentinel.refused:
                # generation gate: the model saw the context and said NO_ANSWER
                log_ctx.info("query_refused_by_model")
                result = await record_once(
                    answer=None,
                    refused=True,
                    cost=cost,
                    model=model,
                    outcome="refused",
                    reason=REFUSAL_REASON,
                )
                if error := persistence_error(result):
                    yield error
                    return
                yield DoneEvent(
                    answer=None,
                    refused=True,
                    reason=REFUSAL_REASON,
                    confidence=retrieval.top_score,
                    prompt_tokens=total_usage.prompt_tokens if total_usage else None,
                    completion_tokens=total_usage.completion_tokens if total_usage else None,
                    cost=cost,
                    latency_ms=latency_ms(),
                    model=model,
                    outcome="refused",
                    context=context_payload,
                )
                return

            raw = "".join(parts)
            if raw.strip():
                break
            if attempt == 0:
                log_ctx.warning(
                    "query_empty_completion_retrying",
                    completion_tokens=(total_usage.completion_tokens if total_usage else None),
                )
                continue
            log_ctx.warning(
                "query_empty_completion_after_retry",
                completion_tokens=total_usage.completion_tokens if total_usage else None,
            )
            await record_incomplete("failed", EMPTY_COMPLETION_REASON)
            yield ErrorEvent(
                code="provider_unavailable",
                message="The LLM did not complete an answer. Please try again.",
            )
            return

        model = llm.model_name
        total_usage = usage.total
        cost = cost_usd(
            model,
            total_usage.prompt_tokens if total_usage else None,
            total_usage.completion_tokens if total_usage else None,
        )

        raw = "".join(parts)
        answer, citations = finalize_answer(raw, blocks)
        quotes = resolve_quotes(splitter.section, answer, blocks)
        log_ctx.info(
            "query_answered",
            citations=[c.n for c in citations],
            quote_methods={n: [q.method for q in spans] for n, spans in quotes.items()},
            latency_ms=latency_ms(),
        )
        result = await record_once(
            answer=answer,
            refused=False,
            cost=cost,
            model=model,
            quotes=quotes,
            outcome="answered",
        )
        if error := persistence_error(result):
            yield error
            return
        yield DoneEvent(
            answer=answer,
            refused=False,
            reason=None,
            confidence=retrieval.top_score,
            prompt_tokens=total_usage.prompt_tokens if total_usage else None,
            completion_tokens=total_usage.completion_tokens if total_usage else None,
            cost=cost,
            latency_ms=latency_ms(),
            model=model,
            citations=citations_payload(blocks, quotes),
            outcome="answered",
            context=context_payload,
        )
    except GenerationError as exc:
        log_ctx.warning("query_normalization_failed", error_type=type(exc).__name__)
        await record_incomplete("failed", "provider_unavailable")
        if conversation_context is not None and not meta_emitted:
            yield MetaEvent(
                query_id=query_id,
                access=access_payload(principal, None),
                context=context_payload,
            )
            meta_emitted = True
        yield ErrorEvent(code="provider_unavailable", message="LLM provider unavailable.")
    except (BudgetExceededError, BudgetUnavailableError) as exc:
        log_ctx.warning("query_budget_blocked", code=exc.code)
        await record_incomplete("failed", exc.code)
        if conversation_context is not None and not meta_emitted:
            yield MetaEvent(
                query_id=query_id,
                access=access_payload(principal, None),
                context=context_payload,
            )
            meta_emitted = True
        yield ErrorEvent(code=exc.code, message=exc.detail, headers=exc.headers, extra=exc.extra)
    except BaseException as exc:
        cancelled = isinstance(exc, (GeneratorExit, anyio.get_cancelled_exc_class()))
        await record_incomplete(
            "cancelled" if cancelled else "failed",
            "client_cancelled" if cancelled else "internal_error",
        )
        raise
    finally:
        if not record_attempted:
            await record_incomplete("cancelled", "client_cancelled")
