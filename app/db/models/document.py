import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        # dedup is enforced by the database, not by SELECT-before-INSERT — concurrency-safe
        UniqueConstraint("collection_id", "sha256"),
        CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="status"),
        Index("ix_documents_collection_id_status", "collection_id", "status"),
        Index("ix_documents_recovery", "status", "next_attempt_at", "lease_expires_at"),
        # one document per external item and source; uploads (source_id null) are exempt
        Index(
            "uq_documents_source_external",
            "source_id",
            "external_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    filename: Mapped[str]
    mime_type: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str]
    status: Mapped[str] = mapped_column(server_default=text("'pending'"))
    error: Mapped[str | None]
    page_count: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    processed_at: Mapped[datetime | None]
    ingestion_attempts: Mapped[int] = mapped_column(server_default=text("0"))
    processing_token: Mapped[uuid.UUID | None]
    lease_expires_at: Mapped[datetime | None]
    next_attempt_at: Mapped[datetime | None]
    last_enqueued_at: Mapped[datetime | None]
    billing_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    billing_ip_digest: Mapped[str | None]
    # set when a source (Notion, ...) created the document; deleting the source keeps
    # the document and nulls the link
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    external_id: Mapped[str | None]
    external_url: Mapped[str | None]
    # provider version marker (Notion last_edited_time); unchanged → the sync skips it
    external_version: Mapped[str | None]
    # OCR: how many pages were recognised rather than extracted, mean confidence (0–100),
    # and the content address of the searchable copy (invisible text layer) in storage
    ocr_pages: Mapped[int | None]
    ocr_confidence: Mapped[float | None]
    searchable_sha256: Mapped[str | None]
    # [{page, size: [w, h], blocks: [{bbox: [x0, y0, x1, y1], text}]}] for OCR'd pages —
    # lets field-extraction evidence be drawn on the scan
    ocr_layout: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
