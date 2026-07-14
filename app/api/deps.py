"""Shared FastAPI dependencies: DB session, current tenant, tenant-scoped resources."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidApiKeyError, NotFoundError, TenantInactiveError
from app.core.redis import get_redis
from app.core.security import split_api_key, verify_api_key
from app.db.base import get_db
from app.db.models import ApiKey, Collection, Tenant

log = structlog.get_logger("docqa.auth")

DbSession = Annotated[AsyncSession, Depends(get_db)]

# one UPDATE per key per 5 minutes instead of per request (write amplification)
LAST_USED_THROTTLE_SECONDS = 300


def _extract_key(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # some clients find a plain header simpler than the Authorization scheme
    return request.headers.get("x-api-key")


async def _touch_last_used(api_key: ApiKey) -> None:
    """Best-effort last_used_at update, throttled via Redis. Never blocks authentication."""
    try:
        fresh = await get_redis().set(
            f"api_key_seen:{api_key.id}", "1", nx=True, ex=LAST_USED_THROTTLE_SECONDS
        )
    except Exception:
        log.warning("last_used_throttle_unavailable")
        return
    if fresh:
        # mutation is flushed and committed together with the request's session
        api_key.last_used_at = datetime.now(UTC)


async def get_current_tenant(request: Request, db: DbSession) -> Tenant:
    plaintext = _extract_key(request)
    if not plaintext:
        raise InvalidApiKeyError(
            "Missing API key. Pass 'Authorization: Bearer <key>' or 'X-API-Key: <key>'."
        )
    prefix = split_api_key(plaintext)
    if prefix is None:
        raise InvalidApiKeyError()

    result = await db.execute(
        select(ApiKey, Tenant)
        .join(Tenant, ApiKey.tenant_id == Tenant.id)
        .where(ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None))
    )
    for api_key, tenant in result.tuples().all():
        if verify_api_key(plaintext, api_key.key_hash):
            if not tenant.is_active:
                raise TenantInactiveError()
            await _touch_last_used(api_key)
            structlog.contextvars.bind_contextvars(tenant_id=str(tenant.id))
            # rate limiting buckets are per key — expose the prefix to later dependencies
            request.state.api_key_prefix = api_key.prefix
            return tenant
    raise InvalidApiKeyError()


CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]


async def fetch_collection(
    db: AsyncSession, tenant_id: uuid.UUID, collection_id: uuid.UUID
) -> Collection:
    # tenant scope lives in the WHERE clause: a foreign collection is indistinguishable
    # from a missing one (404), and no unscoped row ever leaves the database
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.tenant_id == tenant_id)
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise NotFoundError("Collection not found.")
    return collection


async def get_collection_or_404(
    collection_id: uuid.UUID, tenant: CurrentTenant, db: DbSession
) -> Collection:
    return await fetch_collection(db, tenant.id, collection_id)


CurrentCollection = Annotated[Collection, Depends(get_collection_or_404)]
