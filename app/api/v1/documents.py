"""Document upload, listing, status, original-file download and deletion."""

import hashlib
import re
import uuid
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import quote

import anyio
from fastapi import APIRouter, Depends, Header, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.access.labels import restricted_labels_by_document
from app.accounts.actor import Actor, collection_scope
from app.api.deps import (
    CurrentCollection,
    CurrentTenant,
    DbSession,
    collection_principal,
    fetch_collection,
    require_write_access,
)
from app.billing.context import current_billing_actor
from app.config import get_settings
from app.core.errors import (
    DemoReadOnlyError,
    DocumentNotReadyError,
    DocumentRestrictedError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.core.idempotency import replay_headers, run_idempotent
from app.core.rate_limit import rate_limit
from app.db.models import Collection, Document, DocumentStatus
from app.generation.tasks import suggest_questions
from app.ingestion import service as ingestion_service
from app.ingestion.mime import EXT_BY_MIME
from app.storage import get_storage
from app.storage.lifecycle import lock_tenant_files

router = APIRouter(prefix="/v1", tags=["documents"])

_UPLOAD_ERROR_EXAMPLES: dict[int | str, dict[str, Any]] = {
    409: {
        "description": "Identical file already exists in this collection",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "https://docqa.dev/errors/duplicate_document",
                    "title": "Duplicate document",
                    "status": 409,
                    "detail": "Identical file already exists in this collection.",
                    "code": "duplicate_document",
                    "existing_document_id": "8b7f6c77-9ffb-466d-b549-327a2244e186",
                    "request_id": "d41d8cd98f00b204e9800998ecf8427e",
                }
            }
        },
    },
    413: {"description": "File exceeds MAX_UPLOAD_MB or the account's 50 MB storage limit"},
    415: {"description": "Not a PDF/DOCX/MD/TXT file (magic-byte check)"},
    429: {"description": "Upload rate limit exceeded (see Retry-After)"},
}


