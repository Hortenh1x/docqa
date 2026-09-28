"""User-defined extraction schemas and the per-document extractions they produce."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ExtractionStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ExtractionSchema(Base):
    __tablename__ = "extraction_schemas"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str]
    description: Mapped[str | None]
    # ordered list of field specs (app/extraction/fields.py FieldSpec)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # cross-field checks as expressions over field names (app/extraction/rules.py)
    rules: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    # also index the extracted values as one retrievable chunk per document
    index_facts: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (
        UniqueConstraint("document_id", "schema_id"),
        CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="status"),
        Index("ix_extractions_schema_id", "schema_id"),
        Index("ix_extractions_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    schema_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_schemas.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(server_default=text("'pending'"))
    processing_token: Mapped[uuid.UUID | None]
    model: Mapped[str | None]
    # {name: {value, confidence, evidence: {...} | None, edited: bool}}
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # [{field, code, message}]
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    prompt_tokens: Mapped[int | None]
    completion_tokens: Mapped[int | None]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    error: Mapped[str | None]
    # the synthetic "facts" chunk when the schema indexes its values
    facts_chunk_id: Mapped[int | None] = mapped_column(BigInteger)
    billing_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    billing_ip_digest: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
