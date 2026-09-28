"""Sources API + sync on the stub connector (Celery eager, stub embeddings, no network).

The stub workspace is a process-global dict, so a test edits pages between syncs the way a
Notion user would.
"""

import uuid

import pytest
from sqlalchemy import select

from app.sources.stub import WORKSPACES, StubPage

PAGE_A = "page-a"
PAGE_B = "page-b"


@pytest.fixture
def workspace():
    credential = f"ws-{uuid.uuid4().hex[:8]}"
    WORKSPACES[credential] = {
        PAGE_A: StubPage(
            title="Travel policy",
            markdown="# Travel policy\n\nFlights must be economy class.\n",
            url="https://notion.so/page-a",
        ),
        PAGE_B: StubPage(
            title="Expenses",
            markdown="# Expenses\n\nReceipts are required above 25 EUR.\n",
        ),
    }
    yield credential
    WORKSPACES.pop(credential, None)


@pytest.fixture
async def collection_id(client, tenant) -> str:
    response = await client.post(
        "/v1/collections", json={"name": "Wiki"}, headers=tenant["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create(client, tenant, collection_id, credential, **extra):
    return await client.post(
        f"/v1/collections/{collection_id}/sources",
        json={"kind": "stub", "name": "Company wiki", "token": credential, **extra},
        headers=tenant["headers"],
    )


async def _documents(client, tenant, collection_id):
    response = await client.get(
        f"/v1/collections/{collection_id}/documents", headers=tenant["headers"]
    )
    assert response.status_code == 200
    return {d["filename"]: d for d in response.json()}


async def _chunk_texts(document_id: str) -> list[str]:
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk

    async with get_sessionmaker()() as session:
        rows = await session.scalars(
            select(Chunk.content)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )
        return list(rows)


async def test_create_syncs_and_ingests_pages(client, tenant, collection_id, workspace):
    created = await _create(client, tenant, collection_id, workspace)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["kind"] == "stub"
    assert "token" not in body and "credentials" not in body
    source_id = body["id"]

    # celery eager: the first sync ran inside the request
    detail = await client.get(f"/v1/sources/{source_id}", headers=tenant["headers"])
    assert detail.status_code == 200
    source = detail.json()
    assert source["sync_status"] == "idle", source
    assert source["last_sync_error"] is None
    assert source["last_sync_stats"]["added"] == 2
    assert source["document_count"] == 2
    assert source["last_sync_at"] is not None

    docs = await _documents(client, tenant, collection_id)
    assert set(docs) == {"Travel policy.md", "Expenses.md"}
    travel = docs["Travel policy.md"]
    assert travel["status"] == "ready"
    assert travel["source_id"] == source_id
    assert travel["external_url"] == "https://notion.so/page-a"
    assert travel["mime_type"] == "text/markdown"
    assert "Flights must be economy class." in "".join(await _chunk_texts(travel["id"]))

    listed = await client.get(f"/v1/collections/{collection_id}/sources", headers=tenant["headers"])
    assert [s["id"] for s in listed.json()] == [source_id]


async def test_resync_applies_updates_and_removals_only(client, tenant, collection_id, workspace):
    created = await _create(client, tenant, collection_id, workspace)
    source_id = created.json()["id"]
    before = await _documents(client, tenant, collection_id)
    travel_id = before["Travel policy.md"]["id"]

    # nothing changed → nothing re-rendered
    resync = await client.post(f"/v1/sources/{source_id}/sync", headers=tenant["headers"])
    assert resync.status_code == 202, resync.text
    stats = (await client.get(f"/v1/sources/{source_id}", headers=tenant["headers"])).json()[
        "last_sync_stats"
    ]
    assert stats["unchanged"] == 2 and stats["added"] == 0 and stats["updated"] == 0

    # edit one page, delete the other
    pages = WORKSPACES[workspace]
    pages[PAGE_A].markdown = "# Travel policy\n\nBusiness class is allowed over 6 hours.\n"
    pages[PAGE_A].version = "2"
    del pages[PAGE_B]
    resync = await client.post(f"/v1/sources/{source_id}/sync", headers=tenant["headers"])
    assert resync.status_code == 202, resync.text
    stats = (await client.get(f"/v1/sources/{source_id}", headers=tenant["headers"])).json()[
        "last_sync_stats"
    ]
    assert stats == {
        **stats,
        "updated": 1,
        "removed": 1,
        "added": 0,
        "unchanged": 0,
        "duplicates": 0,
    }

    after = await _documents(client, tenant, collection_id)
    assert set(after) == {"Travel policy.md"}
    assert after["Travel policy.md"]["id"] == travel_id  # updated in place, same id
    assert after["Travel policy.md"]["status"] == "ready"
    text = "".join(await _chunk_texts(travel_id))
    assert "Business class is allowed" in text
    assert "economy" not in text

    # the previous rendering's file is gone, the new one is served
    original = await client.get(f"/v1/documents/{travel_id}/file", headers=tenant["headers"])
    assert original.status_code == 200
    assert b"Business class" in original.content


async def test_duplicate_text_and_broken_pages_are_counted_not_fatal(
    client, tenant, collection_id, workspace
):
    pages = WORKSPACES[workspace]
    pages["page-c"] = StubPage(title="Copy", markdown=pages[PAGE_A].markdown)
    pages["page-d"] = StubPage(title="Broken", markdown="x", broken=True)
    created = await _create(client, tenant, collection_id, workspace)
    assert created.status_code == 201, created.text
    stats = (
        await client.get(f"/v1/sources/{created.json()['id']}", headers=tenant["headers"])
    ).json()["last_sync_stats"]
    assert stats["added"] == 2
    assert stats["duplicates"] == 1
    assert stats["skipped_errors"] == 1
    assert stats["errors"] == ["Broken: stub page marked broken"]


async def test_deleting_the_source_keeps_documents(client, tenant, collection_id, workspace):
    created = await _create(client, tenant, collection_id, workspace)
    source_id = created.json()["id"]
    deleted = await client.delete(f"/v1/sources/{source_id}", headers=tenant["headers"])
    assert deleted.status_code == 204
    assert (
        await client.get(f"/v1/sources/{source_id}", headers=tenant["headers"])
    ).status_code == 404
    docs = await _documents(client, tenant, collection_id)
    assert len(docs) == 2
    assert all(d["source_id"] is None for d in docs.values())
    assert all(d["status"] == "ready" for d in docs.values())


async def test_bad_credentials_and_scope(client, tenant, make_tenant, collection_id, workspace):
    rejected = await _create(client, tenant, collection_id, "no-such-workspace")
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "invalid_source_credentials"

    created = await _create(client, tenant, collection_id, workspace)
    source_id = created.json()["id"]
    other = await make_tenant()
    for method, path in (
        ("GET", f"/v1/sources/{source_id}"),
        ("POST", f"/v1/sources/{source_id}/sync"),
        ("DELETE", f"/v1/sources/{source_id}"),
        ("GET", f"/v1/collections/{collection_id}/sources"),
    ):
        response = await client.request(method, path, headers=other["headers"])
        assert response.status_code == 404, (method, path, response.text)


async def test_sync_in_progress_is_a_conflict(client, tenant, collection_id, workspace):
    from datetime import UTC, datetime, timedelta

    from app.db.base import get_sessionmaker
    from app.db.models import Source

    created = await _create(client, tenant, collection_id, workspace)
    source_id = created.json()["id"]
    async with get_sessionmaker()() as session:
        source = await session.get(Source, uuid.UUID(source_id))
        source.sync_status = "syncing"
        source.lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
        await session.commit()
    conflict = await client.post(f"/v1/sources/{source_id}/sync", headers=tenant["headers"])
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "source_sync_in_progress"


async def test_sources_disabled_without_key(client, tenant, collection_id, workspace, monkeypatch):
    from app.config import get_settings

    monkeypatch.delenv("SOURCE_CREDENTIALS_KEY")
    get_settings.cache_clear()
    try:
        response = await _create(client, tenant, collection_id, workspace)
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503
    assert response.json()["code"] == "sources_disabled"


async def test_per_collection_source_limit(client, tenant, collection_id, workspace, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SOURCE_MAX_PER_COLLECTION", "1")
    get_settings.cache_clear()
    try:
        first = await _create(client, tenant, collection_id, workspace)
        assert first.status_code == 201
        second = await _create(client, tenant, collection_id, workspace, name="Again")
    finally:
        get_settings.cache_clear()
    assert second.status_code == 422
    assert second.json()["code"] == "source_limit_exceeded"


async def test_schedule_picks_up_due_auto_sync_sources(client, tenant, collection_id, workspace):
    from datetime import UTC, datetime, timedelta

    from app.db.base import get_sessionmaker
    from app.db.models import Source
    from app.sources.tasks import schedule_syncs

    created = await _create(client, tenant, collection_id, workspace, auto_sync_interval_s=300)
    source_id = uuid.UUID(created.json()["id"])
    assert schedule_syncs() == 0  # just synced

    async with get_sessionmaker()() as session:
        source = await session.get(Source, source_id)
        source.last_sync_at = datetime.now(UTC) - timedelta(seconds=301)
        await session.commit()
    WORKSPACES[workspace]["page-z"] = StubPage(title="New", markdown="# New\n\nFresh page.\n")
    assert schedule_syncs() == 1
    docs = await _documents(client, tenant, collection_id)
    assert "New.md" in docs


async def test_truncated_listing_never_deletes_beyond_the_cap(
    client, tenant, collection_id, workspace, monkeypatch
):
    from app.config import get_settings

    created = await _create(client, tenant, collection_id, workspace)
    source_id = created.json()["id"]
    assert len(await _documents(client, tenant, collection_id)) == 2

    monkeypatch.setenv("SOURCE_MAX_DOCUMENTS", "1")
    get_settings.cache_clear()
    try:
        resync = await client.post(f"/v1/sources/{source_id}/sync", headers=tenant["headers"])
    finally:
        get_settings.cache_clear()
    assert resync.status_code == 202
    stats = (await client.get(f"/v1/sources/{source_id}", headers=tenant["headers"])).json()[
        "last_sync_stats"
    ]
    assert stats["truncated"] is True and stats["listed"] == 1 and stats["removed"] == 0
    assert len(await _documents(client, tenant, collection_id)) == 2
