"""Collection CRUD."""

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentTenant, DbSession
from app.config import get_settings
from app.core.errors import DuplicateCollectionError
from app.core.rate_limit import rate_limit
from app.db.models import Collection

router = APIRouter(
    prefix="/v1/collections",
    tags=["collections"],
    dependencies=[Depends(rate_limit("default"))],
)

SLUG_RE = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100, pattern=SLUG_RE)


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    embedding_model: str
    created_at: datetime


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
async def list_collections(tenant: CurrentTenant, db: DbSession) -> list[Collection]:
    result = await db.execute(
        select(Collection).where(Collection.tenant_id == tenant.id).order_by(Collection.created_at)
    )
    return list(result.scalars().all())
