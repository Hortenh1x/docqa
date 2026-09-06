"""Label statistics for the API: which restricted labels a collection or document holds.

One grouped query per request — never a query per row.
"""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentStatus
from app.ingestion.access import KNOWN_LABELS, LABEL_ALL


def sort_labels(labels: Iterable[str]) -> list[str]:
    """Stable display order: the known labels in privilege order, unknown ones last."""
    order = {label: i for i, label in enumerate(KNOWN_LABELS)}
    return sorted(set(labels), key=lambda label: (order.get(label, len(order)), label))


async def restricted_labels_by_collection(
    db: AsyncSession, collection_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    if not collection_ids:
        return {}
    rows = (
        await db.execute(
            select(Document.collection_id, Chunk.access_label)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Document.collection_id.in_(list(collection_ids)),
                Document.status == DocumentStatus.READY,
                Chunk.access_label != LABEL_ALL,
            )
            .distinct()
        )
    ).all()
    found: dict[uuid.UUID, set[str]] = {}
    for collection_id, label in rows:
        found.setdefault(collection_id, set()).add(label)
    return {cid: sort_labels(labels) for cid, labels in found.items()}


async def restricted_labels_by_document(
    db: AsyncSession, document_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    if not document_ids:
        return {}
    rows = (
        await db.execute(
            select(Chunk.document_id, Chunk.access_label)
            .where(Chunk.document_id.in_(list(document_ids)), Chunk.access_label != LABEL_ALL)
            .distinct()
        )
    ).all()
    found: dict[uuid.UUID, set[str]] = {}
    for document_id, label in rows:
        found.setdefault(document_id, set()).add(label)
    return {did: sort_labels(labels) for did, labels in found.items()}
