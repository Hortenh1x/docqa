"""Integration fixtures: real Postgres (pgvector) + Redis via testcontainers.

Containers are session-scoped; alembic migrates once; tables are truncated between
tests (faster than re-creating). Celery runs eagerly and every provider is a stub —
no network beyond the two containers.
"""

import os
import uuid

import pytest
from sqlalchemy import text


@pytest.fixture(scope="session")
def _containers():
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    with (
        PostgresContainer(
            "pgvector/pgvector:pg18",
            username="docqa",
            password="docqa",
            dbname="docqa",
            driver="asyncpg",
        ) as pg,
        RedisContainer("redis:7-alpine") as redis,
    ):
        db_url = pg.get_connection_url()
        redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"
        yield db_url, redis_url


@pytest.fixture(scope="session")
def app_env(_containers, tmp_path_factory):
    db_url, redis_url = _containers
    os.environ["DATABASE_URL"] = db_url
    os.environ["DATABASE_URL_SYNC"] = db_url.replace("+asyncpg", "+psycopg")
    os.environ["REDIS_URL"] = redis_url
    os.environ["EMBEDDING_PROVIDER"] = "stub"
    os.environ["STORAGE_DIR"] = str(tmp_path_factory.mktemp("storage"))

    import app.core.redis as core_redis
    import app.db.base as db_base
    import app.db.sync as db_sync
    from app.config import get_settings

    get_settings.cache_clear()
    # lazy singletons may have been built against the local .env — reset them
    db_base._engine = None
    db_base._sessionmaker = None
    db_sync._engine = None
    db_sync._sessionmaker = None
    core_redis._client = None

    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")

    from app.workers.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    yield

    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
async def _dispose_clients(app_env):
    yield
    from app.core.redis import close_redis
    from app.db.base import dispose_engine

    await close_redis()
    await dispose_engine()


@pytest.fixture(autouse=True)
async def _clean_state(app_env):
    yield
    from app.core.redis import get_redis
    from app.db.base import get_engine
    from app.db.models import Base

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await get_redis().flushdb()


@pytest.fixture
async def client(app_env):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def make_tenant(app_env):
    """Factory: creates a tenant with one API key, returns id/key/headers."""

    async def _make(active: bool = True) -> dict:
        from app.core.security import generate_api_key
        from app.db.base import get_sessionmaker
        from app.db.models import ApiKey, Tenant

        async with get_sessionmaker()() as session:
            tenant = Tenant(name=f"tenant-{uuid.uuid4().hex[:6]}", is_active=active)
            session.add(tenant)
            await session.flush()
            plaintext, prefix, key_hash = generate_api_key()
            session.add(ApiKey(tenant_id=tenant.id, prefix=prefix, key_hash=key_hash))
            await session.commit()
            return {
                "id": tenant.id,
                "key": plaintext,
                "prefix": prefix,
                "headers": {"Authorization": f"Bearer {plaintext}"},
            }

    return _make


@pytest.fixture
async def tenant(make_tenant):
    return await make_tenant()
