"""Opaque sessions; only a hash of the bearer cookie is stored."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.errors import CsrfError, InvalidSessionError
from app.config import get_settings
from app.db.models import AccountSession, Tenant, User

COOKIE_NAME = "__Host-docqa_session"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def set_cookie(response: Response, token: str, ttl: int) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=ttl, path="/", secure=True, httponly=True, samesite="lax"
    )


async def load_session(
    request: Request, db: AsyncSession
) -> tuple[AccountSession, User | None] | None:
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        return None
    if not get_settings().accounts_enabled or not 32 <= len(token) <= 128:
        raise InvalidSessionError()
    session = await db.scalar(
        select(AccountSession).where(
            AccountSession.token_hash == token_hash(token),
            AccountSession.revoked_at.is_(None),
            AccountSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None:
        raise InvalidSessionError()
    user = None
    if session.user_id is not None:
        user = await db.scalar(
            select(User)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(
                User.id == session.user_id,
                User.is_active.is_(True),
                Tenant.kind == "personal",
                Tenant.is_active.is_(True),
            )
        )
        if user is None:
            raise InvalidSessionError()
    request.state.account_session = session
    request.state.user = user
    return session, user


def check_csrf(request: Request, session: AccountSession | None) -> None:
    supplied = request.headers.get("x-csrf-token", "")
    if (
        request.headers.get("origin") not in get_settings().auth_origin_list
        or session is None
        or not secrets.compare_digest(supplied, session.csrf_token)
    ):
        raise CsrfError()


async def create_session(
    db: AsyncSession, response: Response, user: User | None = None
) -> AccountSession:
    raw = secrets.token_urlsafe(32)
    ttl = get_settings().auth_session_ttl_s if user else 3600
    session = AccountSession(
        token_hash=token_hash(raw),
        user_id=user.id if user else None,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )
    db.add(session)
    await db.flush()
    set_cookie(response, raw, ttl)
    return session


async def create_authenticated_session(
    db: AsyncSession, request: Request, response: Response, user: User, previous: AccountSession
) -> AccountSession:
    previous.revoked_at = datetime.now(UTC)
    session = await create_session(db, response, user)
    from app.accounts.actor import Actor

    request.state.actor = Actor("account", user.id, user.tenant_id)
    request.state.user = user
    request.state.account_session = session
    return session
