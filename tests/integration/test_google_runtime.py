"""The restricted runtime can use Google tables, including defaults for later tables."""

import uuid
from pathlib import Path

import psycopg
import pytest


async def test_google_runtime_grants_cover_current_and_future_auth_tables(_containers):
    name = "docqa_google_test_" + uuid.uuid4().hex
    password = uuid.uuid4().hex
    admin_url = _containers[0].replace("+asyncpg", "")
    grants = Path("deploy/db/runtime-grants.sql").read_text()  # noqa: ASYNC240
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(
            psycopg.sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            ).format(psycopg.sql.Identifier(name), psycopg.sql.Literal(password))
        )
        try:
            admin.execute(grants.replace("docqa_app", name))
            admin.execute("CREATE TABLE public.google_grant_probe (id integer PRIMARY KEY)")
            runtime_url = admin_url.replace("docqa:docqa@", f"{name}:{password}@")
            with psycopg.connect(runtime_url, autocommit=True) as runtime:
                for table in ("google_identities", "google_auth_states", "google_grant_probe"):
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        assert runtime.execute(
                            "SELECT has_table_privilege(current_user, %s, %s)", (table, privilege)
                        ).fetchone() == (True,)
                    assert runtime.execute(
                        "SELECT has_table_privilege(current_user, %s, 'TRUNCATE')", (table,)
                    ).fetchone() == (False,)
                runtime.execute("INSERT INTO google_grant_probe VALUES (1)")
                runtime.execute("UPDATE google_grant_probe SET id=2")
                assert runtime.execute("SELECT id FROM google_grant_probe").fetchone() == (2,)
                runtime.execute("DELETE FROM google_grant_probe")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    runtime.execute("DROP TABLE google_auth_states")
        finally:
            admin.execute("DROP TABLE IF EXISTS public.google_grant_probe")
            admin.execute(psycopg.sql.SQL("DROP OWNED BY {}").format(psycopg.sql.Identifier(name)))
            admin.execute(psycopg.sql.SQL("DROP ROLE {}").format(psycopg.sql.Identifier(name)))
