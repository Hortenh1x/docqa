import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, UniqueConstraint, text
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
