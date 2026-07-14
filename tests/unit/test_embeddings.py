import math

import pytest

from app.config import Settings
from app.embeddings import StubEmbeddings, get_embedding_provider
from app.embeddings.base import EmbeddingError, check_dim


async def test_stub_is_deterministic_and_normalized():
    provider = StubEmbeddings(dim=1024)
    first, second = await provider.embed(["hello world", "hello world"])

    assert first == second
    assert len(first) == 1024
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0, rel_tol=1e-9)


async def test_stub_differs_for_different_texts():
    provider = StubEmbeddings(dim=64)
    a, b = await provider.embed(["alpha", "beta"])
    assert a != b


def test_factory_returns_stub_by_default():
    settings = Settings(database_url="postgresql+asyncpg://x/x", redis_url="redis://x")
    provider = get_embedding_provider(settings)
    assert isinstance(provider, StubEmbeddings)
    assert provider.dim == 1024


def test_check_dim_rejects_mismatch():
    with pytest.raises(EmbeddingError):
        check_dim([[0.0] * 512], expected=1024)
