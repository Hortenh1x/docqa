"""Tenant usage aggregates over the queries table."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Query


async def usage_summary(db: AsyncSession, tenant_id: uuid.UUID, days: int) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    row = (
        await db.execute(
            select(
                func.count(Query.id).label("queries"),
                func.coalesce(func.sum(case((Query.refused, 1), else_=0)), 0).label("refused"),
                func.coalesce(func.sum(Query.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(Query.completion_tokens), 0).label("completion_tokens"),
                func.coalesce(func.sum(Query.cost_usd), 0).label("cost_usd"),
                func.avg(Query.latency_ms).label("avg_latency_ms"),
            ).where(Query.tenant_id == tenant_id, Query.created_at >= since)
        )
    ).one()
    return {
        "days": days,
        "queries": row.queries,
        "refused": row.refused,
        "prompt_tokens": int(row.prompt_tokens),
        "completion_tokens": int(row.completion_tokens),
        "cost_usd": float(row.cost_usd),
        "avg_latency_ms": round(row.avg_latency_ms) if row.avg_latency_ms is not None else None,
    }
