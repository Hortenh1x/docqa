"""Passthrough reranker: keeps the RRF order, normalizes scores to [0, 1].

With this provider the refusal gate effectively fires only on empty retrieval
(the top hit always normalizes to 1.0) — fine for a no-dependency default; use a real
reranker for meaningful confidence scores.
"""

from dataclasses import replace

from app.retrieval.base import RetrievedChunk


class NoRerank:
    async def rerank(
        self, question: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        top_score = chunks[0].score or 1.0
        return [replace(c, score=c.score / top_score) for c in chunks[:top_n]]
