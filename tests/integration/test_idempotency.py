import pytest
from sqlalchemy import func, select

NOTE_MD = b"# Note\n\nIdempotency test content.\n"


@pytest.fixture
async def collection_id(client, tenant) -> str:
    response = await client.post(
        "/v1/collections", json={"name": "Idem"}, headers=tenant["headers"]
    )
    return response.json()["id"]


async def _document_count() -> int:
    from app.db.base import get_sessionmaker
    from app.db.models import Document

    async with get_sessionmaker()() as session:
        return (await session.execute(select(func.count(Document.id)))).scalar_one()


async def test_upload_replay_returns_same_body_once_side_effect(client, tenant, collection_id):
    headers = {**tenant["headers"], "Idempotency-Key": "upload-abc"}
    url = f"/v1/collections/{collection_id}/documents"

    first = await client.post(
        url, files={"file": ("a.md", NOTE_MD, "text/markdown")}, headers=headers
    )
    assert first.status_code == 202
    assert "x-idempotency-replay" not in first.headers

    # same key — even with a different filename the stored response replays
    second = await client.post(
        url, files={"file": ("b.md", NOTE_MD, "text/markdown")}, headers=headers
    )
    assert second.status_code == 202
    assert second.json() == first.json()
    assert second.headers["x-idempotency-replay"] == "true"
    assert await _document_count() == 1


async def test_query_replay_records_one_row(client, tenant, collection_id):
    from app.db.base import get_sessionmaker
    from app.db.models import Query

    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("p.md", b"# P\n\nEmployees receive 27 vacation days.", "text/markdown")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202

    headers = {**tenant["headers"], "Idempotency-Key": "query-1"}
    payload = {
        "collection_id": collection_id,
        "question": "How many vacation days do employees receive?",
        "stream": False,
    }
    first = await client.post("/v1/query", json=payload, headers=headers)
    second = await client.post("/v1/query", json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert second.headers["x-idempotency-replay"] == "true"

    async with get_sessionmaker()() as session:
        count = (await session.execute(select(func.count(Query.id)))).scalar_one()
    assert count == 1  # the replay did not re-run the pipeline


async def test_concurrent_key_in_flight_is_409(client, tenant, collection_id):
    from app.core.redis import get_redis

    await get_redis().set(f"idem:{tenant['id']}:busy-key", "in-flight", ex=60)
    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("x.md", NOTE_MD, "text/markdown")},
        headers={**tenant["headers"], "Idempotency-Key": "busy-key"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "request_in_flight"


async def test_failed_attempt_releases_the_key(client, tenant, collection_id):
    headers = {**tenant["headers"], "Idempotency-Key": "retry-me"}
    url = f"/v1/collections/{collection_id}/documents"

    failed = await client.post(
        url,
        files={"file": ("junk.bin", b"\x00\x01" * 200, "application/octet-stream")},
        headers=headers,
    )
    assert failed.status_code == 415

    # the key must not stay poisoned for the TTL after an error
    retried = await client.post(
        url, files={"file": ("ok.md", NOTE_MD, "text/markdown")}, headers=headers
    )
    assert retried.status_code == 202
