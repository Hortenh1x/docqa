"""Account storage admission against real PostgreSQL; files/providers remain local."""

import asyncio
import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from .test_accounts import account_client, capture_mail, register_login

# Re-export shared account fixtures without copying browser authentication setup.
__all__ = ["account_client", "capture_mail"]

LIMIT = 50 * 1024 * 1024


@pytest.fixture
def quota_settings(app_env, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_MAX_FILES_PER_COLLECTION", "5")
    monkeypatch.setenv("SUGGESTED_QUESTIONS_ENABLED", "false")
    monkeypatch.setenv("BUDGET_ENABLED", "false")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def owner(account_client, capture_mail, quota_settings):
    client, application = account_client
    session, headers = await register_login(client, capture_mail)
    collections = await client.get("/v1/collections")
    assert collections.status_code == 200, collections.text
    return client, application, headers, collections.json()[0]["id"], session["user"]["id"]


async def prefill(collection_id, size, status="ready", content=None):
    """Metadata can approach 50 MB without writing or embedding large fixture files."""
    from app.db.base import get_sessionmaker
    from app.db.models import Document

    async with get_sessionmaker()() as db:
        document = Document(
            collection_id=uuid.UUID(collection_id),
            filename="prefill.md",
            mime_type="text/markdown",
            size_bytes=size,
            sha256=hashlib.sha256(content or uuid.uuid4().bytes).hexdigest(),
            status=status,
        )
        db.add(document)
        await db.commit()
        return str(document.id)


async def upload(client, headers, collection_id, content=b"A", **kwargs):
    return await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("file.md", content, "text/markdown")},
        headers=headers,
        **kwargs,
    )


async def storage(client, used, count):
    response = await client.get("/v1/storage")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "used_bytes": used,
        "limit_bytes": LIMIT,
        "remaining_bytes": max(0, LIMIT - used),
        "document_count": count,
    }
    assert response.headers["cache-control"] == "private, no-store"


async def test_personal_storage_has_no_file_count_cap(owner):
    client, _, headers, collection_id, _ = owner
    for index in range(7):
        response = await upload(client, headers, collection_id, str(index).encode())
        assert response.status_code == 202, response.text
    await storage(client, 7, 7)


async def test_exact_storage_boundary_accepts_then_one_byte_rejects(owner):
    client, _, headers, collection_id, _ = owner
    await prefill(collection_id, LIMIT - 1)
    response = await upload(client, headers, collection_id)
    assert response.status_code == 202, response.text
    rejected = await upload(client, headers, collection_id, b"B")
    assert rejected.status_code == 413, rejected.text
    assert rejected.json()["code"] == "storage_quota_exceeded"
    assert "50 MB" in rejected.json()["detail"]
    assert "delete" in rejected.json()["detail"].lower()
    await storage(client, LIMIT, 2)


@pytest.mark.parametrize("status", ["pending", "processing", "failed", "ready"])
async def test_every_document_status_consumes_storage(owner, status):
    client, _, headers, collection_id, _ = owner
    await prefill(collection_id, LIMIT, status)
    rejected = await upload(client, headers, collection_id)
    assert rejected.status_code == 413, rejected.text
    assert rejected.json()["code"] == "storage_quota_exceeded"
    await storage(client, LIMIT, 1)


