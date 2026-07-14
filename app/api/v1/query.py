"""POST /v1/query — grounded answers with citations, streamed (SSE) or plain JSON.

SSE event order: ``meta`` → ``sources`` → ``delta``… → ``done`` (or ``error``).
Sources arrive before the first token on purpose: the user sees where the answer will
come from before the answer itself.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentTenant, DbSession, fetch_collection
from app.config import get_settings
from app.core.errors import EmbeddingModelMismatchError, ProviderUnavailableError
from app.core.logging import get_request_id
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


@router.post("/query", response_model=None)
async def query(
    payload: QueryRequest, tenant: CurrentTenant, db: DbSession
) -> StreamingResponse | JSONResponse:
    collection = await fetch_collection(db, tenant.id, payload.collection_id)
    settings = get_settings()
    if collection.embedding_model != settings.embedding_model_id:
        raise EmbeddingModelMismatchError(
            f"Collection is pinned to '{collection.embedding_model}' but the server "
            f"currently embeds with '{settings.embedding_model_id}'.",
            collection_embedding_model=collection.embedding_model,
        )

    events = run_query(tenant.id, collection.id, payload.question, settings)
    if payload.stream:
        return StreamingResponse(
            _sse_stream(events), media_type="text/event-stream", headers=_SSE_HEADERS
        )
    return JSONResponse(await _collect_json(events))
