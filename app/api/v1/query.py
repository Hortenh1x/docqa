"""POST /v1/query — grounded answers with citations, streamed (SSE) or plain JSON.

SSE event order: ``meta`` → ``sources`` → ``delta``… → ``done`` (or ``error``).
Sources arrive before the first token on purpose: the user sees where the answer will
come from before the answer itself.
"""

import hashlib
import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentTenant, DbSession, collection_principal, fetch_collection
from app.billing.errors import BudgetExceededError, BudgetUnavailableError
from app.config import get_settings
from app.conversations.context import ConversationContext, load_conversation_context
from app.core.errors import (
    EmbeddingModelMismatchError,
    InvalidConversationParentError,
    ProviderUnavailableError,
    QueryPersistenceError,
    QuerySourceChangedError,
)
from app.core.idempotency import replay_headers, run_idempotent
from app.core.logging import get_request_id
from app.core.rate_limit import rate_limit
from app.db.base import get_sessionmaker
from app.db.models import Collection
from app.generation.service import (
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    QueryEvent,
    SourcesEvent,
    run_query,
)

router = APIRouter(prefix="/v1", tags=["query"])

_SSE_HEADERS = {
    "Cache-Control": "no-store",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class QueryRequest(BaseModel):
    collection_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    parent_query_id: uuid.UUID | None = None
    question: str = Field(min_length=1, max_length=4000)
    stream: bool = True
    # access levels: the trusted API client's claim about its end user. Chunks whose
    # label the role cannot see are filtered before retrieval. Omitted → the default
    # (least-privilege) role; unknown → 422 invalid_role. Roles: GET /v1/roles.
    role: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Caller's access role (see GET /v1/roles); defaults to the least-privileged role."
        ),
        examples=["employee", "leadership"],
    )


def _done_payload(event: DoneEvent) -> dict[str, Any]:
    return {
        "answer": event.answer,
        "refused": event.refused,
        "reason": event.reason,
        "confidence": round(event.confidence, 4) if event.confidence is not None else None,
        "usage": {
            "prompt_tokens": event.prompt_tokens,
            "completion_tokens": event.completion_tokens,
            "cost_usd": float(event.cost) if event.cost is not None else None,
        },
        "latency_ms": event.latency_ms,
        "model": event.model,
        "citations": event.citations,
        "outcome": event.outcome,
        "context": event.context,
    }


