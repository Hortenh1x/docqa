"""Per-model pricing and query cost calculation.

An unknown model yields a NULL cost, never a failure — pricing tables age faster than
code. Prices are USD per 1M tokens (input, output).
"""

from decimal import Decimal

PRICES_PER_1M: dict[str, tuple[Decimal, Decimal]] = {
    "stub": (Decimal("0"), Decimal("0")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
    "deepseek-chat": (Decimal("0.27"), Decimal("1.10")),
    "deepseek-reasoner": (Decimal("0.55"), Decimal("2.19")),
}

_PER = Decimal("1000000")
_CENT_MICRO = Decimal("0.000001")


def cost_usd(
    model: str | None, prompt_tokens: int | None, completion_tokens: int | None
) -> Decimal | None:
    if not model or prompt_tokens is None or completion_tokens is None:
        return None
    prices = PRICES_PER_1M.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    total = (prompt_tokens * input_price + completion_tokens * output_price) / _PER
    return total.quantize(_CENT_MICRO)
