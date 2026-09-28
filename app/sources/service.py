"""API-side source operations: create (credential check), list, trigger sync, delete."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.actor import Actor
from app.config import get_settings
from app.core.errors import (
    InvalidSourceCredentialsError,
    NotFoundError,
    SourceLimitExceededError,
    SourcesDisabledError,
    SourceSyncInProgressError,
    SourceUnavailableError,
)
from app.db.models import Collection, Document, Source, SyncStatus
from app.sources.base import SourceAuthError, SourceError, SourceTransientError, get_connector
from app.sources.crypto import encrypt_secret
from app.sources.notion.client import normalize_id
from app.sources.tasks import LEASE_SECONDS, enqueue_sync

log = structlog.get_logger("docqa.sources")


def ensure_enabled() -> None:
    if get_settings().source_credentials_key is None:
        raise SourcesDisabledError(
            "External sources are disabled on this server (SOURCE_CREDENTIALS_KEY is not set)."
        )


def normalize_roots(kind: str, root_ids: list[str]) -> list[str]:
    if kind != "notion":
        return [r.strip() for r in root_ids if r.strip()]
    roots: list[str] = []
    for raw in root_ids:
        normalized = normalize_id(raw)
        if normalized is None:
            raise InvalidSourceCredentialsError(
                f"'{raw[:80]}' is not a Notion page/database id or URL."
            )
        if normalized not in roots:
            roots.append(normalized)
    return roots


def _check_credentials(kind: str, token: str, config: dict[str, Any]) -> None:
    connector = get_connector(kind, token, config)
    try:
        connector.check()
    finally:
        close = getattr(connector, "close", None)
        if callable(close):
            close()


async def create_source(
    db: AsyncSession,
    collection: Collection,
    actor: Actor,
    *,
    kind: str,
    name: str,
    token: str,
    root_ids: list[str],
    auto_sync_interval_s: int | None,
    billing_ip_digest: str | None,
) -> Source:
    ensure_enabled()
    settings = get_settings()
    count = await db.scalar(
        select(func.count()).select_from(Source).where(Source.collection_id == collection.id)
    )
    if (count or 0) >= settings.source_max_per_collection:
        raise SourceLimitExceededError(
            f"A collection can have at most {settings.source_max_per_collection} sources."
        )
    config = {"root_ids": normalize_roots(kind, root_ids)}
    try:
        await anyio.to_thread.run_sync(_check_credentials, kind, token, config)
    except SourceAuthError:
        raise InvalidSourceCredentialsError(
            "The integration token was rejected. Check it and that pages are shared with it."
        ) from None
    except SourceTransientError as exc:
        raise SourceUnavailableError(f"Could not reach the source: {exc}") from None
    except SourceError as exc:
        raise InvalidSourceCredentialsError(str(exc)) from None

    now = datetime.now(UTC)
    source = Source(
        tenant_id=collection.tenant_id,
        collection_id=collection.id,
        kind=kind,
        name=name,
        credentials=encrypt_secret(token),
        config=config,
        auto_sync_interval_s=auto_sync_interval_s,
        sync_status=SyncStatus.QUEUED,
        lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
        billing_user_id=actor.user_id if actor.kind == "account" else None,
        billing_ip_digest=billing_ip_digest,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    enqueue_sync(source.id)  # only after the commit — the worker must see the row
    log.info("source_created", source_id=str(source.id), kind=kind)
    return source


async def fetch_source(db: AsyncSession, tenant_id: uuid.UUID, source_id: uuid.UUID) -> Source:
    # owner-only, tenant scope in the WHERE: a foreign source reads as 404
    source = await db.scalar(
        select(Source).where(Source.id == source_id, Source.tenant_id == tenant_id)
    )
    if source is None:
        raise NotFoundError("Source not found.")
    return source


async def request_sync(db: AsyncSession, source: Source) -> None:
    ensure_enabled()
    await db.refresh(source, with_for_update=True)
    now = datetime.now(UTC)
    if (
        source.sync_status in (SyncStatus.QUEUED, SyncStatus.SYNCING)
        and source.lease_expires_at
        and source.lease_expires_at > now
    ):
        raise SourceSyncInProgressError("This source is already being synchronised.")
    source.sync_status = SyncStatus.QUEUED
    source.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    source.last_sync_error = None
    await db.commit()
    enqueue_sync(source.id)


async def document_counts(db: AsyncSession, source_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not source_ids:
        return {}
    rows = (
        await db.execute(
            select(Document.source_id, func.count())
            .where(Document.source_id.in_(source_ids))
            .group_by(Document.source_id)
        )
    ).all()
    return {source_id: int(n) for source_id, n in rows}


async def delete_source(db: AsyncSession, source: Source) -> None:
    # documents stay (FK SET NULL); a sync in flight bails out when its token vanishes
    await db.delete(source)
    await db.commit()
