"""Upload intake: streaming hash + size check, magic-byte type detection, dedup, enqueue."""

import hashlib
import uuid
from pathlib import Path

import aiofiles
import anyio
import filetype
import fitz
import structlog
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import (
    DemoQuotaExceededError,
    DemoReadOnlyError,
    DuplicateDocumentError,
    NotFoundError,
    PayloadTooLargeError,
    StorageQuotaExceededError,
    TooManyPagesError,
    UnsupportedFileTypeError,
)
from app.db.models import Collection, Document, DocumentStatus, Tenant
from app.ingestion.mime import EXT_BY_MIME, TEXT_EXT_MIME
from app.ingestion.tasks import ingest_document
from app.storage import get_storage
from app.storage.errors import StorageUnavailableError
from app.storage.lifecycle import lock_tenant_files
from app.storage.local import durable_directory
from app.storage.usage import storage_usage

log = structlog.get_logger("docqa.ingestion")

READ_CHUNK_BYTES = 1024 * 1024


def _detect_mime(head: bytes, filename: str | None) -> str | None:
    """Magic bytes for binary formats; extension + UTF-8 validity for text formats."""
    kind = filetype.guess(head)
    if kind is not None:
        return kind.mime if kind.mime in EXT_BY_MIME else None
    # no magic bytes — accept md/txt only when the extension says so and the bytes decode
    ext = Path(filename or "").suffix.lower()
    mime = TEXT_EXT_MIME.get(ext)
    if mime is None:
        return None
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return mime


def _pdf_page_count(path: Path) -> int | None:
    """Page count for early rejection; unreadable PDFs are left to the worker to fail properly."""
    try:
        with fitz.open(path) as pdf:
            return int(pdf.page_count)
    except Exception:
        return None