def _sse_frame(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _fingerprint(parts: list[Any], *, legacy_spacing: bool) -> str:
    serialized = json.dumps(parts) if legacy_spacing else json.dumps(parts, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


async def _sse_stream(events: AsyncGenerator[QueryEvent, None]) -> AsyncIterator[str]:
    async with aclosing(events):
        async for event in events:
            if isinstance(event, MetaEvent):
                yield _sse_frame(
                    "meta",
                    {
                        "query_id": str(event.query_id),
                        "access": event.access,
                        **({"context": event.context} if event.context is not None else {}),
                    },
                )
            elif isinstance(event, SourcesEvent):
                yield _sse_frame("sources", {"sources": event.sources})
            elif isinstance(event, DeltaEvent):
                yield _sse_frame("delta", {"text": event.text})
            elif isinstance(event, DoneEvent):
                yield _sse_frame("done", _done_payload(event))
            elif isinstance(event, ErrorEvent):
                yield _sse_frame(
                    "error",
                    {
                        "code": event.code,
                        "message": event.message,
                        "request_id": get_request_id(),
                        **(event.extra or {}),
                        **(
                            {"retry_after_s": int(event.headers["Retry-After"])}
                            if event.headers and "Retry-After" in event.headers
                            else {}
                        ),
                    },
                )


async def _collect_json(events: AsyncGenerator[QueryEvent, None]) -> dict[str, Any]:
    query_id: uuid.UUID | None = None
    access: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = []
    async with aclosing(events):
        async for event in events:
            if isinstance(event, MetaEvent):
                query_id = event.query_id
                access = event.access
            elif isinstance(event, SourcesEvent):
                sources = event.sources
            elif isinstance(event, ErrorEvent):
                if event.code == "quota_exceeded":
                    raise BudgetExceededError(
                        event.message, headers=event.headers, **(event.extra or {})
                    )
                if event.code == "budget_unavailable":
                    raise BudgetUnavailableError(
                        event.message, headers=event.headers, **(event.extra or {})
                    )
                if event.code == "query_persistence_failed":
                    raise QueryPersistenceError(event.message)
                if event.code == "query_source_changed":
                    raise QuerySourceChangedError(event.message)
                raise ProviderUnavailableError(event.message)
            elif isinstance(event, DoneEvent):
                return {
                    "query_id": str(query_id) if query_id else None,
                    "access": access,
                    "sources": sources,
                    **_done_payload(event),
                }
        raise ProviderUnavailableError("Query pipeline ended without a result.")


@router.post(
    "/query",
    response_model=None,
    dependencies=[Depends(rate_limit("query"))],
    responses={
        409: {"description": "Embedding model mismatch, or the Idempotency-Key is in flight"},
        422: {"description": "Unknown role, or the Idempotency-Key was reused for another request"},
        429: {"description": "Query rate limit or daily query quota exceeded (see Retry-After)"},
        503: {"description": "Embedding or LLM provider unavailable"},
    },
    description=(
        "Answers strictly from the collection's documents, with [n] citations. "
        "`stream=true` returns SSE (`meta → sources → delta… → done`); `stream=false` "
        "returns one JSON body and supports the `Idempotency-Key` header. Streams have "
        "no idempotency semantics — the header is ignored when streaming. "
        "`role` selects the access level: passages labelled for other roles are filtered "
        "before retrieval; `meta.access` reports the role and, in reveal mode, how many "
        "relevant passages it could not see."
    ),
)
async def query(
    payload: QueryRequest,
    tenant: CurrentTenant,
    db: DbSession,
    response: Response,
    request: Request,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> StreamingResponse | JSONResponse:
    if payload.parent_query_id is not None and payload.conversation_id is None:
        raise InvalidConversationParentError("parent_query_id requires conversation_id.")
    collection = await fetch_collection(db, tenant.id, payload.collection_id, request.state.actor)
    settings = get_settings()
    if collection.embedding_model != settings.embedding_model_id:
        raise EmbeddingModelMismatchError(
            f"Collection is pinned to '{collection.embedding_model}' but the server "
            f"currently embeds with '{settings.embedding_model_id}'.",
            collection_embedding_model=collection.embedding_model,
        )

    principal = await collection_principal(db, collection, request.state.actor, payload.role)
    conversation_context: ConversationContext | None = None
    if payload.conversation_id is not None:
        conversation_context = await load_conversation_context(
            db,
            request,
            request.state.actor,
            collection.id,
            payload.conversation_id,
            payload.parent_query_id,
            principal,
            settings,
        )

    # responses constructed below replace the injected Response — carry over the
    # rate-limit/quota headers the dependency wrote into it
    limit_headers = dict(response.headers)
    tenant_id, collection_id = collection.tenant_id, collection.id
    data_version = collection.data_version
    await db.commit()  # release request dependency connection before generation

    def query_events() -> AsyncGenerator[QueryEvent, None]:
        args = (
            tenant_id,
            collection_id,
            payload.question,
            settings,
            principal,
            data_version,
        )
        if conversation_context is None:
            return run_query(*args)
        return run_query(*args, conversation_context=conversation_context)

    if payload.stream:
        return StreamingResponse(
            _sse_stream(query_events()),
            media_type="text/event-stream",
            headers={**_SSE_HEADERS, **limit_headers},
        )

    if idempotency_key is None:
        return JSONResponse(
            await _collect_json(query_events()),
            headers=limit_headers,
        )

    async def _handler() -> tuple[int, dict[str, Any]]:
        body = await _collect_json(query_events())
        return 200, body

    # Standalone calls retain the historic fingerprint. Contextual calls additionally bind
    # replay to the exact accepted head and source/access snapshot.
    fingerprint_parts: list[Any]
    if conversation_context is None:
        fingerprint_parts = [
            "query",
            str(collection_id),
            data_version,
            principal.role,
            sorted(principal.labels),
            settings.access_reveal_hidden,
            payload.question,
        ]
    else:
        fingerprint_parts = [
            "query",
            str(collection_id),
            data_version,
            conversation_context.source_generation,
            principal.role,
            sorted(principal.labels),
            settings.access_reveal_hidden,
            str(conversation_context.conversation_id),
            (
                str(conversation_context.parent_query_id)
                if conversation_context.parent_query_id is not None
                else None
            ),
            payload.question,
        ]
    fingerprint = _fingerprint(
        fingerprint_parts,
        legacy_spacing=conversation_context is None,
    )

    async def cache_valid() -> bool:
        async with get_sessionmaker()() as session:
            versions = (
                await session.execute(
                    select(Collection.data_version, Collection.source_generation).where(
                        Collection.id == collection_id, Collection.tenant_id == tenant_id
                    )
                )
            ).one_or_none()
            if versions is None or versions.data_version != data_version:
                return False
            return (
                conversation_context is None
                or versions.source_generation == conversation_context.source_generation
            )

    visitor_scope = None
    if request.state.actor.kind == "guest":
        if conversation_context is not None:
            visitor_scope = str(request.state.account_session.id)
        else:
            from app.accounts.limits import client_address
            from app.billing.context import current_billing_actor

            payer = current_billing_actor.get()
            visitor_scope = (
                payer.ip_digest
                if payer
                else hashlib.sha256(client_address(request).encode()).hexdigest()
            )
    result = await run_idempotent(
        tenant.id,
        idempotency_key,
        _handler,
        fingerprint,
        cache_valid,
        visitor_scope=visitor_scope,
    )
    return JSONResponse(
        result.body,
        status_code=result.status,
        headers={**limit_headers, **(replay_headers(result) or {})},
    )
