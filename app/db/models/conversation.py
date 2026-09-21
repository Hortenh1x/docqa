import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("kind IN ('chat', 'legacy')", name="kind"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 120", name="title_length"),
        CheckConstraint(
            "(owner_user_id IS NOT NULL AND owner_guest_session_id IS NULL "
            "AND created_by_api_key_id IS NULL) OR "
            "(owner_user_id IS NULL AND owner_guest_session_id IS NOT NULL "
            "AND created_by_api_key_id IS NULL) OR "
            "(owner_user_id IS NULL AND owner_guest_session_id IS NULL "
            "AND created_by_api_key_id IS NOT NULL)",
            name="one_owner",
        ),
        CheckConstraint("kind <> 'legacy' OR archived_at IS NOT NULL", name="legacy_archived"),
        Index(
            "ix_conversations_collection_archive_activity",
            "collection_id",
            "archived_at",
            text("updated_at DESC"),
            text("id DESC"),
        ),
        Index("ix_conversations_owner_user", "owner_user_id", "collection_id"),
        Index("ix_conversations_owner_guest", "owner_guest_session_id", "collection_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(server_default=text("'New chat'"))
    kind: Mapped[str] = mapped_column(server_default=text("'chat'"))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    owner_guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account_sessions.id", ondelete="RESTRICT")
    )
    created_by_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    archived_at: Mapped[datetime | None]
