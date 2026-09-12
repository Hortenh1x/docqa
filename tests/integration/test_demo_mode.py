import pytest

from app.config import get_settings

NOTE_MD = b"# Note\n\nDemo mode test content.\n"


@pytest.fixture
def demo_mode(monkeypatch, app_env):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_MAX_FILES_PER_COLLECTION", "2")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_read_only_collection_rejects_uploads(client, tenant):
    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    created = await client.post(
        "/v1/collections", json={"name": "Demo docs"}, headers=tenant["headers"]
    )
    collection_id = created.json()["id"]

    async with get_sessionmaker()() as session:
        collection = await session.get(Collection, created.json()["id"])
        collection.read_only = True
        await session.commit()

    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("x.md", NOTE_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    assert response.status_code == 403
    assert response.json()["code"] == "demo_readonly"

    listed = await client.get("/v1/collections", headers=tenant["headers"])
    assert listed.json()[0]["read_only"] is True


async def test_demo_mode_caps_files_per_collection(client, tenant, demo_mode):
    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    # Demo provisioning belongs to the operator; public collection creation is denied.
    async with get_sessionmaker()() as session:
        sandbox = Collection(
            tenant_id=tenant["id"],
            name="Sandbox",
            slug="sandbox",
            embedding_model=get_settings().embedding_model_id,
        )
        session.add(sandbox)
        await session.commit()
        url = f"/v1/collections/{sandbox.id}/documents"

    for i in range(2):
        ok = await client.post(
            url,
            files={"file": (f"f{i}.md", NOTE_MD + str(i).encode(), "text/markdown")},
            headers=tenant["headers"],
        )
        assert ok.status_code == 202

    blocked = await client.post(
        url,
        files={"file": ("f9.md", NOTE_MD + b"9", "text/markdown")},
        headers=tenant["headers"],
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "demo_quota_exceeded"
