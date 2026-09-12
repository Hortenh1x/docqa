"""Visitor-visible remaining AI budget, with guest spend imported on authenticated reads."""

from typing import Any

from fastapi import APIRouter, Depends

from app.billing.context import current_billing_actor
from app.billing.service import summary
from app.config import get_settings
from app.core.rate_limit import rate_limit

router = APIRouter(prefix="/v1", tags=["usage"], dependencies=[Depends(rate_limit("default"))])


@router.get("/budget")
async def get_budget() -> dict[str, Any]:
    if not get_settings().budget_enabled:
        return {"enabled": False}
    actor = current_billing_actor.get()
    if actor is None:
        return {"enabled": False, "reason": "operator_integration"}
    return {"enabled": True, **await summary(actor)}
