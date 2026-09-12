"""Audit-only reproductions. Passing assertions CONFIRM the recorded defects.

Run only with the testcontainers fixtures:
  .venv/bin/python -m pytest -p tests.integration.conftest audit/probes.py -v -s
No production endpoints, data or paid providers are used.
"""

import uuid

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def audit_settings(monkeypatch, app_env):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SUGGESTED_QUESTIONS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def collection(client, tenant, name):
    response = await client.post("/v1/collections", json={"name": name}, headers=tenant["headers"])
    assert response.status_code == 201
    return response.json()["id"]


async def upload(client, tenant, cid, content, **headers):
    return await client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("audit.md", content, "text/markdown")},
        headers={**tenant["headers"], **headers},
    )


async def test_read_only_document_can_be_deleted(client, tenant):
    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    cid = await collection(client, tenant, "Read only exhibit")
    accepted = await upload(client, tenant, cid, b"# Exhibit\n\nSynthetic content.")
    assert accepted.status_code == 202
    did = accepted.json()["id"]
    async with get_sessionmaker()() as db:
        record = await db.get(Collection, uuid.UUID(cid))
        record.read_only = True
        await db.commit()
    denied = await upload(client, tenant, cid, b"# Another exhibit")
    assert denied.status_code == 403
    deleted = await client.delete(f"/v1/documents/{did}", headers=tenant["headers"])
    after = await client.get(f"/v1/documents/{did}", headers=tenant["headers"])
    print(
        f"AUDIT read_only=True: upload={denied.status_code}, "
        f"delete={deleted.status_code}, "
        f"subsequent_get={after.status_code}"
    )
    assert deleted.status_code == 204
    assert after.status_code == 404


@pytest.mark.parametrize("status", ["pending", "processing", "failed"])
async def test_unclassified_restricted_original_is_downloadable(
    client, tenant, monkeypatch, status
):
    from app.db.base import get_sessionmaker
    from app.db.models import Document
    from app.ingestion.tasks import ingest_document

    monkeypatch.setattr(ingest_document, "delay", lambda *args: None)
    cid = await collection(client, tenant, f"Unclassified {status}")
    content = (
        b"# Synthetic finance\n\nAccess: Finance only\n\nSynthetic restricted fact: violet otter."
    )
    accepted = await upload(client, tenant, cid, content)
    assert accepted.status_code == 202
    did = accepted.json()["id"]
    async with get_sessionmaker()() as db:
        record = await db.get(Document, uuid.UUID(did))
        record.status = status
        await db.commit()
    response = await client.get(
        f"/v1/documents/{did}/file?role=employee", headers=tenant["headers"]
    )
    print(
        f"AUDIT status={status}, "
        f"role=employee: download={response.status_code}, "
        f"restricted_bytes_returned={response.content == content}"
    )
    assert response.status_code == 200
    assert response.content == content


async def test_demo_key_can_create_additional_writable_collections(client, tenant):
    created = [await collection(client, tenant, f"Extra sandbox {i}") for i in range(3)]
    accepted = [await upload(client, tenant, cid, b"# Synthetic upload") for cid in created]
    print(
        f"AUDIT DEMO_MODE=true: additional_collections={len(created)}, "
        f"upload_statuses={[r.status_code for r in accepted]}"
    )
    assert all(r.status_code == 202 for r in accepted)


async def test_embedding_retry_skips_processing_document(client, tenant, monkeypatch):
    from app.db.base import get_sessionmaker
    from app.db.models import Document
    from app.embeddings.base import EmbeddingError
    from app.ingestion import tasks

    monkeypatch.setattr(tasks.ingest_document, "delay", lambda *args: None)
    cid = await collection(client, tenant, "Transient failure")
    accepted = await upload(client, tenant, cid, b"# Synthetic retry\n\nSome content.")
    did = accepted.json()["id"]
    calls = []

    class BrokenEmbedding:
        async def embed(self, texts):
            calls.append(True)
            raise EmbeddingError("synthetic temporary outage")

    monkeypatch.setattr(tasks, "get_embedding_provider", lambda settings: BrokenEmbedding())
    # First attempt commits PROCESSING, fails, and requests a Celery retry.
    first_exception = None
    try:
        tasks.ingest_document.run(did)
    except Exception as exc:
        first_exception = type(exc).__name__
    # Simulate delivery of the same task, without waiting for the broker countdown.
    tasks.ingest_document.run(did)
    async with get_sessionmaker()() as db:
        record = await db.get(Document, uuid.UUID(did))
        actual = record.status
    print(
        f"AUDIT embedding retry: first_exception={first_exception}, "
        f"embed_calls={len(calls)}, "
        f"final_status={actual}"
    )
    assert len(calls) == 1
    assert actual == "processing"


async def test_upload_idempotency_replays_other_collection(client, tenant):
    first = await collection(client, tenant, "First collection")
    second = await collection(client, tenant, "Second collection")
    one = await upload(
        client, tenant, first, b"# First content", **{"Idempotency-Key": "audit-reuse"}
    )
    two = await upload(
        client, tenant, second, b"# Different content", **{"Idempotency-Key": "audit-reuse"}
    )
    listed = await client.get(f"/v1/collections/{second}/documents", headers=tenant["headers"])
    print(
        f"AUDIT upload key reused across collections: status={two.status_code}, "
        f"replay={two.headers.get('x-idempotency-replay')}, "
        f"second_collection_count={len(listed.json())}"
    )
    assert one.json() == two.json()
    assert listed.json() == []


