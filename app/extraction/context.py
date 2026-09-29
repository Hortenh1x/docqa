"""Which text the model sees.

Short documents (≤ EXTRACTION_FULL_TEXT_TOKENS) go in whole, chunks in reading order.
Longer ones: every field becomes a query ("label — description — examples"), the
document's own chunks are scored by cosine against those queries in memory (a document has
at most a few hundred chunks — no index needed), and the best chunks are taken until the
context budget is spent. The first chunk is always kept: headers carry the identifiers.
"""

from dataclasses import dataclass

import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Chunk
from app.embeddings import get_embedding_provider
from app.extraction.fields import SchemaDefinition


@dataclass(frozen=True)
class ChunkText:
    chunk_id: int
    chunk_index: int
    content: str
    page_start: int | None
    page_end: int | None
    token_count: int
    access_label: str


def load_chunks(session: Session, document_id: object) -> list[ChunkText]:
    rows = session.execute(
        select(
            Chunk.id,
            Chunk.chunk_index,
            Chunk.content,
            Chunk.page_start,
            Chunk.page_end,
            Chunk.token_count,
            Chunk.access_label,
        )
        .where(
            Chunk.document_id == document_id,
            or_(Chunk.section_path.is_(None), Chunk.section_path != FACTS_SECTION),
        )
        .order_by(Chunk.chunk_index)
    ).all()
    return [ChunkText(*row) for row in rows]


FACTS_SECTION = "Extracted fields"


async def select_chunks(
    chunks: list[ChunkText],
    embeddings: dict[int, list[float]],
    definition: SchemaDefinition,
    settings: Settings,
) -> list[ChunkText]:
    total = sum(c.token_count for c in chunks)
    if total <= settings.extraction_full_text_tokens or not chunks:
        return chunks
    queries = [
        " — ".join(
            part for part in (spec.label, spec.description, "; ".join(spec.examples)) if part
        )
        for spec in definition.fields
    ]
    provider = get_embedding_provider(settings)
    query_vectors = np.asarray(await provider.embed(queries), dtype=np.float32)
    matrix = np.asarray([embeddings.get(c.chunk_id) or [0.0] for c in chunks], dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != query_vectors.shape[1]:
        return chunks[: max(1, len(chunks) // 3)]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    qnorms = np.linalg.norm(query_vectors, axis=1, keepdims=True)
    qnorms[qnorms == 0] = 1.0
    scores = (matrix / norms) @ (query_vectors / qnorms).T  # chunks × fields
    best = scores.max(axis=1)
    order = np.argsort(-best)
    budget = settings.extraction_context_tokens
    chosen = {0}
    spent = chunks[0].token_count
    for index in order:
        i = int(index)
        if i in chosen:
            continue
        if spent + chunks[i].token_count > budget:
            continue
        chosen.add(i)
        spent += chunks[i].token_count
    return [chunks[i] for i in sorted(chosen)]


def render_context(chunks: list[ChunkText]) -> str:
    parts = []
    for chunk in chunks:
        page = f" p.{chunk.page_start}" if chunk.page_start else ""
        parts.append(f"[passage {chunk.chunk_index}{page}]\n{chunk.content}")
    return "\n\n".join(parts)
