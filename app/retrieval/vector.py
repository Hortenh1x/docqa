"""Vector search over pgvector's HNSW index (cosine).

Access control happens here, in the WHERE clause: a chunk whose label the caller's role
cannot see never leaves the database. ``hnsw.iterative_scan`` (pgvector ≥ 0.8) keeps the
index scanning when the label filter discards most candidates, so a role that sees a
small fraction of the corpus still gets ``top_k`` results.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Row, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentStatus
from app.retrieval.base import HiddenStats, RetrievedChunk


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
        access_label=row.access_label,
    )


async def _prepare_hnsw(db: AsyncSession, ef_search: int) -> None:
    # SET LOCAL lives and dies with the current transaction — it must precede the
    # search in the same one. int() guards the literal (SET does not take bind params).
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))
    # One HNSW index spans every collection and every access label. Without iterative
    # scanning the index yields ef_search neighbours from the WHOLE table and our WHERE
    # filters run afterwards, so a small collection next to large ones can come back
    # empty (observed on prod: 509 contracts beside 250k chunks of reports). Iterative
    # scan (pgvector >= 0.8) keeps walking the graph until the LIMIT is satisfied.
    await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))


async def vector_search(
    db: AsyncSession,
    collection_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
    ef_search: int,
    allowed_labels: Sequence[str],
) -> list[RetrievedChunk]:
    await _prepare_hnsw(db, ef_search)

    distance = Chunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.page_start,
            Chunk.page_end,
            Chunk.section_path,
            Chunk.access_label,
            Document.id.label("document_id"),
            Document.filename,
            (1 - distance).label("score"),  # cosine similarity
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(
            # tenant scope is enforced upstream (the collection is fetched tenant-scoped)
            Document.collection_id == collection_id,
            Document.status == DocumentStatus.READY,
            # access scope: filter, never post-check
            Chunk.access_label.in_(list(allowed_labels)),
        )
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await db.execute(stmt)).all()
    return [_to_chunk(row) for row in rows]


async def hidden_probe(
    db: AsyncSession,
    collection_id: uuid.UUID,
    query_embedding: list[float],
    allowed_labels: Sequence[str],
    top_k: int,
    threshold: float,
) -> HiddenStats:
    """The complement of ``vector_search``: the best chunks the role can NOT see.

    Only their count above the refusal threshold and their labels are returned — never
    the content. Runs in the same transaction as the search (SET LOCAL already applied).
    """
    distance = Chunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(Chunk.access_label, (1 - distance).label("score"))
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.collection_id == collection_id,
            Document.status == DocumentStatus.READY,
            Chunk.access_label.not_in(list(allowed_labels)),
        )
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await db.execute(stmt)).all()
    relevant = [row for row in rows if float(row.score) >= threshold]
    labels: dict[str, None] = {}
    for row in relevant:
        labels.setdefault(row.access_label, None)
    return HiddenStats(passages=len(relevant), labels=tuple(labels))
