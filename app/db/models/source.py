"""External content sources (Notion first) synchronised into a collection.

A source owns the documents it created (``documents.source_id``); deleting the source
keeps them as plain documents. Credentials are stored encrypted (see app/sources/crypto).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SourceKind(enum.StrEnum):
    NOTION = "notion"
    STUB = "stub"  # tests only: an in-memory workspace, never reaches the network


class SyncStatus(enum.StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    SYNCING = "syncing"
    PARTIAL = "partial"  # ran out of time; re-enqueued to finish
    FAILED = "failed"


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("kind IN ('notion', 'stub')", name="kind"),
        CheckConstraint(
            "sync_status IN ('idle', 'queued', 'syncing', 'partial', 'failed')",
            name="sync_status",
        ),
        Index("ix_sources_collection_id", "collection_id"),
        Index("ix_sources_auto_sync", "auto_sync_interval_s", "last_sync_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    kind: Mapped[str]
    name: Mapped[str]
    # Fernet token of the provider credential; never returned by the API
    credentials: Mapped[str]
    # provider-specific selection, e.g. {"root_ids": [...]} for Notion
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # null = manual sync only
    auto_sync_interval_s: Mapped[int | None]
    sync_status: Mapped[str] = mapped_column(server_default=text("'idle'"))
    sync_token: Mapped[uuid.UUID | None]
    lease_expires_at: Mapped[datetime | None]
    last_sync_started_at: Mapped[datetime | None]
    last_sync_at: Mapped[datetime | None]
    last_sync_error: Mapped[str | None]
    last_sync_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # copied onto every document the sync creates so the worker can attribute spend
    billing_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    billing_ip_digest: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
