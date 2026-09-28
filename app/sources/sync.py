"""One sync of a source: list → delete vanished → render changed → upsert → enqueue ingest.

Runs inside the Celery worker (sync sessions). Each document is its own transaction, so a
soft time limit loses at most the page in flight; the task marks the source ``partial``
and re-enqueues itself, and the next run skips everything whose version is unchanged.

Locking order (shared with the API): tenant row (file mutations) → collection → document.
"""

import hashlib
import re
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, Collection, Document, DocumentStatus, Source, Tenant
from app.db.sync import sync_session
from app.ingestion.mime import EXT_BY_MIME, MARKDOWN_MIME
from app.sources.base import SourceConnector, SourceItem, SourceItemError
from app.storage import get_storage
from app.storage.local import durable_directory
from app.storage.usage import ACCOUNT_STORAGE_LIMIT_BYTES

log = structlog.get_logger("docqa.sources")

_EXT = EXT_BY_MIME[MARKDOWN_MIME]
_FILENAME_MAX = 120


@dataclass
class SyncStats:
    listed: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    duplicates: int = 0
    skipped_too_large: int = 0
    skipped_quota: int = 0
    skipped_errors: int = 0
    truncated: bool = False
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["errors"] = self.errors[:10]  # bounded: the JSONB column is not a log
        return data


@dataclass(frozen=True)
class _Existing:
    document_id: uuid.UUID
    version: str | None
    sha256: str


def safe_filename(title: str) -> str:
    name = re.sub(r"[\x00-\x1f/\\]+", " ", title).strip() or "untitled"
    return name[:_FILENAME_MAX].rstrip() + _EXT


def _lock_tenant(session: Session, tenant_id: uuid.UUID) -> None:
    session.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())


def _used_bytes(session: Session, tenant_id: uuid.UUID) -> int:
    used = session.scalar(
        select(func.coalesce(func.sum(Document.size_bytes), 0))
        .join(Collection, Document.collection_id == Collection.id)
        .where(Collection.tenant_id == tenant_id)
    )
    return int(used or 0)


def _delete_file_if_unreferenced(tenant_id: uuid.UUID, sha256: str, mime_type: str) -> None:
    with sync_session() as session:
        _lock_tenant(session, tenant_id)
        still_referenced = session.execute(
            select(Document.id)
            .join(Collection, Document.collection_id == Collection.id)
            .where(
                Collection.tenant_id == tenant_id,
                Document.sha256 == sha256,
                Document.mime_type == mime_type,
            )
            .limit(1)
        ).first()
        if still_referenced is None:
            get_storage().delete(str(tenant_id), sha256, EXT_BY_MIME.get(mime_type, ""))


