"""Reranking behind a Protocol.

A reranker re-scores fused candidates against the question with a cross-encoder.
Its score is also what the refusal gate compares against ``REFUSAL_THRESHOLD``.
Rerankers must never break the search: providers degrade to the fused order on failure.
"""

from typing import Protocol

from app.config import Settings
from app.retrieval.base import RetrievedChunk


class RerankProvider(Protocol):
    async def rerank(
        self, question: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        """Return the top_n chunks re-scored and re-ordered by relevance to the question."""
        ...


def get_rerank_provider(settings: Settings) -> RerankProvider:
    if settings.rerank_provider == "cohere":
        if not settings.cohere_api_key:
            raise RuntimeError("COHERE_API_KEY is required when RERANK_PROVIDER=cohere")
        from app.retrieval.rerank.cohere import CohereRerank

        return CohereRerank(
            api_key=settings.cohere_api_key,
            model=settings.cohere_rerank_model,
            timeout_s=settings.rerank_timeout_s,
        )
    if settings.rerank_provider == "local":
        from app.retrieval.rerank.local import LocalRerank

        return LocalRerank()
    if settings.rerank_provider == "stub":
        from app.retrieval.rerank.stub import StubRerank

        return StubRerank()
    from app.retrieval.rerank.none import NoRerank

    return NoRerank()
