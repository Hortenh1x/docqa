"""Document upload, listing, status, original-file download and deletion."""

import uuid
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.deps import CurrentCollection, CurrentTenant, DbSession
from app.core.errors import NotFoundError
from app.core.idempotency import replay_headers, run_idempotent
from app.core.rate_limit import rate_limit
from app.db.models import Collection, Document
from app.ingestion import service as ingestion_service
from app.ingestion.mime import EXT_BY_MIME
from app.storage import get_storage

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
    413: {"description": "File exceeds MAX_UPLOAD_MB"},
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
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Document | JSONResponse:
    if idempotency_key is None:
        return await ingestion_service.save_upload(db, collection, file)

    async def _handler() -> tuple[int, dict[str, Any]]:
        document = await ingestion_service.save_upload(db, collection, file)
        return 202, {"id": str(document.id), "status": document.status}

    result = await run_idempotent(collection.tenant_id, idempotency_key, _handler)
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
) -> list[Document]:
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
    return list(result.scalars().all())


async def _get_scoped_document(
    document_id: uuid.UUID, tenant_id: uuid.UUID, db: DbSession
) -> Document:
    # tenant scope in the query itself: a foreign document reads as 404
    result = await db.execute(
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(Document.id == document_id, Collection.tenant_id == tenant_id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document not found.")
    return document


@router.get(
    "/documents/{document_id}",
    response_model=DocumentOut,
    dependencies=[Depends(rate_limit("default"))],
)
async def get_document(document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession) -> Document:
    return await _get_scoped_document(document_id, tenant.id, db)


@router.get(
    "/documents/{document_id}/file",
    response_class=FileResponse,
    dependencies=[Depends(rate_limit("default"))],
    responses={404: {"description": "Unknown document (or another tenant's)"}},
    description="The original uploaded file, served inline — powers the in-app reader.",
)
async def get_document_file(
    document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession
) -> FileResponse:
    document = await _get_scoped_document(document_id, tenant.id, db)
    path = get_storage().path_for(
        str(tenant.id), document.sha256, EXT_BY_MIME.get(document.mime_type, "")
    )
    if not path.is_file():
        raise NotFoundError("Document not found.")
    # ASCII fallback + RFC 5987 filename* so non-ASCII names survive the header
    ascii_name = document.filename.encode("ascii", "ignore").decode().replace('"', "") or "file"
    return FileResponse(
        path,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": (
                f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(document.filename)}"
            )
        },
    )


@router.delete(
    "/documents/{document_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(rate_limit("default"))],
)
async def delete_document(document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession) -> None:
    document = await _get_scoped_document(document_id, tenant.id, db)
    sha256, mime_type = document.sha256, document.mime_type

    await db.delete(document)  # chunks go with it (FK cascade)
    await db.commit()

    # the stored file is content-addressed per tenant; keep it while other documents reference it
    await ingestion_service.delete_document_file_if_unreferenced(db, tenant.id, sha256, mime_type)
