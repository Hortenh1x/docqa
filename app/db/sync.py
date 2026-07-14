"""Sync engine and session factory for the Celery worker.

Celery tasks are synchronous; dragging an event loop into them is a reliable source of
bugs. Models are shared with the API — only the engines differ (asyncpg vs psycopg).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_sessionmaker: sessionmaker[Session] | None = None


def get_sync_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().sync_database_url, pool_pre_ping=True)
    return _engine


def get_sync_sessionmaker() -> sessionmaker[Session]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = sessionmaker(get_sync_engine(), expire_on_commit=False)
    return _sessionmaker


@contextmanager
def sync_session() -> Iterator[Session]:
    """Commit on success, rollback on any exception."""
    with get_sync_sessionmaker()() as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
