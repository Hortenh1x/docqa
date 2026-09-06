"""Collection CRUD + ingestion progress/cost."""

import math
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.access.labels import restricted_labels_by_collection, sort_labels
from app.api.deps import CurrentCollection, CurrentTenant, DbSession
from app.config import get_settings
from app.core.errors import DuplicateCollectionError
from app.core.rate_limit import rate_limit
from app.db.models import Chunk, Collection, Document, DocumentStatus
from app.usage.costs import embedding_cost_usd, embedding_price_per_1m

router = APIRouter(
    prefix="/v1/collections",
    tags=["collections"],
    dependencies=[Depends(rate_limit("default"))],
)

SLUG_RE = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100, pattern=SLUG_RE)


class SuggestedQuestionOut(BaseModel):
    question: str
    # least-privileged access role that can answer it (GET /v1/roles); the UI shows a
    # lock when the current role is below it
    min_role: str


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    embedding_model: str
    read_only: bool
    # 3 LLM-drafted starter questions; null until the first ingestion settles
    suggested_questions: list[SuggestedQuestionOut] | None
    # restricted content labels present in the collection (empty = nothing restricted)
    access_labels: list[str] = []
    created_at: datetime


class AccessStatsOut(BaseModel):
    chunks_by_label: dict[str, int]
    restricted_chunks: int


class IngestStatusOut(BaseModel):
    pending: int
    processing: int
    ready: int
    failed: int
    embedded_tokens: int
    embedding_model: str
    price_per_1m_tokens: float | None
    embedding_cost_usd: float | None
    eta_seconds: int | None
    suggested_questions: list[SuggestedQuestionOut] | None
    access: AccessStatsOut


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or f"collection-{uuid.uuid4().hex[:8]}"


@router.post("", status_code=201, response_model=CollectionOut)
async def create_collection(
    payload: CollectionCreate, tenant: CurrentTenant, db: DbSession
) -> Collection:
    slug = payload.slug or _slugify(payload.name)
    collection = Collection(
        tenant_id=tenant.id,
        name=payload.name,
        slug=slug,
        # pinned at creation: chunks embedded with different models must never mix
        embedding_model=get_settings().embedding_model_id,
    )
    db.add(collection)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateCollectionError(
            f"A collection with slug '{slug}' already exists.", slug=slug
        ) from None
    await db.refresh(collection)
    return collection


@router.get("", response_model=list[CollectionOut])
async def list_collections(tenant: CurrentTenant, db: DbSession) -> list[CollectionOut]:
    result = await db.execute(
        select(Collection).where(Collection.tenant_id == tenant.id).order_by(Collection.created_at)
    )
    collections = list(result.scalars().all())
    labels = await restricted_labels_by_collection(db, [c.id for c in collections])
    return [
        CollectionOut.model_validate(c).model_copy(update={"access_labels": labels.get(c.id, [])})
        for c in collections
    ]


@router.get(
    "/{collection_id}/ingest-status",
    response_model=IngestStatusOut,
    description=(
        "Ingestion progress and cost for a collection: document counts by status, "
        "tokens embedded so far priced at the collection's embedding model, an ETA "
        "for the in-flight documents (from recently measured throughput), and the "
        "suggested questions once they are generated."
    ),
)
async def ingest_status(collection: CurrentCollection, db: DbSession) -> IngestStatusOut:
    rows = (
        await db.execute(
            select(
                Document.status,
                func.count(),
                func.coalesce(func.sum(Document.size_bytes), 0),
            )
            .where(Document.collection_id == collection.id)
            .group_by(Document.status)
        )
    ).all()
    counts = {status: int(n) for status, n, _ in rows}
    queued_bytes = sum(int(b) for status, _, b in rows if status in ("pending", "processing"))

    embedded_tokens = (
        await db.execute(
            select(func.coalesce(func.sum(Chunk.token_count), 0))
            .select_from(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Document.collection_id == collection.id,
                Document.status == DocumentStatus.READY,
            )
        )
    ).scalar_one()

    eta_seconds: int | None = None
    if queued_bytes:
        # end-to-end throughput (bytes/s, queue wait included) over the last 20 ready
        # documents of this deployment; deliberately cross-tenant — only this scalar
        # rate leaves the DB, no tenant data does
        recent = (
            select(Document.size_bytes, Document.created_at, Document.processed_at)
            .where(
                Document.status == DocumentStatus.READY,
                Document.processed_at.isnot(None),
                Document.processed_at > Document.created_at,
            )
            .order_by(Document.processed_at.desc())
            .limit(20)
            .subquery()
        )
        throughput = (
            await db.execute(
                select(
                    func.sum(recent.c.size_bytes)
                    / func.nullif(
                        func.sum(
                            func.extract("epoch", recent.c.processed_at - recent.c.created_at)
                        ),
                        0,
                    )
                )
            )
        ).scalar()
        if throughput:
            eta_seconds = max(1, math.ceil(queued_bytes / float(throughput)))

    label_rows = (
        await db.execute(
            select(Chunk.access_label, func.count())
            .select_from(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Document.collection_id == collection.id,
                Document.status == DocumentStatus.READY,
            )
            .group_by(Chunk.access_label)
        )
    ).all()
    chunks_by_label = {label: int(n) for label, n in label_rows}
    access = AccessStatsOut(
        chunks_by_label={label: chunks_by_label[label] for label in sort_labels(chunks_by_label)},
        restricted_chunks=sum(n for label, n in chunks_by_label.items() if label != "all"),
    )

    price = embedding_price_per_1m(collection.embedding_model)
    cost = embedding_cost_usd(collection.embedding_model, int(embedded_tokens))
    return IngestStatusOut(
        pending=counts.get("pending", 0),
        processing=counts.get("processing", 0),
        ready=counts.get("ready", 0),
        failed=counts.get("failed", 0),
        embedded_tokens=int(embedded_tokens),
        embedding_model=collection.embedding_model,
        price_per_1m_tokens=float(price) if price is not None else None,
        embedding_cost_usd=float(cost) if cost is not None else None,
        eta_seconds=eta_seconds,
        suggested_questions=collection.suggested_questions,
        access=access,
    )