async def test_all_own_collections_count_but_other_accounts_and_public_corpus_do_not(
    owner, capture_mail, make_tenant, monkeypatch
):
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    client, application, headers, collection_id, _ = owner
    other_collection = await client.post(
        "/v1/collections", headers=headers, json={"name": "Second"}
    )
    assert other_collection.status_code == 201, other_collection.text
    second_id = other_collection.json()["id"]
    await prefill(collection_id, LIMIT - 1)
    assert (await upload(client, headers, second_id)).status_code == 202
    rejected = await upload(client, headers, collection_id, b"B")
    assert rejected.status_code == 413, rejected.text

    public = await make_tenant()
    async with get_sessionmaker()() as db:
        collection = Collection(
            tenant_id=public["id"],
            name="Public",
            slug="public",
            embedding_model=get_settings().embedding_model_id,
            is_public=True,
            read_only=True,
        )
        db.add(collection)
        await db.commit()
        public_collection_id = str(collection.id)
    await prefill(public_collection_id, LIMIT * 2)
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(public["id"]))
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as other:
        _, other_headers = await register_login(other, capture_mail, "bob@example.com")
        own = next(c for c in (await other.get("/v1/collections")).json() if not c["is_public"])
        await storage(other, 0, 0)
        response = await upload(other, other_headers, own["id"], b"C")
        assert response.status_code == 202, response.text
        await storage(other, 1, 1)
        # Caller-supplied scope fields cannot select another owner's usage.
        scoped = await other.get(
            "/v1/storage", params={"tenant_id": public["id"], "user_id": owner[4]}
        )
        assert scoped.status_code == 200
        assert scoped.json()["used_bytes"] == 1
    await storage(client, LIMIT, 2)


async def test_copies_in_different_collections_each_consume_bytes(owner):
    client, _, headers, collection_id, _ = owner
    other = await client.post("/v1/collections", headers=headers, json={"name": "Copies"})
    assert other.status_code == 201
    for target in (collection_id, other.json()["id"]):
        assert (await upload(client, headers, target, b"Same content")).status_code == 202
    await storage(client, 2 * len(b"Same content"), 2)


