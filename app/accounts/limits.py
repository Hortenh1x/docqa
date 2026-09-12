"""Durable fixed-window attempt counters, committed even if authentication fails."""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.accounts.errors import AccountUnavailableError
from app.config import get_settings
from app.core.errors import RateLimitedError
from app.db.models import AuthAttempt


@asynccontextmanager
async def _transaction() -> AsyncIterator[AsyncSession]:
    # Cookie validation already holds a request-pool connection. The independently
    # committed counter must not wait for a second slot in that same bounded pool.
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"timeout": 5, "command_timeout": 5},
    )
    try:
        async with AsyncSession(engine) as db, db.begin():
            yield db
    finally:
        await engine.dispose()


def client_address(request: Request) -> str:
    if get_settings().rate_limit_trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "local"


async def check_attempts(request: Request, operation: str, email: str | None = None) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    window = settings.auth_attempt_window_s
    period = int(now.timestamp()) // window
    scopes = [(f"ip:{client_address(request)}", settings.auth_attempt_ip_limit)]
    if email is not None:
        scopes.append((f"email:{email}", settings.auth_attempt_account_limit))
    allowed = True
    try:
        async with _transaction() as db:
            for scope, limit in scopes:
                key = hashlib.sha256(f"{operation}:{scope}:{period}".encode()).hexdigest()
                statement = insert(AuthAttempt).values(
                    key=key, count=1, expires_at=now + timedelta(seconds=2 * window)
                )
                count = await db.scalar(
                    statement.on_conflict_do_update(
                        index_elements=[AuthAttempt.key], set_={"count": AuthAttempt.count + 1}
                    ).returning(AuthAttempt.count)
                )
                allowed = allowed and count is not None and count <= limit
    except (SQLAlchemyError, OSError, TimeoutError):
        raise AccountUnavailableError() from None
    if not allowed:
        raise RateLimitedError(
            "Too many account attempts. Try again later.",
            headers={"Retry-After": str(window - int(now.timestamp()) % window)},
        )
