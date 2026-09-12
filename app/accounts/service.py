"""Account lifecycle. Personal tenants are created only by the server."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.errors import InvalidCredentialsError
from app.accounts.mail import Mailer
from app.accounts.passwords import (
    hash_password,
    validate_password,
    verify_password,
)
from app.accounts.tokens import consume_token, send_link
from app.config import get_settings
from app.db.models import AccountSession, AccountToken, Collection, Tenant, User


async def register(db: AsyncSession, email: str, password: str, mailer: Mailer) -> None:
    await validate_password(password)
    encoded = await hash_password(password)
    # Serialize duplicate registrations without using a rollback that would expire
    # the caller's session. Email is never interpolated into SQL.
    from sqlalchemy import text

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:email, 9))"), {"email": email}
    )
    user = await db.scalar(select(User).where(User.email == email).with_for_update())
    if user is None:
        tenant = Tenant(name="Personal documents", kind="personal")
        db.add(tenant)
        await db.flush()
        user = User(tenant_id=tenant.id, email=email, password_hash=encoded)
        db.add(user)
        db.add(
            Collection(
                tenant_id=tenant.id,
                name="My documents",
                slug="my-documents",
                embedding_model=get_settings().embedding_model_id,
            )
        )
        await db.flush()
    if user.is_active and not user.email_verified:
        await send_link(db, user, "verify", mailer)
    else:
        await mailer.send(
            email,
            "Your DocQA account",
            "If you already have a DocQA account, sign in or request a password reset.",
        )


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(
        select(User)
        .join(Tenant, User.tenant_id == Tenant.id)
        .where(
            User.email == email,
            User.is_active.is_(True),
            Tenant.is_active.is_(True),
            Tenant.kind == "personal",
        )
        # NO KEY UPDATE still serializes credential changes, while allowing the
        # KEY SHARE lock of a concurrent billing reservation's User foreign key.
        .with_for_update(of=User, key_share=True)
        # load_session may have cached this entity before a concurrent email
        # proof/password reset. Verify the credentials read under this lock.
        .execution_options(populate_existing=True)
    )
    if not await verify_password(user.password_hash if user else None, password) or user is None:
        raise InvalidCredentialsError()
    return user


async def request_link(db: AsyncSession, email: str, kind: str, mailer: Mailer) -> None:
    user = await db.scalar(
        select(User)
        .join(Tenant, User.tenant_id == Tenant.id)
        .where(
            User.email == email,
            User.is_active.is_(True),
            Tenant.is_active.is_(True),
            Tenant.kind == "personal",
        )
        .with_for_update(of=User)
    )
    if user is not None and (kind == "reset" or not user.email_verified):
        await send_link(db, user, "reset" if kind == "reset" else "verify", mailer)
    else:
        # Take the same delivery path for unknown/ineligible addresses, including
        # SMTP outages. Otherwise 202 versus 503 would reveal account existence.
        await mailer.send(
            email,
            "Your DocQA account request",
            "If you have an eligible DocQA account, use the link in your account email. "
            "Otherwise you can register on DocQA. Ignore this email if you did not request it.",
        )


async def verify_email(db: AsyncSession, token: str, password: str) -> User:
    # Registration can be started by anyone knowing an email address. Only the
    # mailbox owner completing this proof may establish the verified credentials.
    await validate_password(password)
    encoded = await hash_password(password)
    user = await consume_token(db, token, "verify")
    user.password_hash = encoded
    user.email_verified = True
    await _revoke_credentials(db, user)
    return user


async def reset_password(db: AsyncSession, token: str, password: str) -> None:
    await validate_password(password)
    encoded = await hash_password(password)
    user = await consume_token(db, token, "reset")
    user.password_hash = encoded
    await _revoke_credentials(db, user)


async def _revoke_credentials(db: AsyncSession, user: User) -> None:
    """Caller holds the user lock; earlier sessions and email proofs lose authority."""
    now = datetime.now(UTC)
    await db.execute(
        update(AccountSession)
        .where(AccountSession.user_id == user.id, AccountSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
