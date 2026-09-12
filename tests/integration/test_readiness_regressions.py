"""Expected-safe regressions from the approved production readiness audit."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.db.base import get_sessionmaker
from app.db.models import Collection, Document

CONTENT = b"# Shared handbook\n\nEmployees get 27 vacation days."


async def collection(client, tenant, name="Sandbox"):
    response = await client.post("/v1/collections", json={"name": name}, headers=tenant["headers"])
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def upload(client, tenant, cid, content=CONTENT, key=None):
    headers = dict(tenant["headers"])
    if key:
        headers["Idempotency-Key"] = key
    return await client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("handbook.md", content, "text/markdown")},
        headers=headers,
    )


async def test_readonly_delete_preserves_document_chunks_and_original(client, tenant, make_tenant):
    cid = await collection(client, tenant)
    document_id = (await upload(client, tenant, cid)).json()["id"]
    async with get_sessionmaker()() as db:
        row = await db.get(Collection, uuid.UUID(cid))
        row.read_only = True
        await db.commit()
    stranger = await make_tenant()
    assert (
        await client.delete(f"/v1/documents/{document_id}", headers=stranger["headers"])
    ).status_code == 404
    denied = await client.delete(f"/v1/documents/{document_id}", headers=tenant["headers"])
    assert denied.status_code == 403
    assert denied.json()["code"] == "demo_readonly"
    original = await client.get(f"/v1/documents/{document_id}/file", headers=tenant["headers"])
    assert original.content == CONTENT
    from app.db.models import Chunk

    async with get_sessionmaker()() as db:
        assert await db.scalar(select(Chunk.id).where(Chunk.document_id == uuid.UUID(document_id)))


async def test_wipe_keeps_other_collection_file_and_removes_final_reference(client, tenant):
    from app.cli import wipe_collection
    from app.ingestion.mime import EXT_BY_MIME
    from app.storage import get_storage

    first, second = await collection(client, tenant), await collection(client, tenant, "Exhibit")
    first_id = (await upload(client, tenant, first)).json()["id"]
    second_id = (await upload(client, tenant, second)).json()["id"]
    async with get_sessionmaker()() as db:
        row = await db.get(Document, uuid.UUID(first_id))
        path = get_storage().path_for(str(tenant["id"]), row.sha256, EXT_BY_MIME[row.mime_type])
    await wipe_collection(uuid.UUID(first))
    original = await client.get(f"/v1/documents/{second_id}/file", headers=tenant["headers"])
    assert original.status_code == 200
    assert original.content == CONTENT
    await wipe_collection(uuid.UUID(second))
    assert not path.exists()


@pytest.mark.parametrize("status", ["pending", "processing", "failed"])
async def test_unclassified_original_is_not_served(client, tenant, monkeypatch, status):
    from app.ingestion.tasks import ingest_document

    monkeypatch.setattr(ingest_document, "delay", lambda *_: None)
    cid = await collection(client, tenant)
    doc_id = (await upload(client, tenant, cid)).json()["id"]
    async with get_sessionmaker()() as db:
        row = await db.get(Document, uuid.UUID(doc_id))
        row.status = status
        await db.commit()
    response = await client.get(f"/v1/documents/{doc_id}/file", headers=tenant["headers"])
    assert response.status_code == 409
    assert response.json()["code"] == "document_not_ready"
    assert CONTENT not in response.content


async def test_demo_cannot_create_extra_collections(client, tenant, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    response = await client.post(
        "/v1/collections", json={"name": "Escape"}, headers=tenant["headers"]
    )
    assert response.status_code == 403


async def test_demo_parallel_uploads_respect_cap(client, tenant, monkeypatch):
    from app.config import get_settings
    from app.ingestion.tasks import ingest_document

    cid = await collection(client, tenant)
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    monkeypatch.setattr(get_settings(), "demo_max_files_per_collection", 1)
    monkeypatch.setattr(ingest_document, "delay", lambda *_: None)
    from starlette.datastructures import UploadFile

    # Every request finishes its first body read before any proceeds to insertion.
    # This deterministically exposes the old pre-read, unlocked quota count.
    original_read = UploadFile.read
    barrier = asyncio.Barrier(4)

    async def simultaneous_read(self, size=-1):
        chunk = await original_read(self, size)
        if chunk:
            await asyncio.wait_for(barrier.wait(), 5)
        return chunk

    monkeypatch.setattr(UploadFile, "read", simultaneous_read)
    responses = await asyncio.gather(
        *(upload(client, tenant, cid, CONTENT + str(i).encode()) for i in range(4))
    )
    assert sorted(r.status_code for r in responses) == [202, 403, 403, 403]


async def test_upload_idempotency_rejects_different_collection_and_bytes(client, tenant):
    first, second = await collection(client, tenant), await collection(client, tenant, "Other")
    original = await upload(client, tenant, first, key="one")
    replay = await upload(client, tenant, first, key="one")
    assert replay.json() == original.json()
    assert replay.headers["x-idempotency-replay"] == "true"
    for cid, content in [(second, CONTENT), (first, CONTENT + b" changed")]:
        changed = await upload(client, tenant, cid, content, key="one")
        assert changed.status_code == 422
        assert changed.json()["code"] == "idempotency_key_reused"


@pytest.mark.parametrize("wipe", [False, True])
@pytest.mark.parametrize("upload_first", [False, True])
async def test_upload_and_removal_never_destroy_a_surviving_file(
    client, tenant, monkeypatch, wipe, upload_first
):
    from app.cli import wipe_collection
    from app.ingestion import service

    first, second = await collection(client, tenant), await collection(client, tenant, "Survivor")
    doc_id = (await upload(client, tenant, first)).json()["id"]
    entered, resume = asyncio.Event(), asyncio.Event()
    original_lock = service.lock_tenant_files
    original_cleanup = service.delete_document_file_if_unreferenced

    async def delayed_lock(db, tid):
        await original_lock(db, tid)
        if asyncio.current_task().get_name() == "new-upload":
            entered.set()
            await resume.wait()

    async def delayed_cleanup(*args):
        entered.set()  # DB removal has committed, but file cleanup has not locked yet.
        await resume.wait()
        await original_cleanup(*args)

    async def remove():
        if wipe:
            await wipe_collection(uuid.UUID(first))
        else:
            assert (
                await client.delete(f"/v1/documents/{doc_id}", headers=tenant["headers"])
            ).status_code == 204

    if upload_first:
        monkeypatch.setattr(service, "lock_tenant_files", delayed_lock)
        uploading = asyncio.create_task(upload(client, tenant, second), name="new-upload")
        await asyncio.wait_for(entered.wait(), 5)
        removing = asyncio.create_task(remove())
    else:
        monkeypatch.setattr(service, "delete_document_file_if_unreferenced", delayed_cleanup)
        # CLI imports this helper directly.
        monkeypatch.setattr("app.cli.delete_document_file_if_unreferenced", delayed_cleanup)
        removing = asyncio.create_task(remove())
        await asyncio.wait_for(entered.wait(), 5)
        uploading = asyncio.create_task(upload(client, tenant, second), name="new-upload")
        await asyncio.wait_for(asyncio.shield(uploading), 5)
    resume.set()
    accepted, _ = await asyncio.wait_for(asyncio.gather(uploading, removing), 10)
    assert accepted.status_code == 202
    original = await client.get(
        f"/v1/documents/{accepted.json()['id']}/file", headers=tenant["headers"]
    )
    assert original.status_code == 200
    assert original.content == CONTENT
    answer = await client.post(
        "/v1/query",
        json={"collection_id": second, "question": "How many vacation days?", "stream": False},
        headers=tenant["headers"],
    )
    assert answer.status_code == 200 and answer.json()["sources"]


async def test_same_bytes_different_storage_extensions_are_cleaned_independently(client, tenant):
    from app.cli import wipe_collection
    from app.config import get_settings

    first, second = await collection(client, tenant), await collection(client, tenant, "Text")
    await upload(client, tenant, first)
    await client.post(
        f"/v1/collections/{second}/documents",
        files={"file": ("same.txt", CONTENT, "text/plain")},
        headers=tenant["headers"],
    )
    await wipe_collection(uuid.UUID(first))
    folder = get_settings().storage_dir / str(tenant["id"])
    assert not list(folder.glob("*.md"))
    assert len(list(folder.glob("*.txt"))) == 1
    await wipe_collection(uuid.UUID(second))
    assert not list(folder.iterdir())


@pytest.mark.parametrize("upload_first", [True, False])
async def test_idempotency_rejects_cross_operation_reuse(client, tenant, upload_first):
    cid = await collection(client, tenant)

    async def ask():
        return await client.post(
            "/v1/query",
            json={"collection_id": cid, "question": "How many vacation days?", "stream": False},
            headers={**tenant["headers"], "Idempotency-Key": "one-operation"},
        )

    first = await upload(client, tenant, cid, key="one-operation") if upload_first else await ask()
    assert first.status_code in (200, 202)
    second = await ask() if upload_first else await upload(client, tenant, cid, key="one-operation")
    assert second.status_code == 422
    assert second.json()["code"] == "idempotency_key_reused"


async def test_authenticated_api_responses_are_not_http_cached(client, tenant):
    response = await client.get("/v1/collections", headers=tenant["headers"])
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_demo_upload_error_reports_the_effective_limit(client, tenant, monkeypatch):
    from app.config import get_settings

    cid = await collection(client, tenant)
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    response = await upload(client, tenant, cid, b"x" * (6 * 1024 * 1024))
    assert response.status_code == 413
    assert "5 MB" in response.json()["detail"]
    assert "25 MB" not in response.json()["detail"]


async def test_role_policy_change_cannot_replay_old_privileged_answer(client, tenant, monkeypatch):
    from app.config import get_settings
    from app.generation.llm.stub import StubLLM

    cid = await collection(client, tenant)
    await upload(client, tenant, cid, b"Access: Finance only. Employees get 27 vacation days.")
    payload = {
        "collection_id": cid,
        "question": "How many vacation days?",
        "stream": False,
        "role": "finance",
    }
    headers = {**tenant["headers"], "Idempotency-Key": "policy-change"}
    assert (await client.post("/v1/query", json=payload, headers=headers)).status_code == 200
    calls = StubLLM.calls
    monkeypatch.setattr(
        get_settings(), "access_roles", {**get_settings().access_roles, "finance": ["all"]}
    )
    replay = await client.post("/v1/query", json=payload, headers=headers)
    assert replay.status_code == 422
    assert StubLLM.calls == calls


async def test_original_authorization_cannot_race_with_chunk_deletion(client, tenant, monkeypatch):
    from app.api.v1 import documents

    first, second = await collection(client, tenant), await collection(client, tenant, "Shared")
    private = b"Access: Finance only. Confidential non-numeric project Magnolia."
    doc_id = (await upload(client, tenant, first, private)).json()["id"]
    other_id = (await upload(client, tenant, second, private)).json()["id"]
    entered, resume = asyncio.Event(), asyncio.Event()
    original_labels = documents.restricted_labels_by_document

    async def paused_labels(*args):
        entered.set()
        await resume.wait()
        return await original_labels(*args)

    monkeypatch.setattr(documents, "restricted_labels_by_document", paused_labels)
    reading = asyncio.create_task(
        client.get(f"/v1/documents/{doc_id}/file", headers=tenant["headers"])
    )
    await asyncio.wait_for(entered.wait(), 5)
    deleting = asyncio.create_task(
        client.delete(f"/v1/documents/{doc_id}", headers=tenant["headers"])
    )
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(deleting), 0.1)
    finally:
        resume.set()
        response, removed = await asyncio.gather(reading, deleting)
    assert response.status_code == 403
    assert private not in response.content
    assert removed.status_code == 204
    original = await client.get(
        f"/v1/documents/{other_id}/file?role=finance", headers=tenant["headers"]
    )
    assert original.content == private
