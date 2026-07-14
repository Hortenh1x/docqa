"""Query pipeline end-to-end on the all-stub stack: no network, deterministic scores."""

import json

import pytest
from sqlalchemy import select

POLICY_MD = b"""# Vacation Policy

Employees receive 27 vacation days per year.

## Carryover

Unused vacation days expire on March 31. Exceptions require HR approval.
"""


@pytest.fixture(autouse=True)
def _reset_stub_llm_counter():
    from app.generation.llm.stub import StubLLM

    StubLLM.calls = 0
    yield


@pytest.fixture
async def ready_collection(client, tenant) -> str:
    created = await client.post(
        "/v1/collections", json={"name": "Policies"}, headers=tenant["headers"]
    )
    collection_id = created.json()["id"]
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("policy.md", POLICY_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202  # celery eager: ready right away
    return collection_id


async def _query_rows():
    from app.db.base import get_sessionmaker
    from app.db.models import Query, QueryCitation

    async with get_sessionmaker()() as session:
        queries = list((await session.execute(select(Query))).scalars().all())
        citations = list((await session.execute(select(QueryCitation))).scalars().all())
        return queries, citations


async def read_sse(client, payload, headers):
    events = []
    async with client.stream("POST", "/v1/query", json=payload, headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        assert lines[0].startswith("event: ") and lines[1].startswith("data: ")
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    return events


async def test_json_happy_path_with_citations_and_recording(client, tenant, ready_collection):
    from app.generation.llm.stub import StubLLM

    response = await client.post(
        "/v1/query",
        json={
            "collection_id": ready_collection,
            "question": "How many vacation days do employees get?",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["refused"] is False
    assert "[1]" in body["answer"]
    assert body["query_id"]
    assert body["confidence"] >= 0.35
    assert body["model"] == "stub"
    assert body["usage"] == {"prompt_tokens": 100, "completion_tokens": 18, "cost_usd": 0.0}
    assert body["sources"], "sources must accompany a non-refused answer"
    assert body["sources"][0]["filename"] == "policy.md"
    assert body["sources"][0]["snippet"]
    assert StubLLM.calls == 1

    queries, citations = await _query_rows()
    assert len(queries) == 1
    row = queries[0]
    assert str(row.id) == body["query_id"]
    assert row.refused is False
    assert row.answer == body["answer"]
    assert row.prompt_tokens == 100
    assert float(row.cost_usd) == 0.0
    assert row.latency_ms is not None
    assert len(citations) == len(body["sources"])
    assert {c.rank for c in citations} == {s["n"] for s in body["sources"]}


async def test_off_corpus_question_refused_without_llm_call(client, tenant, ready_collection):
    from app.generation.llm.stub import StubLLM

    response = await client.post(
        "/v1/query",
        json={
            "collection_id": ready_collection,
            "question": "What is the company sabbatical policy?",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    body = response.json()

    assert body["refused"] is True
    assert body["reason"] == "not_in_documents"
    assert body["answer"] is None
    assert body["usage"]["prompt_tokens"] is None
    assert body["usage"]["cost_usd"] is None
    assert StubLLM.calls == 0, "the refusal gate must not spend an LLM call"

    queries, citations = await _query_rows()
    assert len(queries) == 1 and queries[0].refused is True
    assert citations == []  # nothing reached the context


async def test_sse_event_order_and_invalid_citation_cleanup(client, tenant, ready_collection):
    events = await read_sse(
        client,
        {
            "collection_id": ready_collection,
            # 'badcite' switches the stub LLM to the answer citing a non-existent [9]
            "question": "badcite: how many vacation days do employees receive per year?",
            "stream": True,
        },
        tenant["headers"],
    )
    names = [name for name, _ in events]

    assert names[0] == "meta" and events[0][1]["query_id"]
    assert names[1] == "sources" and events[1][1]["sources"]
    assert names[-1] == "done"
    delta_text = "".join(data["text"] for name, data in events if name == "delta")
    assert delta_text, "at least one delta expected"
    assert "[9]" in delta_text  # raw stream carries the model's mistake...

    done = events[-1][1]
    assert done["refused"] is False
    assert "[9]" not in done["answer"]  # ...the final answer does not
    assert "[1]" in done["answer"]
    assert done["usage"]["prompt_tokens"] == 120


async def test_sse_refusal_is_meta_then_done(client, tenant, ready_collection):
    events = await read_sse(
        client,
        {
            "collection_id": ready_collection,
            "question": "Do we offer pet insurance to anyone?",
            "stream": True,
        },
        tenant["headers"],
    )
    assert [name for name, _ in events] == ["meta", "done"]
    assert events[1][1]["refused"] is True


async def test_query_foreign_collection_is_404(client, make_tenant, ready_collection):
    stranger = await make_tenant()
    response = await client.post(
        "/v1/query",
        json={"collection_id": ready_collection, "question": "anything", "stream": False},
        headers=stranger["headers"],
    )
    assert response.status_code == 404