async def test_security_http_baseline(client):
    for path in ["/.env", "/.git/config", "/backup.sql", "/missing-audit-path"]:
        response = await client.get(path)
        assert response.status_code == 404
        assert "traceback" not in response.text.lower()
    for path in ["/v1/collections", "/v1/roles", "/v1/usage"]:
        assert (await client.get(path)).status_code == 401
    allowed = await client.options(
        "/v1/collections",
        headers={
            "Origin": "http://localhost:3002",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    denied = await client.options(
        "/v1/collections",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    print(
        "AUDIT public paths=404; no-key protected paths=401; "
        f"CORS preflight allowed={allowed.status_code}, "
        f"untrusted={denied.status_code}"
    )
    assert allowed.status_code == 200
    assert denied.status_code == 400


async def test_concurrent_uploads_exceed_demo_cap(client, tenant, monkeypatch):
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ingestion.tasks import ingest_document

    monkeypatch.setenv("DEMO_MAX_FILES_PER_COLLECTION", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(ingest_document, "delay", lambda *args: None)
    cid = await collection(client, tenant, "Concurrent quota")
    original = AsyncSession.execute
    arrived = 0
    barrier = asyncio.Event()

    async def synchronized_count(self, statement, *args, **kwargs):
        nonlocal arrived
        result = await original(self, statement, *args, **kwargs)
        if "count(documents.id)" in str(statement).lower():
            arrived += 1
            if arrived == 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), timeout=5)
        return result

    monkeypatch.setattr(AsyncSession, "execute", synchronized_count)
    responses = await asyncio.gather(
        upload(client, tenant, cid, b"# Parallel one"),
        upload(client, tenant, cid, b"# Parallel two"),
    )
    listed = await client.get(f"/v1/collections/{cid}/documents", headers=tenant["headers"])
    print(
        f"AUDIT configured_cap=1: upload_statuses={[r.status_code for r in responses]}, "
        f"persisted={len(listed.json())}"
    )
    assert [r.status_code for r in responses] == [202, 202]
    assert len(listed.json()) == 2


async def test_enqueue_failure_leaves_unrecoverable_duplicate(client, tenant, monkeypatch):
    from app.ingestion.tasks import ingest_document

    cid = await collection(client, tenant, "Broker outage")

    def unavailable(*args):
        raise RuntimeError("synthetic broker unavailable")

    monkeypatch.setattr(ingest_document, "delay", unavailable)
    with pytest.raises(RuntimeError, match="synthetic broker unavailable"):
        await upload(client, tenant, cid, b"# Broker outage")
    retry = await upload(client, tenant, cid, b"# Broker outage")
    listed = await client.get(f"/v1/collections/{cid}/documents", headers=tenant["headers"])
    print(
        f"AUDIT commit before enqueue failure: retry={retry.status_code}, "
        f"document_status={listed.json()[0]['status']}"
    )
    assert retry.status_code == 409
    assert listed.json()[0]["status"] == "pending"


async def test_database_bootstrap_identity_is_superuser():
    from sqlalchemy import text

    from app.db.base import get_sessionmaker

    async with get_sessionmaker()() as db:
        privileged = await db.scalar(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        )
    print(
        "AUDIT disposable pgvector initialized with POSTGRES_USER=docqa: "
        f"app_identity_superuser={privileged}, live DB grants not inspected"
    )
    assert privileged is True


async def test_provider_config_missing_secret_does_not_fail_startup(monkeypatch):
    import app.main as main
    from app.config import Settings
    from app.embeddings import get_embedding_provider

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://synthetic:synthetic@127.0.0.1:1/synthetic",
        redis_url="redis://127.0.0.1:1/0",
        embedding_provider="openai",
        openai_api_key=None,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        get_embedding_provider(settings)
    print(
        f"AUDIT EMBEDDING_PROVIDER=openai without key: app_created={app is not None}, "
        f"error deferred until provider construction"
    )


async def test_sandbox_wipe_retains_query_text(client, tenant):
    from sqlalchemy import func, select

    from app.cli import wipe_collection
    from app.db.base import get_sessionmaker
    from app.db.models import Document, Query

    cid = await collection(client, tenant, "Nightly wipe")
    accepted = await upload(
        client, tenant, cid, b"# Synthetic travel\n\nEmployees travel by train."
    )
    assert accepted.status_code == 202
    response = await client.post(
        "/v1/query",
        json={"collection_id": cid, "question": "How do employees travel?", "stream": False},
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    await wipe_collection(uuid.UUID(cid))
    async with get_sessionmaker()() as db:
        documents = await db.scalar(select(func.count()).select_from(Document))
        queries = (await db.execute(select(Query))).scalars().all()
    print(
        f"AUDIT nightly wipe: documents_remaining={documents}, "
        f"query_rows_remaining={len(queries)}, "
        f"question_retained={bool(queries and queries[0].question)}"
    )
    assert documents == 0
    assert len(queries) == 1
    assert queries[0].question == "How do employees travel?"


async def test_wipe_removes_original_still_used_by_other_collection(client, tenant):
    from app.cli import wipe_collection

    preserved = await collection(client, tenant, "Preserved exhibit")
    sandbox = await collection(client, tenant, "Sandbox to wipe")
    content = b"# Shared synthetic original\n\nContent-addressed across the tenant."
    first = await upload(client, tenant, preserved, content)
    second = await upload(client, tenant, sandbox, content)
    assert first.status_code == second.status_code == 202
    did = first.json()["id"]
    assert (
        await client.get(f"/v1/documents/{did}/file", headers=tenant["headers"])
    ).status_code == 200
    await wipe_collection(uuid.UUID(sandbox))
    metadata = await client.get(f"/v1/documents/{did}", headers=tenant["headers"])
    original = await client.get(f"/v1/documents/{did}/file", headers=tenant["headers"])
    print(
        "AUDIT wiping sandbox with shared content:",
        f"other_collection_metadata={metadata.status_code}, original_file={original.status_code}",
    )
    assert metadata.status_code == 200
    assert original.status_code == 404
