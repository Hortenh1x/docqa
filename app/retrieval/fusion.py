"""Reciprocal Rank Fusion.

Why RRF and not a weighted score sum: cosine similarity and ts_rank live on
incomparable scales; RRF works on ranks alone, needs no normalization and no weight
tuning, and a chunk found by both searches naturally rises above single-source hits.

    score(chunk) = Σ over lists 1 / (k + rank_in_list),  k = 60
"""

from collections.abc import Sequence
from dataclasses import replace

from app.retrieval.base import RetrievedChunk


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[RetrievedChunk]],
    k: int = 60,
    top_n: int = 20,
) -> list[RetrievedChunk]:
    fused_scores: dict[int, float] = {}
    by_id: dict[int, RetrievedChunk] = {}

    for results in result_lists:
        for rank, chunk in enumerate(results, start=1):
            fused_scores[chunk.chunk_id] = fused_scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            by_id.setdefault(chunk.chunk_id, chunk)  # dedup across lists

    ordered = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)[:top_n]
    return [replace(by_id[chunk_id], score=score) for chunk_id, score in ordered]
