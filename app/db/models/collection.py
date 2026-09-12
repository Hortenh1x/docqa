import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug"),
        CheckConstraint("NOT is_public OR read_only", name="public_read_only"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str]
    slug: Mapped[str]
    # e.g. 'bge-m3' or 'text-embedding-3-small@1024' — guards against mixing embedding models
    embedding_model: Mapped[str]
    # public-demo collections reject uploads (403 demo_readonly)
    read_only: Mapped[bool] = mapped_column(server_default=text("false"))
    is_public: Mapped[bool] = mapped_column(server_default=text("false"))
    # LLM-drafted starter questions the corpus can answer, as
    # [{"question": str, "min_role": str}]; refreshed by the worker whenever the
    # collection's ingestion settles (see app/generation/suggestions.py)
    suggested_questions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    # Incremented by wipe; fences results from queries/suggestions already in flight.
    data_version: Mapped[int] = mapped_column(server_default=text("0"))
    suggestion_billing_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    suggestion_billing_ip_digest: Mapped[str | None]
    suggestion_revision: Mapped[int] = mapped_column(server_default=text("0"))
