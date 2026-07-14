"""Vector search over pgvector's HNSW index (cosine)."""

import uuid
from typing import Any

from sqlalchemy import Row, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentStatus
from app.retrieval.base import RetrievedChunk


def _to_chunk(row: Row[Any]) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.id,
        document_id=row.document_id,
        filename=row.filename,
        content=row.content,
        page_start=row.page_start,
        page_end=row.page_end,
        section_path=row.section_path,
        score=float(row.score),
    )


async def vector_search(
    db: AsyncSession,
    collection_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    ef_search: int,
) -> list[RetrievedChunk]:
    # SET LOCAL lives and dies with the current transaction — it must precede the
    # search in the same one. int() guards the literal (SET does not take bind params).
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))

    distance = Chunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.page_start,
            Chunk.page_end,
            Chunk.section_path,
            Document.id.label("document_id"),
            Document.filename,
            (1 - distance).label("score"),  # cosine similarity
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(
            # tenant scope is enforced upstream (the collection is fetched tenant-scoped)
            Document.collection_id == collection_id,
            Document.status == DocumentStatus.READY,
        )
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await db.execute(stmt)).all()
    return [_to_chunk(row) for row in rows]
