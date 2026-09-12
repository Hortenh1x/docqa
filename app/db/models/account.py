"""Account credentials and opaque, revocable browser sessions."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), unique=True
    )
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    email_verified: Mapped[bool] = mapped_column(server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class AccountSession(Base):
    __tablename__ = "account_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    token_hash: Mapped[str] = mapped_column(unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    csrf_token: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(index=True)
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class AccountToken(Base):
    __tablename__ = "account_tokens"
    __table_args__ = (CheckConstraint("kind IN ('verify', 'reset')", name="kind"),)

    token_hash: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(index=True)
    used_at: Mapped[datetime | None]


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"

    key: Mapped[str] = mapped_column(primary_key=True)
    count: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(index=True)