class DocumentAccepted(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    status: str
    error: str | None
    page_count: int | None
    created_at: datetime
    processed_at: datetime | None
    # restricted content labels found in the document's sections (empty = all open)
    access_labels: list[str] = []


@router.post(
    "/collections/{collection_id}/documents",
    status_code=202,
    response_model=DocumentAccepted,
    dependencies=[Depends(rate_limit("upload"))],
    responses=_UPLOAD_ERROR_EXAMPLES,
    description=(
        "Accepts a file for background ingestion. Supports the `Idempotency-Key` header: "
        "a repeated POST with the same key replays the stored response "
        "(`X-Idempotency-Replay: true`) instead of creating anything."
    ),
)
async def upload_document(
    collection: CurrentCollection,
    file: UploadFile,
    db: DbSession,
    request: Request,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Document | JSONResponse:
    require_write_access(request, collection)
    if idempotency_key is None:
        return await ingestion_service.save_upload(db, collection, file)

    async def _handler() -> tuple[int, dict[str, Any]]:
        document = await ingestion_service.save_upload(db, collection, file)
        return 202, {"id": str(document.id), "status": document.status}

    # Multipart data is already spooled by Starlette. Hash in bounded chunks and
    # rewind, binding this key to the operation, destination and exact upload.
    hasher = hashlib.sha256()
    size = 0
    head = b""
    while chunk := await file.read(ingestion_service.READ_CHUNK_BYTES):
        if not head:
            head = chunk[:8192]
        size += len(chunk)
        if size > get_settings().max_upload_bytes:
            raise PayloadTooLargeError("File exceeds the upload limit.")
        hasher.update(chunk)
    await file.seek(0)
    mime = ingestion_service._detect_mime(head, file.filename)
    fingerprint = hashlib.sha256(
        f"upload|{collection.id}|{collection.data_version}|{mime}|{hasher.hexdigest()}".encode()
    ).hexdigest()
    result = await run_idempotent(collection.tenant_id, idempotency_key, _handler, fingerprint)
    return JSONResponse(result.body, status_code=result.status, headers=replay_headers(result))


@router.get(
    "/collections/{collection_id}/documents",
    response_model=list[DocumentOut],
    dependencies=[Depends(rate_limit("default"))],
    description=(
        "Newest first. `limit`/`offset` page through large collections; both optional, "
        "so existing full-list consumers keep working. `X-Total-Count` always carries "
        "the collection's total."
    ),
)
async def list_documents(
    collection: CurrentCollection,
    db: DbSession,
    response: Response,
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentOut]:
    total = await db.scalar(
        select(func.count()).select_from(Document).where(Document.collection_id == collection.id)
    )
    response.headers["X-Total-Count"] = str(total or 0)

    # id as tiebreak: bulk-seeded documents share created_at, pages must not overlap
    stmt = (
        select(Document)
        .where(Document.collection_id == collection.id)
        .order_by(Document.created_at.desc(), Document.id)
    )
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    documents = list(result.scalars().all())
    labels = await restricted_labels_by_document(db, [d.id for d in documents])
    return [
        DocumentOut.model_validate(d).model_copy(update={"access_labels": labels.get(d.id, [])})
        for d in documents
    ]


async def _get_scoped_document(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: DbSession,
    *,
    lock: bool = False,
    actor: Actor | None = None,
) -> Document:
    # tenant scope in the query itself: a foreign document reads as 404
    statement = (
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(
            Document.id == document_id,
            collection_scope(actor) if actor else Collection.tenant_id == tenant_id,
        )
    )
    if lock:
        statement = statement.with_for_update(of=Document)
    result = await db.execute(statement)
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document not found.")
    return document


@router.get(
    "/documents/{document_id}",
    response_model=DocumentOut,
    dependencies=[Depends(rate_limit("default"))],
)
async def get_document(
    document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession, request: Request
) -> DocumentOut:
    document = await _get_scoped_document(document_id, tenant.id, db, actor=request.state.actor)
    labels = await restricted_labels_by_document(db, [document.id])
    return DocumentOut.model_validate(document).model_copy(
        update={"access_labels": labels.get(document.id, [])}
    )


@router.get(
    "/documents/{document_id}/file",
    response_class=FileResponse,
    dependencies=[Depends(rate_limit("default"))],
    responses={
        403: {"description": "The document holds sections the given role may not read"},
        404: {"description": "Unknown document (or another tenant's)"},
    },
    description=(
        "The original uploaded file, served inline — powers the in-app reader. `role` "
        "applies the same access labels as retrieval: a file with a section the role "
        "cannot read is refused as a whole (403 `document_restricted`), because the file "
        "cannot be served partially. Omitted → the least-privileged role."
    ),
)
async def get_document_file(
    document_id: uuid.UUID,
    tenant: CurrentTenant,
    db: DbSession,
    request: Request,
    role: Annotated[str | None, Query(max_length=50)] = None,
) -> FileResponse:
    # Keep status and classification stable against deletion/reprocessing until
    # access has been decided (missing chunks must never mean public access).
    actor: Actor = request.state.actor
    document = await _get_scoped_document(document_id, tenant.id, db, lock=True, actor=actor)
    collection = await fetch_collection(db, tenant.id, document.collection_id, actor)
    principal = await collection_principal(db, collection, actor, role)
    if principal.role != "owner" and document.status != DocumentStatus.READY:
        raise DocumentNotReadyError(
            "The original is available only after successful processing and access classification.",
            document_status=document.status,
        )
    labels = (await restricted_labels_by_document(db, [document.id])).get(document.id, [])
    blocked = [label for label in labels if not principal.sees(label)]
    if blocked:
        raise DocumentRestrictedError(
            "This document contains sections restricted to another group.",
            labels=blocked,
            role=principal.role,
        )
    path = await anyio.to_thread.run_sync(
        get_storage().path_for,
        str(collection.tenant_id),
        document.sha256,
        EXT_BY_MIME.get(document.mime_type, ""),
    )
    if not path.is_file():
        raise NotFoundError("Document not found.")
    # ASCII fallback + RFC 5987 filename* so non-ASCII names survive the header
    ascii_name = (
        re.sub(r'[\x00-\x1f\x7f"\\]', "_", document.filename.encode("ascii", "ignore").decode())
        or "file"
    )
    return FileResponse(
        path,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": (
                f'inline; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(document.filename, safe='')}"
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/documents/{document_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(rate_limit("default"))],
)
async def delete_document(
    document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession, request: Request
) -> None:
    await lock_tenant_files(db, tenant.id)
    document = await _get_scoped_document(document_id, tenant.id, db, actor=request.state.actor)
    collection = await db.scalar(
        select(Collection)
        .where(Collection.id == document.collection_id, collection_scope(request.state.actor))
        .with_for_update()
    )
    if collection is None:
        raise NotFoundError("Collection not found.")
    require_write_access(request, collection)
    if collection.read_only:
        raise DemoReadOnlyError("This collection is read-only.")
    sha256, mime_type = document.sha256, document.mime_type
    collection_id = document.collection_id
    collection.data_version += 1
    collection.suggested_questions = None
    payer = current_billing_actor.get()
    collection.suggestion_billing_user_id = payer.user_id if payer else None
    collection.suggestion_billing_ip_digest = payer.ip_digest if payer else None
    collection.suggestion_revision += 1
    revision = collection.suggestion_revision

    await db.delete(document)  # chunks go with it (FK cascade)
    await db.commit()

    # the stored file is content-addressed per tenant; keep it while other documents reference it
    await ingestion_service.delete_document_file_if_unreferenced(db, tenant.id, sha256, mime_type)
    await db.commit()

    # the corpus shrank — refresh the collection's suggested questions (worker-side)
    if get_settings().suggested_questions_enabled:
        try:
            suggest_questions.delay(str(collection_id), revision)
        except Exception:
            # The deletion has succeeded; a best-effort suggestion refresh must
            # not turn its response into a misleading 500.
            ingestion_service.log.warning(
                "suggestions_enqueue_failed", collection_id=str(collection_id)
            )


@router.post(
    "/documents/{document_id}/reprocess",
    status_code=202,
    response_model=DocumentAccepted,
    dependencies=[Depends(rate_limit("upload"))],
)
async def retry_document(
    document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession, request: Request
) -> DocumentAccepted:
    await lock_tenant_files(db, tenant.id)
    document = await _get_scoped_document(document_id, tenant.id, db, actor=request.state.actor)
    collection = await db.scalar(
        select(Collection)
        .where(Collection.id == document.collection_id, collection_scope(request.state.actor))
        .with_for_update()
    )
    if collection is None:
        raise NotFoundError("Collection not found.")
    require_write_access(request, collection)
    await db.refresh(document, with_for_update=True)
    if document.status != DocumentStatus.FAILED:
        raise DocumentNotReadyError("Only a failed document can be retried.")
    await ingestion_service.retry_failed_document(db, collection, document)
    return DocumentAccepted(id=document.id, status=DocumentStatus.PENDING)
