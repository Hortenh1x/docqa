"""Embedding provider protocol.

Every external provider has a stub sibling — tests and the offline demo run without a
single API key. Providers must return vectors of exactly the configured dimension.
"""

from typing import Protocol


class EmbeddingError(Exception):
    """Provider failure after retries — treated as transient by the ingestion task."""


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def check_dim(vectors: list[list[float]], expected: int) -> list[list[float]]:
    for vector in vectors:
        if len(vector) != expected:
            raise EmbeddingError(
                f"provider returned a {len(vector)}-dim vector, expected {expected}"
            )
    return vectors
