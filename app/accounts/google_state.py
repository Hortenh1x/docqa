"""One-time OAuth state; consume it durably before any provider network request."""

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.google_provider import AUTHORIZATION_URL
from app.accounts.sessions import COOKIE_NAME, load_session, token_hash
from app.config import get_settings
from app.core.errors import DomainError
from app.db.models import AccountSession, GoogleAuthState

GoogleErrorCode = Literal["unavailable", "failed", "email_exists", "link_failed"]


class GoogleAuthError(DomainError):
    status = 400
    code = "google_auth_failed"
    title = "Google sign-in could not be completed"

    def __init__(self, reason: GoogleErrorCode = "failed") -> None:
        self.reason = reason
        super().__init__()


@dataclass(frozen=True)
class AuthorizationState:
    session_id: uuid.UUID
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)
    link_user_id: uuid.UUID | None


async def begin(
    db: AsyncSession, request: Request, session: AccountSession, intent: Literal["login", "link"]
) -> str:
    link_user_id = None
    if intent == "link":
        loaded = await load_session(request, db)
        if loaded is None or loaded[1] is None or not loaded[1].email_verified:
            raise GoogleAuthError("link_failed")
        link_user_id = loaded[1].id
    now = datetime.now(UTC)
    # Keep expired PKCE material short-lived without an additional scheduled job.
    expired = (
        select(GoogleAuthState.state_hash).where(GoogleAuthState.expires_at <= now).limit(1000)
    )
    await db.execute(delete(GoogleAuthState).where(GoogleAuthState.state_hash.in_(expired)))
    raw, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    db.add(
        GoogleAuthState(
            state_hash=token_hash(raw),
            session_id=session.id,
            nonce=nonce,
            code_verifier=verifier,
            link_user_id=link_user_id,
            expires_at=now + timedelta(minutes=10),
        )
    )
    await db.flush()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return (
        AUTHORIZATION_URL
        + "?"
        + urlencode(
            {
                "client_id": get_settings().google_client_id,
                "redirect_uri": get_settings().google_redirect_uri,
                "response_type": "code",
                "scope": "openid email",
                "state": raw,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
    )


async def consume(db: AsyncSession, request: Request, raw: str) -> AuthorizationState:
    if not 32 <= len(raw) <= 128:
        raise GoogleAuthError()
    cookie = request.cookies.get(COOKIE_NAME, "")
    if not 32 <= len(cookie) <= 128:
        raise GoogleAuthError()
    now = datetime.now(UTC)
    active_sessions = select(AccountSession.id).where(
        AccountSession.token_hash == token_hash(cookie),
        AccountSession.revoked_at.is_(None),
        AccountSession.expires_at > now,
    )
    # PostgreSQL rechecks the row predicate after concurrent updates: only one callback wins.
    state = await db.scalar(
        update(GoogleAuthState)
        .where(
            GoogleAuthState.state_hash == token_hash(raw),
            GoogleAuthState.session_id.in_(active_sessions),
            GoogleAuthState.used_at.is_(None),
            GoogleAuthState.expires_at > now,
        )
        .values(used_at=now)
        .returning(GoogleAuthState)
    )
    if state is None:
        raise GoogleAuthError()
    result = AuthorizationState(
        state.session_id, state.nonce, state.code_verifier, state.link_user_id
    )
    state.nonce = state.code_verifier = ""
    await db.commit()  # releases the connection/locks before token/JWKS network traffic
    return result
