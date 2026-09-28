"""Celery tasks: ``sources.sync`` (one source) and ``sources.schedule`` (beat, auto-sync).

Leases mirror ingestion: a live ``lease_expires_at`` means a worker owns the source; an
expired one is reclaimable, so a crashed worker never wedges a source.
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import or_, select

from app.core.errors import SourcesDisabledError
from app.db.models import Source, SyncStatus
from app.db.sync import sync_session
from app.ingestion.tasks import ingest_document
from app.sources.base import SourceAuthError, SourceError, SourceTransientError, get_connector
from app.sources.crypto import decrypt_secret
from app.sources.sync import SourceSync
from app.workers.celery_app import celery_app

log = structlog.get_logger("docqa.sources")

LEASE_SECONDS = 660  # > task_time_limit (600) so a killed worker's lease expires after it
PARTIAL_RETRY_SECONDS = 5
PARTIAL_LEASE_SECONDS = 120


def enqueue_sync(source_id: uuid.UUID) -> None:
    try:
        sync_source.delay(str(source_id))
    except Exception:
        # the QUEUED row is durable; the beat schedule re-publishes it once its lease expires
        log.warning("source_sync_publish_deferred", source_id=str(source_id))


def _finish(
    source_id: uuid.UUID,
    token: uuid.UUID,
    status: SyncStatus,
    error: str | None,
    stats: dict[str, object] | None,
) -> None:
    with sync_session() as session:
        source = session.get(Source, source_id, with_for_update=True)
        if source is None or source.sync_token != token:
            return
        source.sync_status = status
        source.sync_token = None
        # a partial run re-enqueues itself; the short lease keeps the beat from doubling it
        source.lease_expires_at = (
            datetime.now(UTC) + timedelta(seconds=PARTIAL_LEASE_SECONDS)
            if status == SyncStatus.PARTIAL
            else None
        )
        source.last_sync_error = error
        if stats is not None:
            source.last_sync_stats = stats
        if status in (SyncStatus.IDLE, SyncStatus.PARTIAL):
            source.last_sync_at = datetime.now(UTC)


@celery_app.task(name="sources.sync", bind=True, max_retries=0)  # type: ignore[untyped-decorator]
def sync_source(self: Task, source_id: str) -> None:
    src_id = uuid.UUID(source_id)
    token = uuid.uuid4()
    log_ctx = log.bind(source_id=source_id)

    with sync_session() as session:
        source = session.get(Source, src_id, with_for_update=True)
        if source is None:
            return
        now = datetime.now(UTC)
        if (
            source.sync_status == SyncStatus.SYNCING
            and source.lease_expires_at
            and source.lease_expires_at > now
        ):
            return  # another worker owns it
        source.sync_status = SyncStatus.SYNCING
        source.sync_token = token
        source.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        source.last_sync_started_at = now
        kind, config, encrypted = source.kind, dict(source.config or {}), source.credentials

    try:
        credential = decrypt_secret(encrypted)
    except SourcesDisabledError as exc:
        _finish(src_id, token, SyncStatus.FAILED, exc.detail, None)
        return

    connector = get_connector(kind, credential, config)
    to_ingest: list[uuid.UUID] = []
    sync: SourceSync | None = None
    try:
        sync = SourceSync(src_id, connector)
        for document_id in sync.run():
            to_ingest.append(document_id)
            _enqueue_ingest(document_id)
    except SoftTimeLimitExceeded:
        log_ctx.warning("source_sync_partial", ingested=len(to_ingest))
        _finish(src_id, token, SyncStatus.PARTIAL, None, sync.stats.as_dict() if sync else None)
        try:
            sync_source.apply_async(args=[source_id], countdown=PARTIAL_RETRY_SECONDS)
        except Exception:
            log_ctx.warning("source_sync_publish_deferred")
        return
    except SourceAuthError as exc:
        log_ctx.warning("source_sync_auth_failed")
        _finish(src_id, token, SyncStatus.FAILED, f"credentials rejected: {exc}", None)
        return
    except SourceTransientError as exc:
        log_ctx.warning("source_sync_unavailable", error=str(exc))
        _finish(src_id, token, SyncStatus.FAILED, f"source unavailable: {exc}", None)
        return
    except (SourceError, LookupError) as exc:
        log_ctx.warning("source_sync_failed", error_type=type(exc).__name__)
        _finish(src_id, token, SyncStatus.FAILED, str(exc), None)
        return
    except Exception:
        log_ctx.exception("source_sync_unexpected_error")
        _finish(src_id, token, SyncStatus.FAILED, "Sync failed. See worker logs.", None)
        return
    finally:
        close = getattr(connector, "close", None)
        if callable(close):
            close()

    stats = sync.stats.as_dict()
    log_ctx.info("source_sync_done", **{k: v for k, v in stats.items() if k != "errors"})
    _finish(src_id, token, SyncStatus.IDLE, None, stats)


def _enqueue_ingest(document_id: uuid.UUID) -> None:
    try:
        ingest_document.delay(str(document_id))
    except Exception:
        # the PENDING row is picked up by ingestion.recover
        log.warning("ingestion_publish_deferred", document_id=str(document_id))


@celery_app.task(name="sources.schedule")  # type: ignore[untyped-decorator]
def schedule_syncs() -> int:
    """Enqueue auto-sync sources whose interval elapsed, and re-publish lost QUEUED rows."""
    now = datetime.now(UTC)
    due: list[uuid.UUID] = []
    with sync_session() as session:
        rows = session.scalars(
            select(Source)
            .where(
                or_(
                    Source.auto_sync_interval_s.isnot(None),
                    Source.sync_status == SyncStatus.QUEUED,
                    Source.sync_status == SyncStatus.PARTIAL,
                ),
                or_(Source.lease_expires_at.is_(None), Source.lease_expires_at <= now),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for source in rows:
            interval = source.auto_sync_interval_s
            elapsed = (
                source.last_sync_at is None
                or interval is None
                or source.last_sync_at + timedelta(seconds=interval) <= now
            )
            lost = source.sync_status in (SyncStatus.QUEUED, SyncStatus.PARTIAL)
            if not (lost or (interval is not None and elapsed)):
                continue
            source.sync_status = SyncStatus.QUEUED
            source.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            due.append(source.id)
    for source_id in due:
        enqueue_sync(source_id)
    if due:
        log.info("source_syncs_scheduled", count=len(due))
    return len(due)
