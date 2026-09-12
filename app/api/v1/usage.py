"""GET /v1/usage — tenant usage aggregates (refusals are a statistic, not noise)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentTenant, DbSession
from app.billing.context import current_billing_actor
from app.core.rate_limit import rate_limit
from app.usage.service import usage_summary

router = APIRouter(prefix="/v1", tags=["usage"], dependencies=[Depends(rate_limit("default"))])


@router.get("/usage")
async def get_usage(
    tenant: CurrentTenant,
    db: DbSession,
    request: Request,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    actor = getattr(request.state, "actor", None)
    payer = current_billing_actor.get()
    return await usage_summary(
        db,
        tenant.id,
        days,
        visitor=actor is not None and actor.kind != "api_key",
        user_id=actor.user_id if actor else None,
        ip_digest=payer.ip_digest if payer else None,
    )
