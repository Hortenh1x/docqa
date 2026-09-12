"""The deployed application role can use the API, but cannot administer PostgreSQL."""

import uuid
from pathlib import Path

import psycopg
import pytest


async def test_runtime_role_supports_ingestion_query_and_delete_without_ddl(
    client, tenant, monkeypatch, _containers
):
    from app.config import get_settings
    from app.db import base, sync
    from tests.integration.test_readiness_regressions import collection, upload

    grants = Path("deploy/db/runtime-grants.sql")
    assert grants.is_file(), "Production runtime grants have not been defined"  # noqa: ASYNC240
    settings = get_settings()
    admin_url = _containers[0].replace("+asyncpg", "")
    assert settings.database_url == _containers[0]
    runtime_password = uuid.uuid4().hex
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(
            psycopg.sql.SQL(
                "CREATE ROLE docqa_app LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
            ).format(psycopg.sql.Literal(runtime_password))
        )
        admin.execute(grants.read_text())  # noqa: ASYNC240
    runtime_url = admin_url.replace("docqa:docqa@", f"docqa_app:{runtime_password}@")
    with psycopg.connect(runtime_url, autocommit=True) as runtime:
        assert (
            runtime.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            == (False,) * 5
        )
        for statement in (
            "CREATE TABLE public.forbidden (id integer)",
            "CREATE TEMP TABLE forbidden (id integer)",
            "CREATE ROLE forbidden_role",
            "TRUNCATE documents CASCADE",
            "DROP TABLE documents CASCADE",
            "UPDATE alembic_version SET version_num = 'invalid'",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                runtime.execute(statement)

    # Both FastAPI and eager Celery use the restricted role for the real application flow.
    with monkeypatch.context() as patch:
        patch.setattr(
            settings, "database_url", runtime_url.replace("postgresql:", "postgresql+asyncpg:")
        )
        patch.setattr(
            settings, "database_url_sync", runtime_url.replace("postgresql:", "postgresql+psycopg:")
        )
        patch.setattr(base, "_engine", None)
        patch.setattr(base, "_sessionmaker", None)
        patch.setattr(sync, "_engine", None)
        patch.setattr(sync, "_sessionmaker", None)
        try:
            cid = await collection(client, tenant)
            accepted = await upload(client, tenant, cid)
            assert accepted.status_code == 202, accepted.text
            doc_id = accepted.json()["id"]
            document = await client.get(f"/v1/documents/{doc_id}", headers=tenant["headers"])
            assert document.json()["status"] == "ready"
            answer = await client.post(
                "/v1/query",
                json={
                    "collection_id": cid,
                    "question": "How many vacation days do employees get?",
                    "stream": False,
                },
                headers=tenant["headers"],
            )
            assert answer.status_code == 200, answer.text
            assert (
                await client.delete(f"/v1/documents/{doc_id}", headers=tenant["headers"])
            ).status_code == 204
        finally:
            await base.dispose_engine()
            if sync._engine is not None:
                sync._engine.dispose()
