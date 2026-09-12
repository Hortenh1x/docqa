"""Conservative reservation bounds and exact decimal usage valuation."""

from decimal import ROUND_CEILING, Decimal

from app.billing.errors import BudgetUnavailableError
from app.usage.costs import PRICES_PER_1M, embedding_price_per_1m

PRECISION = Decimal("0.00000001")


def _prices(model: str, embedding: bool) -> tuple[Decimal, Decimal]:
    if embedding:
        price = embedding_price_per_1m(model)
        if price is not None:
            return price, Decimal(0)
    elif model in PRICES_PER_1M:
        return PRICES_PER_1M[model]
    raise BudgetUnavailableError("This model has no configured spending tariff.")


def actual_price(
    model: str, prompt: int | None, completion: int | None, *, embedding: bool = False
) -> Decimal | None:
    if prompt is None or completion is None or prompt < 0 or completion < 0:
        return None
    p_in, p_out = _prices(model, embedding)
    return ((prompt * p_in + completion * p_out) / 1_000_000).quantize(
        PRECISION, rounding=ROUND_CEILING
    )


def reserve_price(
    model: str, texts: list[str], max_output: int, *, embedding: bool = False
) -> Decimal:
    # UTF-8 bytes bound text tokens conservatively; extra space covers message framing.
    # Providers' max_output includes reasoning tokens. No tools/media are sent here.
    if max_output < 0:
        raise BudgetUnavailableError("Invalid provider output bound.")
    tokens = sum(len(t.encode("utf-8")) for t in texts) + 1024
    amount = actual_price(model, tokens, max_output, embedding=embedding)
    assert amount is not None
    return amount
