"""Hashed, expiring, single-use account links; fragments stay out of HTTP/access logs."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.errors import InvalidTokenError
from app.accounts.mail import Mailer
from app.accounts.sessions import token_hash
from app.config import get_settings
from app.db.models import AccountToken, Tenant, User


async def send_link(
    db: AsyncSession, user: User, kind: Literal["verify", "reset"], mailer: Mailer
) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    await db.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.kind == kind,
            AccountToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(32)
    ttl = settings.auth_verify_ttl_s if kind == "verify" else settings.auth_reset_ttl_s
    db.add(
        AccountToken(
            token_hash=token_hash(raw),
            user_id=user.id,
            kind=kind,
            expires_at=now + timedelta(seconds=ttl),
        )
    )
    await db.flush()
    action = "Verify your DocQA email" if kind == "verify" else "Reset your DocQA password"
    url = f"{settings.auth_public_url.rstrip('/')}/account/{kind}#token={raw}"
    await mailer.send(
        user.email,
        action,
        f"{action}:\n\n{url}\n\nThis link expires in {ttl // 60} minutes and can be used once. "
        "If you did not request it, ignore this email.",
    )


async def consume_token(db: AsyncSession, raw: str, kind: Literal["verify", "reset"]) -> User:
    digest = token_hash(raw)
    # Resolve the owner without taking a token lock. Issuance, verification and
    # reset always lock User first, then tokens; the reverse order can deadlock
    # when a credential change invalidates another in-flight proof.
    user_id = await db.scalar(
        select(AccountToken.user_id).where(
            AccountToken.token_hash == digest,
            AccountToken.kind == kind,
            AccountToken.used_at.is_(None),
            AccountToken.expires_at > datetime.now(UTC),
        )
    )
    if user_id is None:
        raise InvalidTokenError()
    user = await db.scalar(
        select(User)
        .join(Tenant, User.tenant_id == Tenant.id)
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            Tenant.is_active.is_(True),
            Tenant.kind == "personal",
        )
        .with_for_update(of=User)
    )
    if user is None:
        raise InvalidTokenError()
    # Another proof may have been consumed, expired or replaced while we waited
    # for the user lock. Only this fresh check can authorize the credential change.
    now = datetime.now(UTC)
    token = await db.scalar(
        select(AccountToken)
        .where(
            AccountToken.token_hash == digest,
            AccountToken.user_id == user.id,
            AccountToken.kind == kind,
            AccountToken.used_at.is_(None),
            AccountToken.expires_at > now,
        )
        .with_for_update()
    )
    if token is None:
        raise InvalidTokenError()
    token.used_at = now
    return user
