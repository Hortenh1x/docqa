"""Liveness and readiness probes."""

from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.redis import get_redis
from app.db.base import get_engine

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, Any]:
    checks: dict[str, str] = {}

    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    ready = all(state == "ok" for state in checks.values())
    response.status_code = 200 if ready else 503
    return {"status": "ok" if ready else "unavailable", "checks": checks}
