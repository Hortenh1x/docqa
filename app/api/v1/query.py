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
from app.core.errors import EmbeddingModelMismatchError, ProviderUnavailableError
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
    }


def _sse_frame(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _sse_stream(events: AsyncGenerator[QueryEvent, None]) -> AsyncIterator[str]:
    async with aclosing(events):
        async for event in events:
            if isinstance(event, MetaEvent):
                yield _sse_frame("meta", {"query_id": str(event.query_id), "access": event.access})
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
    collection = await fetch_collection(db, tenant.id, payload.collection_id, request.state.actor)
    settings = get_settings()
    if collection.embedding_model != settings.embedding_model_id:
        raise EmbeddingModelMismatchError(
            f"Collection is pinned to '{collection.embedding_model}' but the server "
            f"currently embeds with '{settings.embedding_model_id}'.",
            collection_embedding_model=collection.embedding_model,
        )

    principal = await collection_principal(db, collection, request.state.actor, payload.role)

    # responses constructed below replace the injected Response — carry over the
    # rate-limit/quota headers the dependency wrote into it
    limit_headers = dict(response.headers)
    tenant_id, collection_id = collection.tenant_id, collection.id
    data_version = collection.data_version
    await db.commit()  # release request dependency connection before generation
    if payload.stream:
        events = run_query(
            tenant_id, collection_id, payload.question, settings, principal, data_version
        )
        return StreamingResponse(
            _sse_stream(events),
            media_type="text/event-stream",
            headers={**_SSE_HEADERS, **limit_headers},
        )

    if idempotency_key is None:
        return JSONResponse(
            await _collect_json(
                run_query(
                    tenant_id, collection_id, payload.question, settings, principal, data_version
                )
            ),
            headers=limit_headers,
        )

    async def _handler() -> tuple[int, dict[str, Any]]:
        body = await _collect_json(
            run_query(tenant_id, collection_id, payload.question, settings, principal, data_version)
        )
        return 200, body

    # the key is bound to (collection, role, question): a replay under another role
    # must not receive an answer produced with different access
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                "query",
                str(collection_id),
                data_version,
                principal.role,
                sorted(principal.labels),
                settings.access_reveal_hidden,
                payload.question,
            ]
        ).encode()
    ).hexdigest()

    async def cache_valid() -> bool:
        async with get_sessionmaker()() as session:
            return (
                await session.scalar(
                    select(Collection.data_version).where(
                        Collection.id == collection_id, Collection.tenant_id == tenant_id
                    )
                )
                == data_version
            )

    visitor_scope = None
    if request.state.actor.kind == "guest":
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
