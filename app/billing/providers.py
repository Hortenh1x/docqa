"""Provider adapters call admission once per HTTP attempt, settlement once per usage."""

import uuid

from app.billing.context import current_billing_actor, operator_billing
from app.billing.errors import BudgetUnavailableError
from app.billing.pricing import actual_price, reserve_price
from app.billing.service import reserve, settle
from app.config import get_settings


async def before_call(
    model: str, texts: list[str], max_output: int = 0, *, embedding: bool = False
) -> uuid.UUID | None:
    if not get_settings().budget_enabled or operator_billing.get():
        return None
    actor = current_billing_actor.get()
    if actor is None:
        raise BudgetUnavailableError("Paid operation has no billing identity.")
    amount = reserve_price(model, texts, max_output, embedding=embedding)
    return await reserve(actor, amount, "embedding" if embedding else "generation", model)


async def after_call(
    ticket: uuid.UUID | None,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None = 0,
    *,
    embedding: bool = False,
) -> None:
    if ticket is None:
        return
    await settle(ticket, actual_price(model, prompt_tokens, completion_tokens, embedding=embedding))
