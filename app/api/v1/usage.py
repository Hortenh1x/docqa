"""GET /v1/usage — tenant usage aggregates (refusals are a statistic, not noise)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentTenant, DbSession
from app.core.rate_limit import rate_limit
from app.usage.service import usage_summary

router = APIRouter(prefix="/v1", tags=["usage"], dependencies=[Depends(rate_limit("default"))])


@router.get("/usage")
async def get_usage(
    tenant: CurrentTenant,
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    return await usage_summary(db, tenant.id, days)
