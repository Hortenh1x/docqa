"""Conversation history — an account's past exchanges, rebuilt from the query log.

Every query is recorded with its context blocks (`queries` + `query_citations`), so the
Ask screen's thread for a signed-in user is a read of that log: question, answer,
refusal, usage, and the sources with their pinpoint quotes. Guests keep their thread in
the browser instead (an IP digest is shared behind NAT) and, on sign-in, claim the rows
they asked as a guest by id — ids are unguessable and only the asking browser saw them.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field
from sqlalchemy import select, tuple_, update

from app.accounts.actor import Actor
from app.accounts.errors import AuthenticationError
from app.api.deps import CurrentCollection, CurrentTenant, DbSession
from app.core.rate_limit import rate_limit
from app.db.models import Chunk, Collection, Document, Query, QueryCitation
from app.generation.prompts import ContextBlock
from app.generation.quotes import resolve_quotes
from app.generation.service import EMPTY_COMPLETION_REASON, REFUSAL_REASON
from app.retrieval.base import RetrievedChunk

router = APIRouter(prefix="/v1", tags=["history"])


class QuoteSpan(BaseModel):
    start: int
    end: int
    text: str


class HistorySource(BaseModel):
    n: int
    document_id: uuid.UUID
    filename: str
    pages: list[int] | None
    section: str | None
    snippet: str
    score: float | None
    access_label: str
    chunk_id: int
    chunk_index: int
    # the full passage and its highlighted spans — cited blocks only
    content: str | None = None
    quotes: list[QuoteSpan] | None = None


class HistoryUsage(BaseModel):
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None


class HistoryQuery(BaseModel):
    id: uuid.UUID
    question: str
    answer: str | None
    refused: bool
    reason: str | None
    role: str | None
    confidence: float | None
    usage: HistoryUsage
    latency_ms: int | None
    model: str | None
    created_at: datetime
    sources: list[HistorySource]


class HistoryPage(BaseModel):
    # newest first; page backwards with `before=<id of the oldest item shown>`
    queries: list[HistoryQuery]
    has_more: bool


class ClaimRequest(BaseModel):
    query_ids: list[uuid.UUID] = Field(max_length=200)


class ClaimResult(BaseModel):
    claimed: int


def _to_source(
    citation: QueryCitation, chunk: Chunk, filename: str, answer: str | None
) -> dict[str, Any]:
    pages = (
        [chunk.page_start, chunk.page_end if chunk.page_end is not None else chunk.page_start]
        if chunk.page_start is not None
        else None
    )
    source: dict[str, Any] = {
        "n": citation.rank,
        "document_id": chunk.document_id,
        "filename": filename,
        "pages": pages,
        "section": chunk.section_path,
        "snippet": chunk.content[:300],
        "score": citation.score,
        "access_label": chunk.access_label,
        "chunk_id": chunk.id,
        "chunk_index": chunk.chunk_index,
    }
    spans = citation.quotes
    if spans is None and answer and f"[{citation.rank}]" in answer:
        # recorded before pinpoint quotes existed: derive the best-overlapping sentence now
        retrieved = RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            content=chunk.content,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_path=chunk.section_path,
            score=citation.score or 0.0,
        )
        block = ContextBlock(n=citation.rank, chunk=retrieved, text=chunk.content)
        spans = [
            {"start": q.start, "end": q.end}
            for q in resolve_quotes("", answer, [block]).get(citation.rank, [])
        ]
    if spans is not None:
        source["content"] = chunk.content
        source["quotes"] = [
            {"start": s["start"], "end": s["end"], "text": chunk.content[s["start"] : s["end"]]}
            for s in spans
        ]
    return source


@router.get(
    "/collections/{collection_id}/queries",
    response_model=HistoryPage,
    dependencies=[Depends(rate_limit("default"))],
    description=(
        "The caller's own past questions in this collection, newest first, with answers and "
        "the sources each answer cited (full passage + pinpoint quote spans). Page backwards "
        "with `before`. Guests get an empty page: their thread lives in the browser. An API "
        "key sees its tenant's whole query log for the collection."
    ),
)
async def list_queries(
    collection: CurrentCollection,
    db: DbSession,
    request: Request,
    limit: Annotated[int, QueryParam(ge=1, le=100)] = 20,
    before: Annotated[uuid.UUID | None, QueryParam()] = None,
) -> HistoryPage:
    actor: Actor = request.state.actor
    if actor.kind == "guest":
        return HistoryPage(queries=[], has_more=False)
    scope = [Query.collection_id == collection.id]
    if actor.kind == "account":
        scope.append(Query.user_id == actor.user_id)
    else:
        scope.append(Query.tenant_id == actor.tenant_id)
    if before is not None:
        anchor = (
            await db.execute(select(Query.created_at, Query.id).where(Query.id == before, *scope))
        ).first()
        if anchor is None:
            return HistoryPage(queries=[], has_more=False)
        scope.append(tuple_(Query.created_at, Query.id) < tuple_(anchor[0], anchor[1]))
    rows = list(
        (
            await db.execute(
                select(Query)
                .where(*scope)
                .order_by(Query.created_at.desc(), Query.id.desc())
                .limit(limit + 1)
            )
        ).scalars()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    sources: dict[uuid.UUID, list[dict[str, Any]]] = {q.id: [] for q in rows}
    if rows:
        cited = (
            await db.execute(
                select(QueryCitation, Chunk, Document.filename)
                .join(Chunk, QueryCitation.chunk_id == Chunk.id)
                .join(Document, Chunk.document_id == Document.id)
                .where(QueryCitation.query_id.in_(list(sources)))
                .order_by(QueryCitation.query_id, QueryCitation.rank)
            )
        ).all()
        answers = {q.id: q.answer for q in rows}
        for citation, chunk, filename in cited:
            sources[citation.query_id].append(
                _to_source(citation, chunk, filename, answers[citation.query_id])
            )
    return HistoryPage(
        queries=[
            HistoryQuery(
                id=q.id,
                question=q.question,
                answer=q.answer,
                refused=q.refused,
                reason=(
                    None
                    if not q.refused
                    else EMPTY_COMPLETION_REASON
                    if q.model is not None and q.completion_tokens
                    else REFUSAL_REASON
                ),
                role=q.role,
                confidence=q.confidence,
                usage=HistoryUsage(
                    prompt_tokens=q.prompt_tokens,
                    completion_tokens=q.completion_tokens,
                    cost_usd=float(q.cost_usd) if q.cost_usd is not None else None,
                ),
                latency_ms=q.latency_ms,
                model=q.model,
                created_at=q.created_at,
                sources=[HistorySource.model_validate(s) for s in sources[q.id]],
            )
            for q in rows
        ],
        has_more=has_more,
    )


@router.post(
    "/queries/claim",
    response_model=ClaimResult,
    dependencies=[Depends(rate_limit("default"))],
    description=(
        "Attach queries asked as a guest to the signed-in account, so the thread survives "
        "sign-in. Only rows without an owner move, and only in public collections; ids are "
        "the unguessable `query_id`s the asking browser received."
    ),
)
async def claim_queries(
    payload: ClaimRequest, tenant: CurrentTenant, db: DbSession, request: Request
) -> ClaimResult:
    actor: Actor = request.state.actor
    if actor.kind != "account" or actor.user_id is None:
        raise AuthenticationError("Sign in to keep your questions.")
    if not payload.query_ids:
        return ClaimResult(claimed=0)
    claimed = list(
        (
            await db.execute(
                update(Query)
                .where(
                    Query.id.in_(payload.query_ids),
                    Query.user_id.is_(None),
                    Query.collection_id.in_(
                        select(Collection.id).where(Collection.is_public.is_(True))
                    ),
                )
                .values(user_id=actor.user_id)
                .returning(Query.id)
            )
        ).scalars()
    )
    await db.commit()
    return ClaimResult(claimed=len(claimed))