class SourceSync:
    def __init__(self, source_id: uuid.UUID, connector: SourceConnector) -> None:
        self.source_id = source_id
        self.connector = connector
        self.stats = SyncStats()
        with sync_session() as session:
            source = session.get(Source, source_id)
            if source is None:
                raise LookupError("source vanished")
            self.collection_id = source.collection_id
            self.tenant_id = source.tenant_id
            self.billing_user_id = source.billing_user_id
            self.billing_ip_digest = source.billing_ip_digest
            self.personal = (
                session.scalar(select(Tenant.kind).where(Tenant.id == source.tenant_id))
                == "personal"
            )

    # -- phases ----------------------------------------------------------------------

    def run(self) -> Iterator[uuid.UUID]:
        """Yields the id of every document whose ingestion must be enqueued."""
        settings = get_settings()
        items: list[SourceItem] = []
        for item in self.connector.list_items():
            if len(items) >= settings.source_max_documents:
                self.stats.truncated = True
                break
            items.append(item)
        self.stats.listed = len(items)
        listed_ids = {item.external_id for item in items}

        existing = self._existing()
        if not self.stats.truncated:
            # a capped listing says nothing about what lies beyond the cap
            self._remove_vanished(existing, listed_ids)

        for item in items:
            current = existing.get(item.external_id)
            if current is not None and current.version == item.version:
                self.stats.unchanged += 1
                continue
            document_id = self._upsert(item, current)
            if document_id is not None:
                yield document_id

    def _existing(self) -> dict[str, _Existing]:
        with sync_session() as session:
            rows = session.execute(
                select(
                    Document.external_id, Document.id, Document.external_version, Document.sha256
                ).where(Document.source_id == self.source_id, Document.external_id.isnot(None))
            ).all()
        return {
            str(external_id): _Existing(document_id, version, sha256)
            for external_id, document_id, version, sha256 in rows
        }

    def _remove_vanished(self, existing: dict[str, _Existing], listed_ids: set[str]) -> None:
        vanished = [ext for ext in existing if ext not in listed_ids]
        if not vanished:
            return
        removed_files: list[tuple[str, str]] = []
        with sync_session() as session:
            collection = session.get(Collection, self.collection_id, with_for_update=True)
            if collection is None:
                return
            for external_id in vanished:
                document = session.get(
                    Document, existing[external_id].document_id, with_for_update=True
                )
                if document is None or document.source_id != self.source_id:
                    continue
                had_chunks = bool(
                    session.scalar(
                        select(func.count())
                        .select_from(Chunk)
                        .where(Chunk.document_id == document.id)
                    )
                )
                removed_files.append((document.sha256, document.mime_type))
                session.delete(document)  # chunks cascade
                collection.data_version += 1
                if had_chunks:
                    collection.source_generation += 1
                collection.suggested_questions = None
                self.stats.removed += 1
        for sha256, mime_type in removed_files:
            _delete_file_if_unreferenced(self.tenant_id, sha256, mime_type)

    def _upsert(self, item: SourceItem, current: _Existing | None) -> uuid.UUID | None:
        settings = get_settings()
        try:
            rendered = self.connector.render(item)
        except SourceItemError as exc:
            self.stats.skipped_errors += 1
            self.stats.errors.append(f"{item.title[:60]}: {exc}")
            return None
        payload = rendered.markdown.encode("utf-8")
        if len(payload) > settings.max_upload_bytes:
            self.stats.skipped_too_large += 1
            return None
        sha256 = hashlib.sha256(payload).hexdigest()
        filename = safe_filename(rendered.title or item.title)

        if current is not None and current.sha256 == sha256:
            # edited without visible change (e.g. a property the renderer drops)
            with sync_session() as session:
                document = session.get(Document, current.document_id, with_for_update=True)
                if document is not None and document.source_id == self.source_id:
                    document.external_version = item.version
                    document.external_url = item.url
                    document.filename = filename
            self.stats.unchanged += 1
            return None

        tmp_dir = settings.storage_dir / "tmp"
        durable_directory(tmp_dir)
        tmp_path = tmp_dir / uuid.uuid4().hex
        old_file: tuple[str, str] | None = None
        try:
            tmp_path.write_bytes(payload)
            with sync_session() as session:
                _lock_tenant(session, self.tenant_id)
                if self.personal:
                    used = _used_bytes(session, self.tenant_id)
                    previous = 0
                    if current is not None:
                        previous = int(
                            session.scalar(
                                select(Document.size_bytes).where(
                                    Document.id == current.document_id
                                )
                            )
                            or 0
                        )
                    if used - previous + len(payload) > ACCOUNT_STORAGE_LIMIT_BYTES:
                        self.stats.skipped_quota += 1
                        return None
                get_storage().store(str(self.tenant_id), sha256, _EXT, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        try:
            with sync_session() as session:
                collection = session.get(Collection, self.collection_id, with_for_update=True)
                if collection is None:
                    return None
                if current is None:
                    document = Document(
                        collection_id=self.collection_id,
                        filename=filename,
                        mime_type=MARKDOWN_MIME,
                        size_bytes=len(payload),
                        sha256=sha256,
                        status=DocumentStatus.PENDING,
                        source_id=self.source_id,
                        external_id=item.external_id,
                        external_url=item.url,
                        external_version=item.version,
                        billing_user_id=self.billing_user_id,
                        billing_ip_digest=self.billing_ip_digest,
                    )
                    session.add(document)
                    session.flush()
                    self.stats.added += 1
                else:
                    document = session.get(Document, current.document_id, with_for_update=True)
                    if document is None or document.source_id != self.source_id:
                        return None
                    old_file = (document.sha256, document.mime_type)
                    document.filename = filename
                    document.size_bytes = len(payload)
                    document.sha256 = sha256
                    document.external_url = item.url
                    document.external_version = item.version
                    document.status = DocumentStatus.PENDING
                    document.error = None
                    document.ingestion_attempts = 0
                    document.processing_token = None
                    document.lease_expires_at = None
                    document.next_attempt_at = None
                    document.last_enqueued_at = None
                    document.processed_at = None
                    document.billing_user_id = self.billing_user_id
                    document.billing_ip_digest = self.billing_ip_digest
                    collection.data_version += 1
                    collection.suggested_questions = None
                    self.stats.updated += 1
                document_id = document.id
        except IntegrityError:
            # (collection_id, sha256): another document already carries this exact text
            self.stats.duplicates += 1
            _delete_file_if_unreferenced(self.tenant_id, sha256, MARKDOWN_MIME)
            return None
        if old_file is not None:
            _delete_file_if_unreferenced(self.tenant_id, *old_file)
        return document_id
