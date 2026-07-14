"""Retrieval orchestration: embed the question → vector + FTS → RRF → rerank.

Opens its own short-lived session so no connection is held while the LLM streams later.
"""

import uuid
from dataclasses import dataclass

from app.config import Settings
from app.db.base import get_sessionmaker
from app.embeddings import get_embedding_provider
from app.retrieval.base import RetrievedChunk
from app.retrieval.fulltext import fulltext_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.rerank import get_rerank_provider
from app.retrieval.vector import vector_search


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    top_score: float | None


async def retrieve(collection_id: uuid.UUID, question: str, settings: Settings) -> RetrievalResult:
    provider = get_embedding_provider(settings)
    [query_embedding] = await provider.embed([question])

    async with get_sessionmaker()() as db:
        vector_hits = await vector_search(
            db, collection_id, query_embedding, settings.top_k_vector, settings.hnsw_ef_search
        )
        fulltext_hits = await fulltext_search(db, collection_id, question, settings.top_k_fts)

    fused = reciprocal_rank_fusion(
        [vector_hits, fulltext_hits], k=settings.rrf_k, top_n=settings.rrf_top_n
    )
    reranked = await get_rerank_provider(settings).rerank(question, fused, settings.rerank_top_n)
    return RetrievalResult(chunks=reranked, top_score=reranked[0].score if reranked else None)
