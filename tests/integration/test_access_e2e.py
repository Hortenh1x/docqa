"""Access levels end to end on the all-stub stack.

The stub embedding maps identical texts to identical vectors (cosine 1.0) and unrelated
texts to ~0, and the stub reranker scores word overlap — so questions below either quote
a chunk verbatim (vector path) or share its words (gate). The document has one open
section and one section labelled for Finance; they must never share a chunk.
"""

import json

import pytest
from sqlalchemy import select

from app.config import get_settings

FIN_MD = b"""# Expense Rates

## Per-diems

The Germany per-diem is 28 euro per day for business travel.

## Card limits

Access: Finance only

The single-transaction card limit is 1500 euro; above it the CFO approves.
"""

OPEN_CHUNK = (
    "Expense Rates\n\nPer-diems\n\nThe Germany per-diem is 28 euro per day for business travel."
)
RESTRICTED_CHUNK = (
    "Card limits\n\nAccess: Finance only\n\n"
    "The single-transaction card limit is 1500 euro; above it the CFO approves."
)
OPEN_QUESTION = "What is the Germany per-diem per day for business travel?"


@pytest.fixture
async def fin_collection(client, tenant) -> str:
    created = await client.post(
        "/v1/collections", json={"name": "Finance"}, headers=tenant["headers"]
    )
    collection_id = created.json()["id"]
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("FIN-001.md", FIN_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202
    return collection_id


@pytest.fixture
def reveal_mode(monkeypatch, app_env):
    monkeypatch.setenv("ACCESS_REVEAL_HIDDEN", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _ask(client, tenant, collection_id, question, role=None, **extra):
    payload = {"collection_id": collection_id, "question": question, "stream": False}
    if role is not None:
        payload["role"] = role
    response = await client.post("/v1/query", json=payload, headers={**tenant["headers"], **extra})
    return response


# --- filtering ---


async def test_restricted_chunk_is_stored_with_its_label(fin_collection):
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk

    async with get_sessionmaker()() as session:
        rows = (await session.execute(select(Chunk.access_label, Chunk.content))).all()
    labels = {content: label for label, content in rows}
    assert labels[OPEN_CHUNK] == "all"
    assert labels[RESTRICTED_CHUNK] == "finance"
    assert len(rows) == 2  # different labels never share a chunk


async def test_default_role_never_sees_the_restricted_passage(client, tenant, fin_collection):
    # exact text of the restricted chunk: the vector path would rank it first (cosine 1.0)
    response = await _ask(client, tenant, fin_collection, RESTRICTED_CHUNK)
    assert response.status_code == 200
    body = response.json()
    assert body["access"] == {"role": "employee", "hidden_passages": None, "hidden_labels": None}
    assert all(s["access_label"] == "all" for s in body["sources"])
    assert not any("1500" in s["snippet"] for s in body["sources"])
    assert "1500" not in (body["answer"] or "")


async def test_finance_role_sees_the_restricted_passage(client, tenant, fin_collection):
    response = await _ask(client, tenant, fin_collection, RESTRICTED_CHUNK, role="finance")
    assert response.status_code == 200
    body = response.json()
    assert body["access"]["role"] == "finance"
    assert body["sources"][0]["access_label"] == "finance"
    assert "1500" in body["sources"][0]["snippet"]


async def test_hr_role_does_not_see_finance_content(client, tenant, fin_collection):
    body = (await _ask(client, tenant, fin_collection, RESTRICTED_CHUNK, role="hr")).json()
    assert all(s["access_label"] == "all" for s in body["sources"])


async def test_search_functions_filter_in_sql(fin_collection):
    """Both retrieval paths and the hidden probe apply the label predicate themselves."""
    from app.db.base import get_sessionmaker
    from app.embeddings import get_embedding_provider
    from app.retrieval.fulltext import fulltext_search
    from app.retrieval.vector import hidden_probe, vector_search

    settings = get_settings()
    [embedding] = await get_embedding_provider(settings).embed([RESTRICTED_CHUNK])
    import uuid

    cid = uuid.UUID(fin_collection)
    async with get_sessionmaker()() as db:
        open_only = await vector_search(db, cid, embedding, 10, 100, ["all"])
        assert [c.access_label for c in open_only] == ["all"]

        with_finance = await vector_search(db, cid, embedding, 10, 100, ["all", "finance"])
        assert with_finance[0].access_label == "finance"
        assert with_finance[0].score > 0.99

        fts_open = await fulltext_search(db, cid, "1500 euro CFO", 10, ["all"])
        assert fts_open == []
        fts_fin = await fulltext_search(db, cid, "1500 euro CFO", 10, ["all", "finance"])
        assert [c.access_label for c in fts_fin] == ["finance"]

        hidden = await hidden_probe(db, cid, embedding, ["all"], 8, 0.5)
        assert hidden.passages == 1 and hidden.labels == ("finance",)
        nothing_hidden = await hidden_probe(db, cid, embedding, ["all", "finance"], 8, 0.5)
        assert nothing_hidden.passages == 0 and nothing_hidden.labels == ()


# --- reveal mode ---


async def test_reveal_mode_reports_what_the_role_cannot_see(
    client, tenant, fin_collection, reveal_mode
):
    employee = (await _ask(client, tenant, fin_collection, RESTRICTED_CHUNK)).json()
    assert employee["access"] == {
        "role": "employee",
        "hidden_passages": 1,
        "hidden_labels": ["finance"],
    }
    # the hint never carries content
    assert "1500" not in json.dumps(employee)

    finance = (await _ask(client, tenant, fin_collection, RESTRICTED_CHUNK, role="finance")).json()
    assert finance["access"] == {"role": "finance", "hidden_passages": 0, "hidden_labels": []}

    # a full-access role reports zero without probing
    leadership = (
        await _ask(client, tenant, fin_collection, RESTRICTED_CHUNK, role="leadership")
    ).json()
    assert leadership["access"] == {
        "role": "leadership",
        "hidden_passages": 0,
        "hidden_labels": [],
    }


async def test_sse_meta_carries_access(client, tenant, fin_collection, reveal_mode):
    payload = {"collection_id": fin_collection, "question": RESTRICTED_CHUNK, "stream": True}
    async with client.stream(
        "POST", "/v1/query", json=payload, headers=tenant["headers"]
    ) as response:
        assert response.status_code == 200
        body = "".join([chunk async for chunk in response.aiter_text()])
    frames = [f.splitlines() for f in body.strip().split("\n\n")]
    assert frames[0][0] == "event: meta"
    meta = json.loads(frames[0][1][6:])
    assert meta["access"] == {
        "role": "employee",
        "hidden_passages": 1,
        "hidden_labels": ["finance"],
    }


# --- contract ---


async def test_unknown_role_is_422_before_any_work(client, tenant, fin_collection):
    response = await _ask(client, tenant, fin_collection, OPEN_QUESTION, role="intern")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_role"
    assert body["role"] == "intern"
    assert "request_id" in body


async def test_roles_endpoint_lists_roles_in_privilege_order(client, tenant):
    response = await client.get("/v1/roles", headers=tenant["headers"])
    assert response.status_code == 200
    roles = response.json()
    assert [r["role"] for r in roles] == ["employee", "manager", "hr", "finance", "leadership"]
    assert [r["default"] for r in roles] == [True, False, False, False, False]
    assert roles[-1]["labels"] == ["all", "managers", "hr", "finance", "leadership"]
    assert all(r["description"] for r in roles)


async def test_roles_endpoint_requires_a_key(client):
    assert (await client.get("/v1/roles")).status_code == 401


async def test_role_is_recorded_on_the_query_row(client, tenant, fin_collection):
    from app.db.base import get_sessionmaker
    from app.db.models import Query

    await _ask(client, tenant, fin_collection, OPEN_QUESTION, role="manager")
    async with get_sessionmaker()() as session:
        roles = (await session.execute(select(Query.role))).scalars().all()
    assert roles == ["manager"]


async def test_foreign_collection_with_a_role_is_still_404(client, make_tenant, fin_collection):
    other = await make_tenant()
    response = await _ask(client, other, fin_collection, OPEN_QUESTION, role="leadership")
    assert response.status_code == 404


# --- idempotency ---


async def test_idempotency_key_is_bound_to_the_role(client, tenant, fin_collection):
    key = {"Idempotency-Key": "access-key-1"}
    first = await _ask(client, tenant, fin_collection, OPEN_QUESTION, role="employee", **key)
    assert first.status_code == 200
    assert "x-idempotency-replay" not in first.headers

    replay = await _ask(client, tenant, fin_collection, OPEN_QUESTION, role="employee", **key)
    assert replay.status_code == 200
    assert replay.headers["x-idempotency-replay"] == "true"
    assert replay.json() == first.json()

    # same key, another role: the stored (employee) answer must not be handed out
    reused = await _ask(client, tenant, fin_collection, OPEN_QUESTION, role="finance", **key)
    assert reused.status_code == 422
    assert reused.json()["code"] == "idempotency_key_reused"

    # same key, another question: rejected as well
    other_q = await _ask(client, tenant, fin_collection, "Something else?", role="employee", **key)
    assert other_q.status_code == 422


# --- the original file follows the same labels ---


async def test_file_download_respects_the_role(client, tenant, fin_collection):
    documents = (
        await client.get(f"/v1/collections/{fin_collection}/documents", headers=tenant["headers"])
    ).json()
    doc = next(d for d in documents if d["filename"] == "FIN-001.md")
    assert doc["access_labels"] == ["finance"]

    # default role (employee): the file holds a Finance-only section → refused as a whole
    refused = await client.get(f"/v1/documents/{doc['id']}/file", headers=tenant["headers"])
    assert refused.status_code == 403
    body = refused.json()
    assert body["code"] == "document_restricted"
    assert body["labels"] == ["finance"] and body["role"] == "employee"

    hr = await client.get(
        f"/v1/documents/{doc['id']}/file", params={"role": "hr"}, headers=tenant["headers"]
    )
    assert hr.status_code == 403

    finance = await client.get(
        f"/v1/documents/{doc['id']}/file", params={"role": "finance"}, headers=tenant["headers"]
    )
    assert finance.status_code == 200
    assert b"1500" in finance.content

    unknown = await client.get(
        f"/v1/documents/{doc['id']}/file", params={"role": "intern"}, headers=tenant["headers"]
    )
    assert unknown.status_code == 422
