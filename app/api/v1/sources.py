"""External sources of a collection (Notion): create, list, sync, delete."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentCollection, CurrentTenant, DbSession, require_write_access
from app.billing.context import current_billing_actor
from app.core.errors import NotFoundError
from app.core.rate_limit import rate_limit
from app.db.models import Source
from app.sources import service

router = APIRouter(prefix="/v1", tags=["sources"], dependencies=[Depends(rate_limit("default"))])


class SourceCreate(BaseModel):
    kind: Literal["notion", "stub"] = "notion"
    name: str = Field(min_length=1, max_length=120)
    # Notion internal integration token (secret_... / ntn_...); stored encrypted, never returned
    token: str = Field(min_length=1, max_length=512)
    # Notion page/database ids or URLs; empty = everything shared with the integration
    root_ids: list[str] = Field(default_factory=list, max_length=50)
    # null = manual sync only; otherwise the worker re-syncs at this cadence
    auto_sync_interval_s: int | None = Field(default=None, ge=300, le=7 * 86400)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID
    kind: str
    name: str
    root_ids: list[str] = []
    auto_sync_interval_s: int | None
    sync_status: str
    last_sync_started_at: datetime | None
    last_sync_at: datetime | None
    last_sync_error: str | None
    last_sync_stats: dict[str, Any] | None
    document_count: int = 0
    created_at: datetime


def _out(source: Source, count: int) -> SourceOut:
    return SourceOut.model_validate(source).model_copy(
        update={
            "root_ids": list((source.config or {}).get("root_ids") or []),
            "document_count": count,
        }
    )


@router.post(
    "/collections/{collection_id}/sources",
    status_code=201,
    response_model=SourceOut,
    responses={
        422: {"description": "Credentials rejected by the source, or invalid root ids"},
        503: {
            "description": "Sources disabled (SOURCE_CREDENTIALS_KEY unset) or source unreachable"
        },
    },
)
async def create_source(
    payload: SourceCreate,
    collection: CurrentCollection,
    tenant: CurrentTenant,
    db: DbSession,
    request: Request,
) -> SourceOut:
    require_write_access(request, collection)
    payer = current_billing_actor.get()
    source = await service.create_source(
        db,
        collection,
        request.state.actor,
        kind=payload.kind,
        name=payload.name,
        token=payload.token,
        root_ids=payload.root_ids,
        auto_sync_interval_s=payload.auto_sync_interval_s,
        billing_ip_digest=payer.ip_digest if payer else None,
    )
    return _out(source, 0)


@router.get("/collections/{collection_id}/sources", response_model=list[SourceOut])
async def list_sources(
    collection: CurrentCollection, tenant: CurrentTenant, db: DbSession
) -> list[SourceOut]:
    if collection.tenant_id != tenant.id:
        return []  # public collections expose no operator sources
    sources = list(
        (
            await db.scalars(
                select(Source)
                .where(Source.collection_id == collection.id, Source.tenant_id == tenant.id)
                .order_by(Source.created_at)
            )
        ).all()
    )
    counts = await service.document_counts(db, [s.id for s in sources])
    return [_out(s, counts.get(s.id, 0)) for s in sources]


@router.get("/sources/{source_id}", response_model=SourceOut)
async def get_source(source_id: uuid.UUID, tenant: CurrentTenant, db: DbSession) -> SourceOut:
    source = await service.fetch_source(db, tenant.id, source_id)
    counts = await service.document_counts(db, [source.id])
    return _out(source, counts.get(source.id, 0))


@router.post(
    "/sources/{source_id}/sync",
    status_code=202,
    response_model=SourceOut,
    responses={409: {"description": "A sync is already queued or running"}},
)
async def sync_source(
    source_id: uuid.UUID, tenant: CurrentTenant, db: DbSession, request: Request
) -> SourceOut:
    source = await service.fetch_source(db, tenant.id, source_id)
    collection = await _owned_collection(db, source, tenant.id)
    require_write_access(request, collection)
    await service.request_sync(db, source)
    counts = await service.document_counts(db, [source.id])
    return _out(source, counts.get(source.id, 0))


@router.delete("/sources/{source_id}", status_code=204, response_class=Response)
async def delete_source(
    source_id: uuid.UUID, tenant: CurrentTenant, db: DbSession, request: Request
) -> None:
    source = await service.fetch_source(db, tenant.id, source_id)
    collection = await _owned_collection(db, source, tenant.id)
    require_write_access(request, collection)
    await service.delete_source(db, source)


async def _owned_collection(db: DbSession, source: Source, tenant_id: uuid.UUID) -> Any:
    from app.db.models import Collection

    collection = await db.scalar(
        select(Collection).where(
            Collection.id == source.collection_id, Collection.tenant_id == tenant_id
        )
    )
    if collection is None:
        raise NotFoundError("Collection not found.")
    return collection
