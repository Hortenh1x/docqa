"""Shared FastAPI dependencies: DB session, current tenant, tenant-scoped resources."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.roles import Principal, all_labels, resolve_principal
from app.accounts.actor import Actor, collection_scope
from app.accounts.errors import AuthenticationError, EmailVerificationRequiredError
from app.accounts.sessions import check_csrf, load_session
from app.config import get_settings
from app.core.errors import (
    DemoReadOnlyError,
    InvalidApiKeyError,
    NotFoundError,
    TenantInactiveError,
)
from app.core.redis import get_redis
from app.core.security import split_api_key, verify_api_key
from app.db.base import get_db
from app.db.models import ApiKey, Chunk, Collection, Document, Tenant

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
    settings = get_settings()
    loaded = await load_session(request, db)
    if loaded is not None:
        browser_session, user = loaded
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            check_csrf(request, browser_session)
        if user is not None:
            tenant = await db.scalar(
                select(Tenant).where(
                    Tenant.id == user.tenant_id,
                    Tenant.kind == "personal",
                    Tenant.is_active.is_(True),
                )
            )
            if tenant is None:
                raise AuthenticationError()
            request.state.actor = Actor("account", user.id, tenant.id)
            structlog.contextvars.bind_contextvars(tenant_id=str(tenant.id))
            return tenant
        # An explicitly supplied anonymous session is a guest, never a bearer-key login.
        return await _guest_tenant(request, db)
    plaintext = _extract_key(request)
    if not plaintext:
        if settings.accounts_enabled:
            return await _guest_tenant(request, db)
        raise InvalidApiKeyError(
            "Missing API key. Pass 'Authorization: Bearer <key>' or 'X-API-Key: <key>'."
        )
    prefix = split_api_key(plaintext)
    if prefix is None:
        raise InvalidApiKeyError()

    result = await db.execute(
        select(ApiKey, Tenant)
        .join(Tenant, ApiKey.tenant_id == Tenant.id)
        .where(ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None), Tenant.kind == "service")
    )
    for api_key, tenant in result.tuples().all():
        if verify_api_key(plaintext, api_key.key_hash):
            if not tenant.is_active:
                raise TenantInactiveError()
            await _touch_last_used(api_key)
            structlog.contextvars.bind_contextvars(tenant_id=str(tenant.id))
            # rate limiting buckets are per key — expose the prefix to later dependencies
            request.state.api_key_prefix = api_key.prefix
            request.state.actor = Actor(
                "guest"
                if (settings.accounts_enabled or settings.budget_enabled)
                and tenant.id == settings.public_tenant_id
                else "api_key",
                None,
                tenant.id,
            )
            return tenant
    raise InvalidApiKeyError()


async def _guest_tenant(request: Request, db: AsyncSession) -> Tenant:
    tenant = await db.scalar(
        select(Tenant).where(
            Tenant.id == get_settings().public_tenant_id,
            Tenant.kind == "service",
            Tenant.is_active.is_(True),
        )
    )
    if tenant is None:
        raise AuthenticationError("Sign in to access your documents.")
    request.state.actor = Actor("guest", None, tenant.id)
    structlog.contextvars.bind_contextvars(tenant_id=str(tenant.id))
    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]


async def fetch_collection(
    db: AsyncSession, tenant_id: uuid.UUID, collection_id: uuid.UUID, actor: Actor | None = None
) -> Collection:
    # tenant scope lives in the WHERE clause: a foreign collection is indistinguishable
    # from a missing one (404), and no unscoped row ever leaves the database
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id,
            collection_scope(actor) if actor else Collection.tenant_id == tenant_id,
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise NotFoundError("Collection not found.")
    return collection


async def get_collection_or_404(
    collection_id: uuid.UUID, tenant: CurrentTenant, db: DbSession, request: Request
) -> Collection:
    return await fetch_collection(db, tenant.id, collection_id, request.state.actor)


CurrentCollection = Annotated[Collection, Depends(get_collection_or_404)]


def require_write_access(request: Request, collection: Collection | None = None) -> None:
    actor: Actor = request.state.actor
    if actor.kind == "guest" or (
        get_settings().accounts_enabled
        and actor.kind == "api_key"
        and request.headers.get("origin")
    ):
        raise AuthenticationError("Sign in and verify your email to upload documents.")
    if collection is not None:
        if collection.tenant_id != actor.tenant_id:
            if collection.is_public:
                raise DemoReadOnlyError("Public collections are read-only.")
            raise NotFoundError("Collection not found.")
        if collection.read_only or collection.is_public:
            raise DemoReadOnlyError("This collection is read-only.")
    if actor.kind == "account" and not request.state.user.email_verified:
        raise EmailVerificationRequiredError()


async def collection_principal(
    db: AsyncSession, collection: Collection, actor: Actor, role: str | None
) -> Principal:
    if (
        actor.kind == "account"
        and actor.tenant_id == collection.tenant_id
        and not collection.is_public
    ):
        # Includes historical labels that may no longer appear in the demo role map.
        labels = await db.scalars(
            select(Chunk.access_label)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.collection_id == collection.id)
            .distinct()
        )
        return Principal("owner", tuple(sorted(set(labels) | set(all_labels(get_settings())))))
    return resolve_principal(get_settings(), role)
