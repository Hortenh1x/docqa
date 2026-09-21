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


async def test_query_replay_records_one_row(client, tenant, collection_id, monkeypatch):
    from app.db.base import get_sessionmaker
    from app.db.models import Query
    from app.embeddings.stub import StubEmbeddings
    from app.generation.llm.stub import StubLLM

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
    embed = StubEmbeddings.embed
    embedding_calls = 0

    async def counted_embed(self, texts):
        nonlocal embedding_calls
        embedding_calls += 1
        return await embed(self, texts)

    monkeypatch.setattr(StubEmbeddings, "embed", counted_embed)
    calls_before = StubLLM.calls
    first = await client.post("/v1/query", json=payload, headers=headers)
    calls_after_first = StubLLM.calls
    embedding_calls_after_first = embedding_calls
    second = await client.post("/v1/query", json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert second.headers["x-idempotency-replay"] == "true"
    assert calls_after_first - calls_before == 2  # planner and answer
    assert StubLLM.calls == calls_after_first  # replay calls no provider
    assert embedding_calls_after_first == 1
    assert embedding_calls == embedding_calls_after_first

    async with get_sessionmaker()() as session:
        count = (await session.execute(select(func.count(Query.id)))).scalar_one()
    assert count == 1  # the replay did not re-run the pipeline


async def test_query_replay_adds_no_provider_billing_operations(
    client, tenant, collection_id, monkeypatch
):
    import json

    import httpx

    from app.generation import service
    from app.generation.llm import openai_compat
    from app.generation.llm.openai_compat import OpenAICompatLLM
    from app.retrieval.planning import PLANNER_SYSTEM_PROMPT

    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("p.md", b"# P\n\nEmployees receive 27 vacation days.", "text/markdown")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202

    transport_calls = []
    admissions = []
    settlements = []

    def handler(request):
        transport_calls.append(request)
        system = json.loads(request.content)["messages"][0]["content"]
        content = '{"queries":[]}' if system == PLANNER_SYSTEM_PROMPT else "Supported [1]."
        delta = json.dumps({"choices": [{"delta": {"content": content}}]})
        usage = json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 2}})
        return httpx.Response(
            200,
            text=f"data: {delta}\n\ndata: {usage}\n\ndata: [DONE]\n\n",
        )

    async def counted_before(*args, **kwargs):
        admissions.append((args, kwargs))
        return None

    async def counted_after(*args, **kwargs):
        settlements.append((args, kwargs))

    llm = OpenAICompatLLM(
        "https://api.deepseek.com",
        "fixture",
        "deepseek-flash",
        0,
        100,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(openai_compat, "before_call", counted_before)
    monkeypatch.setattr(openai_compat, "after_call", counted_after)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: llm)

    headers = {**tenant["headers"], "Idempotency-Key": "query-billing-1"}
    payload = {
        "collection_id": collection_id,
        "question": "How many vacation days do employees receive?",
        "stream": False,
    }
    first = await client.post("/v1/query", json=payload, headers=headers)
    second = await client.post("/v1/query", json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert second.headers["x-idempotency-replay"] == "true"
    assert len(transport_calls) == len(admissions) == len(settlements) == 2


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
