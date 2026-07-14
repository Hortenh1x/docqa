"""Full-text search over the generated tsvector column.

``websearch_to_tsquery`` tolerates human input (quotes, OR, stray punctuation) and never
raises on garbage. The ``'simple'`` config matches the generated column (no stemming —
the corpus is bilingual EN+DE): FTS is our source of exact matches (IDs like "POL-004",
numbers); semantics is the vector's job. An empty result is normal, not an error.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentStatus
from app.retrieval.base import RetrievedChunk
from app.retrieval.vector import _to_chunk


async def fulltext_search(
    db: AsyncSession,
    collection_id: uuid.UUID,
    question: str,
    top_k: int,
) -> list[RetrievedChunk]:
    tsquery = func.websearch_to_tsquery("simple", question)
    score = func.ts_rank_cd(Chunk.tsv, tsquery)
    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.page_start,
            Chunk.page_end,
            Chunk.section_path,
            Document.id.label("document_id"),
            Document.filename,
            score.label("score"),
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.collection_id == collection_id,
            Document.status == DocumentStatus.READY,
            Chunk.tsv.op("@@")(tsquery),
        )
        .order_by(score.desc())
        .limit(top_k)
    )
    rows = (await db.execute(stmt)).all()
    return [_to_chunk(row) for row in rows]