async def save_upload(db: AsyncSession, collection: Collection, upload: UploadFile) -> Document:
    settings = get_settings()
    # captured before the INSERT attempt: a rollback expires ORM instances, and touching
    # their attributes afterwards would trigger a sync lazy-load inside the event loop
    collection_id = collection.id
    tenant_id = collection.tenant_id

    if collection.read_only:
        raise DemoReadOnlyError("This demo collection is read-only. Use the sandbox collection.")
    tmp_dir = settings.storage_dir / "tmp"
    try:
        await anyio.to_thread.run_sync(durable_directory, tmp_dir)
    except OSError:
        raise StorageUnavailableError("Could not prepare document storage.") from None
    tmp_path = tmp_dir / uuid.uuid4().hex

    hasher = hashlib.sha256()
    size = 0
    head = b""
    try:
        async with aiofiles.open(tmp_path, "wb") as out:
            while chunk := await upload.read(READ_CHUNK_BYTES):
                if not head:
                    head = chunk[:8192]
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise PayloadTooLargeError(
                        f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} "
                        "MB upload limit."
                    )
                hasher.update(chunk)
                await out.write(chunk)

        if size == 0:
            raise UnsupportedFileTypeError("Empty file.")

        mime = _detect_mime(head, upload.filename)
        if mime is None:
            raise UnsupportedFileTypeError(
                "Unsupported file type. Allowed: PDF, DOCX, Markdown, plain text."
            )

        if mime == "application/pdf":
            pages = await anyio.to_thread.run_sync(_pdf_page_count, tmp_path)
            if pages is not None and pages > settings.max_pages:
                raise TooManyPagesError(
                    f"PDF has {pages} pages; the limit is {settings.max_pages}."
                )
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    sha256 = hasher.hexdigest()
    try:
        await lock_tenant_files(db, tenant_id)
        # Re-read policy after waiting for a concurrent mutation; the dependency's
        # ORM object can be stale by the time the upload body has been validated.
        read_only = await db.scalar(
            select(Collection.read_only).where(
                Collection.id == collection_id, Collection.tenant_id == tenant_id
            )
        )
        if read_only is None:
            raise NotFoundError("Collection not found.")
        if read_only:
            raise DemoReadOnlyError("This collection is read-only.")
        tenant_kind = await db.scalar(select(Tenant.kind).where(Tenant.id == tenant_id))
        if tenant_kind == "personal":
            # Under the tenant lock, preserve duplicate semantics even when full.
            # The database unique constraint remains the final dedup safety net.
            existing_id = await db.scalar(
                select(Document.id).where(
                    Document.collection_id == collection_id, Document.sha256 == sha256
                )
            )
            if existing_id is not None:
                raise DuplicateDocumentError(
                    "Identical file already exists in this collection.",
                    existing_document_id=str(existing_id),
                )
            usage = await storage_usage(db, tenant_id)
            if usage.used_bytes + size > usage.limit_bytes:
                raise StorageQuotaExceededError(
                    "Your account has a 50 MB document storage limit. "
                    "Delete files from your collections to make room before uploading."
                )
        elif settings.demo_mode:
            existing = (
                await db.execute(
                    select(func.count(Document.id)).where(Document.collection_id == collection_id)
                )
            ).scalar_one()
            if existing >= settings.demo_max_files_per_collection:
                raise DemoQuotaExceededError(
                    f"Demo sandbox allows at most {settings.demo_max_files_per_collection} files "
                    "per collection. Data is wiped nightly."
                )
        await anyio.to_thread.run_sync(
            get_storage().store, str(tenant_id), sha256, EXT_BY_MIME[mime], tmp_path
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    from app.billing.context import current_billing_actor

    payer = current_billing_actor.get()
    document = Document(
        collection_id=collection_id,
        filename=upload.filename or "unnamed",
        mime_type=mime,
        size_bytes=size,
        sha256=sha256,
        status=DocumentStatus.PENDING,
        billing_user_id=payer.user_id if payer else None,
        billing_ip_digest=payer.ip_digest if payer else None,
    )
    db.add(document)
    try:
        await db.commit()
    except IntegrityError:
        # the unique constraint (collection_id, sha256) wins any race —
        # a SELECT-before-INSERT check would not
        await db.rollback()
        existing_id = (
            await db.execute(
                select(Document.id).where(
                    Document.collection_id == collection_id, Document.sha256 == sha256
                )
            )
        ).scalar_one()
        raise DuplicateDocumentError(
            "Identical file already exists in this collection.",
            existing_document_id=str(existing_id),
        ) from None
    await db.refresh(document)

    # enqueue only after the commit — otherwise the worker can wake up before the row is visible
    try:
        ingest_document.delay(str(document.id))
    except Exception:
        # The committed PENDING row is the durable queue entry; the recovery task
        # republishes it when Redis is back. Do not misreport the accepted upload.
        log.warning("ingestion_publish_deferred", document_id=str(document.id))
    log.info("document_enqueued", document_id=str(document.id), mime=mime, size_bytes=size)
    return document


async def delete_document_file_if_unreferenced(
    db: AsyncSession, tenant_id: uuid.UUID, sha256: str, mime_type: str
) -> None:
    """Remove the stored file unless another document of this tenant still points at it."""
    await lock_tenant_files(db, tenant_id)
    still_referenced = (
        await db.execute(
            select(Document.id)
            .join(Collection, Document.collection_id == Collection.id)
            .where(
                Collection.tenant_id == tenant_id,
                Document.sha256 == sha256,
                Document.mime_type == mime_type,
            )
            .limit(1)
        )
    ).first()
    if still_referenced is None:
        await anyio.to_thread.run_sync(
            get_storage().delete, str(tenant_id), sha256, EXT_BY_MIME.get(mime_type, "")
        )


async def retry_failed_document(
    db: AsyncSession, collection: Collection, document: Document
) -> None:
    """Keep the original; explicitly queue another metered attempt for its owner."""
    from app.billing.context import current_billing_actor

    payer = current_billing_actor.get()
    document.billing_user_id = payer.user_id if payer else None
    document.billing_ip_digest = payer.ip_digest if payer else None
    document.status = DocumentStatus.PENDING
    document.error = None
    document.ingestion_attempts = 0
    document.processing_token = None
    document.lease_expires_at = None
    document.next_attempt_at = None
    document.last_enqueued_at = None
    document.processed_at = None
    collection.data_version += 1
    collection.suggested_questions = None
    await db.commit()
    try:
        ingest_document.delay(str(document.id))
    except Exception:
        log.warning("ingestion_publish_deferred", document_id=str(document.id))
