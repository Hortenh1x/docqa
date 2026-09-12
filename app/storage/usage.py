"""Logical original-document capacity across every collection owned by an account."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Collection, Document

ACCOUNT_STORAGE_LIMIT_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class StorageUsage:
    used_bytes: int
    limit_bytes: int
    remaining_bytes: int
    document_count: int


async def storage_usage(db: AsyncSession, tenant_id: uuid.UUID) -> StorageUsage:
    """Every document row counts, independently of ingestion state or physical dedup."""
    used, count = (
        await db.execute(
            select(func.coalesce(func.sum(Document.size_bytes), 0), func.count(Document.id))
            .join(Collection, Document.collection_id == Collection.id)
            .where(Collection.tenant_id == tenant_id)
        )
    ).one()
    used_bytes = int(used)
    return StorageUsage(
        used_bytes=used_bytes,
        limit_bytes=ACCOUNT_STORAGE_LIMIT_BYTES,
        remaining_bytes=max(0, ACCOUNT_STORAGE_LIMIT_BYTES - used_bytes),
        document_count=int(count),
    )
