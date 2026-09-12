"""Stable Google identity and short-lived browser-bound authorization proofs."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class GoogleIdentity(Base):
    __tablename__ = "google_identities"

    issuer: Mapped[str] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class GoogleAuthState(Base):
    __tablename__ = "google_auth_states"

    state_hash: Mapped[str] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_sessions.id", ondelete="CASCADE"), index=True
    )
    nonce: Mapped[str]
    code_verifier: Mapped[str]
    link_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(index=True)
    used_at: Mapped[datetime | None]
