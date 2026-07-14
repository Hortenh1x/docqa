from datetime import UTC, datetime

from sqlalchemy import update


async def test_missing_key_is_401(client):
    response = await client.get("/v1/collections")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "invalid_api_key"
    assert "request_id" in body
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_garbage_key_is_401(client):
    response = await client.get(
        "/v1/collections", headers={"Authorization": "Bearer dqa_live_" + "0" * 32}
    )
    assert response.status_code == 401


async def test_valid_key_via_bearer_and_x_api_key(client, tenant):
    bearer = await client.get("/v1/collections", headers=tenant["headers"])
    assert bearer.status_code == 200
    assert bearer.json() == []

    x_api = await client.get("/v1/collections", headers={"X-API-Key": tenant["key"]})
    assert x_api.status_code == 200


async def test_revoked_key_is_401(client, tenant):
    from app.db.base import get_sessionmaker
    from app.db.models import ApiKey

    async with get_sessionmaker()() as session:
        await session.execute(
            update(ApiKey)
            .where(ApiKey.prefix == tenant["prefix"])
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()

    response = await client.get("/v1/collections", headers=tenant["headers"])
    assert response.status_code == 401


async def test_inactive_tenant_is_403(client, make_tenant):
    inactive = await make_tenant(active=False)
    response = await client.get("/v1/collections", headers=inactive["headers"])
    assert response.status_code == 403
    assert response.json()["code"] == "tenant_inactive"


async def test_tenant_isolation_matrix(client, make_tenant):
    """IDOR guard: a foreign tenant's resource is indistinguishable from a missing one."""
    alice, bob = await make_tenant(), await make_tenant()

    created = await client.post(
        "/v1/collections", json={"name": "Alice docs"}, headers=alice["headers"]
    )
    collection_id = created.json()["id"]
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("note.md", b"# Note\n\nSecret alice text.", "text/markdown")},
        headers=alice["headers"],
    )
    assert upload.status_code == 202
    document_id = upload.json()["id"]

    foreign_calls = [
        client.get(f"/v1/collections/{collection_id}/documents", headers=bob["headers"]),
        client.post(
            f"/v1/collections/{collection_id}/documents",
            files={"file": ("x.md", b"# X\n\nbody", "text/markdown")},
            headers=bob["headers"],
        ),
        client.get(f"/v1/documents/{document_id}", headers=bob["headers"]),
        client.delete(f"/v1/documents/{document_id}", headers=bob["headers"]),
    ]
    for call in foreign_calls:
        response = await call
        assert response.status_code == 404, response.text

    # bob sees an empty world, alice still sees her document
    assert (await client.get("/v1/collections", headers=bob["headers"])).json() == []
    mine = await client.get(f"/v1/documents/{document_id}", headers=alice["headers"])
    assert mine.status_code == 200
