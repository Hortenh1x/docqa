"""POST /v1/query — grounded answers with citations, streamed (SSE) or plain JSON.

SSE event order: ``meta`` → ``sources`` → ``delta``… → ``done`` (or ``error``).
Sources arrive before the first token on purpose: the user sees where the answer will
come from before the answer itself.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentTenant, DbSession, fetch_collection
from app.config import get_settings
from app.core.errors import EmbeddingModelMismatchError, ProviderUnavailableError
from app.core.idempotency import replay_headers, run_idempotent
from app.core.logging import get_request_id
from app.core.rate_limit import rate_limit
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


async def _sse_stream(events: AsyncIterator[QueryEvent]) -> AsyncIterator[str]:
    async for event in events:
        if isinstance(event, MetaEvent):
            yield _sse_frame("meta", {"query_id": str(event.query_id)})
        elif isinstance(event, SourcesEvent):
            yield _sse_frame("sources", {"sources": event.sources})
        elif isinstance(event, DeltaEvent):
            yield _sse_frame("delta", {"text": event.text})
        elif isinstance(event, DoneEvent):
            yield _sse_frame("done", _done_payload(event))
        elif isinstance(event, ErrorEvent):
            yield _sse_frame(
                "error",
                {"code": event.code, "message": event.message, "request_id": get_request_id()},
            )


async def _collect_json(events: AsyncIterator[QueryEvent]) -> dict[str, Any]:
    query_id: uuid.UUID | None = None
    sources: list[dict[str, Any]] = []
    async for event in events:
        if isinstance(event, MetaEvent):
            query_id = event.query_id
        elif isinstance(event, SourcesEvent):
            sources = event.sources
        elif isinstance(event, ErrorEvent):
            raise ProviderUnavailableError(event.message)
        elif isinstance(event, DoneEvent):
            return {
                "query_id": str(query_id) if query_id else None,
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
        429: {"description": "Query rate limit or daily query quota exceeded (see Retry-After)"},
        503: {"description": "Embedding or LLM provider unavailable"},
    },
    description=(
        "Answers strictly from the collection's documents, with [n] citations. "
        "`stream=true` returns SSE (`meta → sources → delta… → done`); `stream=false` "
        "returns one JSON body and supports the `Idempotency-Key` header. Streams have "
        "no idempotency semantics — the header is ignored when streaming."
    ),
)
async def query(
    payload: QueryRequest,
    tenant: CurrentTenant,
    db: DbSession,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> StreamingResponse | JSONResponse:
    collection = await fetch_collection(db, tenant.id, payload.collection_id)
    settings = get_settings()
    if collection.embedding_model != settings.embedding_model_id:
        raise EmbeddingModelMismatchError(
            f"Collection is pinned to '{collection.embedding_model}' but the server "
            f"currently embeds with '{settings.embedding_model_id}'.",
            collection_embedding_model=collection.embedding_model,
        )

    # responses constructed below replace the injected Response — carry over the
    # rate-limit/quota headers the dependency wrote into it
    limit_headers = dict(response.headers)
    tenant_id, collection_id = tenant.id, collection.id
    if payload.stream:
        events = run_query(tenant_id, collection_id, payload.question, settings)
        return StreamingResponse(
            _sse_stream(events),
            media_type="text/event-stream",
            headers={**_SSE_HEADERS, **limit_headers},
        )

    if idempotency_key is None:
        return JSONResponse(
            await _collect_json(run_query(tenant_id, collection_id, payload.question, settings)),
            headers=limit_headers,
        )

    async def _handler() -> tuple[int, dict[str, Any]]:
        body = await _collect_json(run_query(tenant_id, collection_id, payload.question, settings))
        return 200, body

    result = await run_idempotent(tenant_id, idempotency_key, _handler)
    return JSONResponse(
        result.body,
        status_code=result.status,
        headers={**limit_headers, **(replay_headers(result) or {})},
    )
