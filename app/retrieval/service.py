"""Retrieval orchestration: embed the question → vector + FTS → RRF → rerank.

Opens its own short-lived session so no connection is held while the LLM streams later.
Every search carries the caller's principal: chunks outside its labels are filtered in
SQL. In reveal mode (demo) an extra probe reports what the role could not see.
"""

import uuid
from dataclasses import dataclass

from app.access import Principal, resolve_principal
from app.access.roles import sees_everything
from app.config import Settings
from app.db.base import get_sessionmaker
from app.embeddings import get_embedding_provider
from app.retrieval.base import HiddenStats, RetrievedChunk
from app.retrieval.fulltext import fulltext_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.rerank import get_rerank_provider
from app.retrieval.vector import hidden_probe, vector_search


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    top_score: float | None
    # None unless reveal mode is on and the role has something to miss
    hidden: HiddenStats | None = None


async def retrieve(
    collection_id: uuid.UUID,
    question: str,
    settings: Settings,
    principal: Principal | None = None,
) -> RetrievalResult:
    # no principal → the default (least-privilege) role; never "see everything"
    principal = principal or resolve_principal(settings, None)
    provider = get_embedding_provider(settings)
    [query_embedding] = await provider.embed([question])

    hidden: HiddenStats | None = None
    async with get_sessionmaker()() as db:
        vector_hits = await vector_search(
            db,
            collection_id,
            query_embedding,
            settings.top_k_vector,
            settings.hnsw_ef_search,
            principal.labels,
        )
        fulltext_hits = await fulltext_search(
            db, collection_id, question, settings.top_k_fts, principal.labels
        )
        if settings.access_reveal_hidden:
            # reveal mode: null means "not revealed"; a full-access role reports zero
            # without a probe
            if sees_everything(settings, principal):
                hidden = HiddenStats(passages=0, labels=())
            else:
                hidden = await hidden_probe(
                    db,
                    collection_id,
                    query_embedding,
                    principal.labels,
                    settings.rerank_top_n,
                    settings.refusal_threshold,
                )

    fused = reciprocal_rank_fusion(
        [vector_hits, fulltext_hits], k=settings.rrf_k, top_n=settings.rrf_top_n
    )
    reranked = await get_rerank_provider(settings).rerank(question, fused, settings.rerank_top_n)

    if settings.rerank_provider == "none":
        # NoRerank normalizes fused ranks (the top hit is always 1.0) — useless against a
        # refusal threshold. The honest confidence signal in that mode is the best vector
        # cosine similarity: "is anything in the corpus semantically close at all".
        gate_score = vector_hits[0].score if vector_hits else None
    else:
        gate_score = reranked[0].score if reranked else None
    return RetrievalResult(chunks=reranked, top_score=gate_score, hidden=hidden)