async def test_deleting_document_frees_storage(owner):
    client, _, headers, collection_id, _ = owner
    await prefill(collection_id, LIMIT - 1)
    accepted = await upload(client, headers, collection_id)
    assert accepted.status_code == 202
    assert (await upload(client, headers, collection_id, b"B")).status_code == 413
    deleted = await client.delete(f"/v1/documents/{accepted.json()['id']}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    await storage(client, LIMIT - 1, 1)
    assert (await upload(client, headers, collection_id, b"B")).status_code == 202
    await storage(client, LIMIT, 2)


async def test_existing_over_limit_documents_are_retained(owner):
    client, _, headers, collection_id, _ = owner
    existing_id = await prefill(collection_id, LIMIT + 100)
    await storage(client, LIMIT + 100, 1)
    rejected = await upload(client, headers, collection_id)
    assert rejected.status_code == 413
    document = await client.get(f"/v1/documents/{existing_id}")
    assert document.status_code == 200
    assert document.json()["size_bytes"] == LIMIT + 100


async def test_concurrent_near_limit_uploads_admit_only_one(owner, monkeypatch):
    from app.db.base import get_sessionmaker
    from app.db.models import Collection
    from app.ingestion import service

    client, _, headers, collection_id, _ = owner
    await prefill(collection_id, LIMIT - 1)
    original_lock = service.lock_tenant_files
    both_waiting = asyncio.Event()
    entered = 0

    async def observed_lock(db, tenant_id):
        nonlocal entered
        entered += 1
        if entered == 2:
            both_waiting.set()
        await original_lock(db, tenant_id)

    monkeypatch.setattr(service, "lock_tenant_files", observed_lock)
    async with get_sessionmaker()() as blocker:
        tenant_id = await blocker.scalar(
            select(Collection.tenant_id).where(Collection.id == uuid.UUID(collection_id))
        )
        await original_lock(blocker, tenant_id)
        pending = [
            asyncio.create_task(upload(client, headers, collection_id, content))
            for content in (b"A", b"B")
        ]
        try:
            await asyncio.wait_for(both_waiting.wait(), timeout=5)
            await blocker.commit()
            responses = await asyncio.wait_for(asyncio.gather(*pending), timeout=10)
        finally:
            await blocker.rollback()
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    assert sorted(r.status_code for r in responses) == [202, 413]
    await storage(client, LIMIT, 2)


async def test_duplicate_and_idempotent_replay_keep_their_semantics_at_full_capacity(owner):
    client, _, headers, collection_id, _ = owner
    await prefill(collection_id, LIMIT - 1)
    idem_headers = {**headers, "Idempotency-Key": "storage-boundary"}
    accepted = await upload(client, idem_headers, collection_id)
    assert accepted.status_code == 202
    duplicate = await upload(client, headers, collection_id)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["code"] == "duplicate_document"
    assert duplicate.json()["existing_document_id"] == accepted.json()["id"]
    replay = await upload(client, idem_headers, collection_id)
    assert replay.status_code == 202, replay.text
    assert replay.headers["x-idempotency-replay"] == "true"
    assert replay.json() == accepted.json()
    await storage(client, LIMIT, 2)


async def test_failed_validation_and_storage_write_do_not_consume_capacity(owner, monkeypatch):
    from app.storage.errors import StorageUnavailableError
    from app.storage.local import LocalStorage

    client, _, headers, collection_id, _ = owner
    await prefill(collection_id, LIMIT - 1)
    invalid = await upload(client, headers, collection_id, b"\xff")
    assert invalid.status_code == 415

    def unavailable(*args):
        raise StorageUnavailableError("Fixture storage outage.")

    with monkeypatch.context() as failed_storage:
        failed_storage.setattr(LocalStorage, "store", unavailable)
        failed = await upload(client, headers, collection_id)
        assert failed.status_code == 503
        await storage(client, LIMIT - 1, 1)
    assert (await upload(client, headers, collection_id)).status_code == 202
    await storage(client, LIMIT, 2)


async def test_failed_db_commit_does_not_consume_capacity(owner, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import Document

    client, application, headers, collection_id, _ = owner
    await prefill(collection_id, LIMIT - 1)
    original_commit = AsyncSession.commit

    async def failing_commit(db):
        if any(isinstance(row, Document) for row in db.new):
            raise OperationalError("fixture", {}, Exception("fixture database outage"))
        await original_commit(db)

    with monkeypatch.context() as failed_db:
        failed_db.setattr(AsyncSession, "commit", failing_commit)
        async with AsyncClient(
            transport=ASGITransport(app=application, raise_app_exceptions=False),
            base_url="https://api.test",
            cookies=client.cookies,
        ) as failed_client:
            failed = await upload(failed_client, headers, collection_id)
            assert failed.status_code == 500
        await storage(client, LIMIT - 1, 1)
    assert (await upload(client, headers, collection_id)).status_code == 202
    await storage(client, LIMIT, 2)


async def test_ingestion_provider_failure_retains_original_and_counts_it_once(owner, monkeypatch):
    from app.ingestion import tasks

    class FailedProvider:
        async def embed(self, texts):
            raise RuntimeError("Fixture provider outage.")

    client, _, headers, collection_id, _ = owner
    monkeypatch.setattr(tasks, "get_embedding_provider", lambda settings: FailedProvider())
    accepted = await upload(client, headers, collection_id)
    assert accepted.status_code == 202
    document = await client.get(f"/v1/documents/{accepted.json()['id']}")
    assert document.json()["status"] == "failed"
    await storage(client, 1, 1)


async def test_storage_requires_account_even_for_public_and_service_api_keys(
    account_client, make_tenant, monkeypatch, quota_settings
):
    from app.config import get_settings

    client, _ = account_client
    public = await make_tenant()
    service = await make_tenant()
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(public["id"]))
    get_settings.cache_clear()
    for headers in ({}, public["headers"], service["headers"]):
        response = await client.get("/v1/storage", headers=headers)
        assert response.status_code == 401, response.text
    await client.get("/v1/auth/session")
    assert (await client.get("/v1/storage")).status_code == 401


async def test_unverified_owner_can_read_storage_but_cannot_upload(
    account_client, capture_mail, quota_settings
):
    client, _ = account_client
    _, headers = await register_login(client, capture_mail, verified=False)
    collection_id = (await client.get("/v1/collections")).json()[0]["id"]
    await storage(client, 0, 0)
    response = await upload(client, headers, collection_id)
    assert response.status_code == 403
    assert response.json()["code"] == "email_verification_required"
