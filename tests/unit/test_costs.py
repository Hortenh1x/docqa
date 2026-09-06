"""Pricing helpers: embedding models are keyed by base name, dims suffix ignored."""

from decimal import Decimal

from app.usage.costs import cost_usd, embedding_cost_usd, embedding_price_per_1m


def test_price_strips_dims_suffix():
    assert embedding_price_per_1m("text-embedding-3-small@1024") == Decimal("0.02")
    assert embedding_price_per_1m("text-embedding-3-small") == Decimal("0.02")


def test_local_models_are_free():
    assert embedding_price_per_1m("bge-m3") == Decimal("0")
    assert embedding_cost_usd("stub@1024", 1_000_000) == Decimal("0")


def test_unknown_model_yields_null_not_failure():
    assert embedding_price_per_1m("some-future-model@1024") is None
    assert embedding_cost_usd("some-future-model@1024", 1000) is None


def test_embedding_cost_math():
    assert embedding_cost_usd("text-embedding-3-small@1024", 1_000_000) == Decimal("0.020000")
    # the whole demo corpus is ~20k tokens — visibly non-zero, honestly tiny
    assert embedding_cost_usd("text-embedding-3-small@1024", 20_000) == Decimal("0.000400")


def test_embedding_cost_none_tokens():
    assert embedding_cost_usd("text-embedding-3-small@1024", None) is None


def test_llm_cost_table_still_intact():
    assert cost_usd("deepseek-v4-flash", 1_000_000, 0) == Decimal("0.140000")
    assert cost_usd("unknown", 10, 10) is None
