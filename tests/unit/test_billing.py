"""Money precision and stable client scopes; no network calls."""

from decimal import Decimal

import pytest


def test_embedding_bound_covers_multibyte_text_and_protocol_overhead():
    from app.billing.pricing import reserve_price

    result = reserve_price("text-embedding-3-small", ["a", "€🙂"], 0, embedding=True)
    assert result == Decimal("0.00002064")  # (8 UTF-8 bytes + 1024) * $0.02 / 1M


def test_generation_bound_includes_the_entire_max_completion():
    from app.billing.pricing import reserve_price

    assert reserve_price("deepseek-v4-flash", ["hello"], 4096) == Decimal("0.00522390")


def test_missing_price_cannot_turn_a_paid_request_into_free_work():
    from app.billing.errors import BudgetUnavailableError
    from app.billing.pricing import reserve_price

    with pytest.raises(BudgetUnavailableError):
        reserve_price("unknown-hosted-model", ["hello"], 4096)


def test_usage_rounds_up_instead_of_erasing_sub_microdollar_embedding_cost():
    from app.billing.pricing import actual_price

    assert actual_price("text-embedding-3-small", 1, 0, embedding=True) == Decimal("0.00000002")
    assert actual_price("deepseek-flash", 1, 1) == Decimal("0.00000150")


def test_usage_missing_or_invalid_does_not_release_uncertain_reservation():
    from app.billing.pricing import actual_price

    assert actual_price("deepseek-flash", None, 2) is None
    assert actual_price("deepseek-flash", -1, 2) is None


def test_sub_million_token_arithmetic_never_uses_float():
    from app.billing.pricing import actual_price

    costs = [actual_price("text-embedding-3-small", 3, 0, embedding=True) for _ in range(1000)]
    assert sum(costs, Decimal("0")) == Decimal("0.00006000")
