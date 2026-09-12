"""Resolve Google subjects without email merging; preserve account and session authority."""

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import Request, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.google_provider import GoogleIdentityClaims
from app.accounts.google_state import AuthorizationState, GoogleAuthError
from app.accounts.passwords import hash_password
from app.accounts.sessions import COOKIE_NAME, create_authenticated_session, token_hash
from app.config import get_settings
from app.db.models import AccountSession, Collection, GoogleIdentity, Tenant, User


async def _lock_session_and_users(
    db: AsyncSession, request: Request, state: AuthorizationState, user_id: uuid.UUID | None
) -> tuple[AccountSession, User | None]:
    original_user_id = await db.scalar(
        select(AccountSession.user_id).where(AccountSession.id == state.session_id)
    )
    ids = {value for value in (original_user_id, user_id) if value is not None}
    # Credential resets lock User then sessions. Preserve that order, including
    # account switching, and refresh ORM entities loaded before network/lock waits.
    users = {
        user.id: user
        for user in await db.scalars(
            select(User)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(
                User.id.in_(ids),
                User.is_active.is_(True),
                Tenant.is_active.is_(True),
                Tenant.kind == "personal",
            )
            .order_by(User.id)
            .with_for_update(of=User, key_share=True)
            .execution_options(populate_existing=True)
        )
    }
    if users.keys() != ids:
        raise GoogleAuthError()
    current = await db.scalar(
        select(AccountSession)
        .where(
            AccountSession.id == state.session_id,
            AccountSession.token_hash == token_hash(request.cookies.get(COOKIE_NAME, "")),
            AccountSession.revoked_at.is_(None),
            AccountSession.expires_at > datetime.now(UTC),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None or current.user_id != original_user_id:
        raise GoogleAuthError()
    if state.link_user_id is not None:
        linked_user = users.get(state.link_user_id)
        if (
            current.user_id != state.link_user_id
            or linked_user is None
            or not linked_user.email_verified
        ):
            raise GoogleAuthError("link_failed")
    return current, users.get(user_id) if user_id else None


async def resolve_user(
    db: AsyncSession, request: Request, state: AuthorizationState, claims: GoogleIdentityClaims
) -> User:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 17))"),
        {"subject": f"{claims.issuer}|{claims.subject}"},
    )
    # Same lock namespace as email registration; neither path can claim an email twice.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:email, 9))"), {"email": claims.email}
    )
    identity = await db.get(GoogleIdentity, (claims.issuer, claims.subject))
    target_id = (
        state.link_user_id if state.link_user_id else (identity.user_id if identity else None)
    )
    _, user = await _lock_session_and_users(db, request, state, target_id)
    if state.link_user_id is not None:
        if user is None or user.email != claims.email:
            raise GoogleAuthError("link_failed")
        existing = await db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
        if (identity is not None and identity.user_id != user.id) or (
            existing is not None
            and (existing.issuer, existing.subject) != (claims.issuer, claims.subject)
        ):
            raise GoogleAuthError("link_failed")
        if identity is None:
            db.add(GoogleIdentity(issuer=claims.issuer, subject=claims.subject, user_id=user.id))
        return user
    if identity is not None:
        if user is None:
            raise GoogleAuthError()
        return user  # Stable subject keeps its original account/email/tenant.
    if await db.scalar(select(User.id).where(User.email == claims.email)) is not None:
        raise GoogleAuthError("email_exists")
    tenant = Tenant(name="Personal documents", kind="personal")
    db.add(tenant)
    await db.flush()
    user = User(
        tenant_id=tenant.id,
        email=claims.email,
        email_verified=True,
        password_hash=await hash_password(secrets.token_urlsafe(64)),
    )
    db.add(user)
    await db.flush()
    db.add(
        Collection(
            tenant_id=tenant.id,
            name="My documents",
            slug="my-documents",
            embedding_model=get_settings().embedding_model_id,
        )
    )
    db.add(GoogleIdentity(issuer=claims.issuer, subject=claims.subject, user_id=user.id))
    return user


async def complete(
    db: AsyncSession,
    request: Request,
    response: Response,
    state: AuthorizationState,
    claims: GoogleIdentityClaims,
) -> None:
    user = await resolve_user(db, request, state, claims)
    if state.link_user_id is None:
        # The separate billing transaction has a User FK. Commit a newly created
        # account first; otherwise that transaction waits on our own uncommitted row.
        user_id = user.id
        await db.commit()
        if get_settings().budget_enabled:
            from app.billing.context import BillingActor, client_digest
            from app.billing.service import summary

            await summary(BillingActor(client_digest(request), user_id))
        previous, refreshed = await _lock_session_and_users(db, request, state, user_id)
        if refreshed is None:
            raise GoogleAuthError()
        user = refreshed
    else:
        # Linking has no provider calls or independent billing transaction remaining.
        previous, _ = await _lock_session_and_users(db, request, state, user.id)
    await create_authenticated_session(db, request, response, user, previous)
    await db.commit()  # Never expose a new cookie before its durable transaction succeeds.
