"""Document upload, listing, status and deletion."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Response, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import CurrentCollection, CurrentTenant, DbSession
from app.core.errors import NotFoundError
from app.db.models import Collection, Document
from app.ingestion import service as ingestion_service

router = APIRouter(prefix="/v1", tags=["documents"])


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
    "/collections/{collection_id}/documents", status_code=202, response_model=DocumentAccepted
)
async def upload_document(
    collection: CurrentCollection, file: UploadFile, db: DbSession
) -> Document:
    return await ingestion_service.save_upload(db, collection, file)


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentOut])
async def list_documents(collection: CurrentCollection, db: DbSession) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.collection_id == collection.id)
        .order_by(Document.created_at.desc())
    )
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


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession) -> Document:
    return await _get_scoped_document(document_id, tenant.id, db)


@router.delete("/documents/{document_id}", status_code=204, response_class=Response)
async def delete_document(document_id: uuid.UUID, tenant: CurrentTenant, db: DbSession) -> None:
    document = await _get_scoped_document(document_id, tenant.id, db)
    sha256, mime_type = document.sha256, document.mime_type

    await db.delete(document)  # chunks go with it (FK cascade)
    await db.commit()

    # the stored file is content-addressed per tenant; keep it while other documents reference it
    await ingestion_service.delete_document_file_if_unreferenced(db, tenant.id, sha256, mime_type)
