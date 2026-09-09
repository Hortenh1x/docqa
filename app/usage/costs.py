"""Per-model pricing and query cost calculation.

An unknown model yields a NULL cost, never a failure — pricing tables age faster than
code. Prices are USD per 1M tokens (input, output).
"""

from decimal import Decimal

# Every entry is the **peak-hour, cache-miss** rate: a deliberate upper bound. DeepSeek
# halves both prices outside 01:00–04:00 and 06:00–10:00 UTC on weekdays, and a cache hit
# costs ~1/30 of a miss — we track neither, so a recorded cost is never an understatement.
# DeepSeek prices per api-docs.deepseek.com/quick_start/pricing, checked 2026-09-09.
PRICES_PER_1M: dict[str, tuple[Decimal, Decimal]] = {
    "stub": (Decimal("0"), Decimal("0")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
    "deepseek-v4-flash": (Decimal("0.44"), Decimal("1.32")),
    "deepseek-v4-flash-vision-exp": (Decimal("0.44"), Decimal("1.32")),
    "deepseek-v4-pro": (Decimal("1.32"), Decimal("3.96")),
    # legacy aliases, deprecated 2026-07-24; they bill as v4-flash until removal
    "deepseek-chat": (Decimal("0.44"), Decimal("1.32")),
    "deepseek-reasoner": (Decimal("0.44"), Decimal("1.32")),
}

# Embedding prices, USD per 1M input tokens. Keyed by the base model name — the id
# pinned on a collection may carry a "@<dims>" suffix (text-embedding-3-small@1024).
EMBEDDING_PRICES_PER_1M: dict[str, Decimal] = {
    "stub": Decimal("0"),
    "bge-m3": Decimal("0"),  # local ollama
    "text-embedding-3-small": Decimal("0.02"),
    "text-embedding-3-large": Decimal("0.13"),
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


def embedding_price_per_1m(model_id: str) -> Decimal | None:
    return EMBEDDING_PRICES_PER_1M.get(model_id.split("@", 1)[0])


def embedding_cost_usd(model_id: str, tokens: int | None) -> Decimal | None:
    price = embedding_price_per_1m(model_id)
    if price is None or tokens is None:
        return None
    return (tokens * price / _PER).quantize(_CENT_MICRO)
