"""Suggested questions land once ingestion settles; ingest-status reports progress.

Celery is eager, providers are stubs: the upload call runs the whole chain inline —
parse → chunk → embed → store → settle-check → suggest task (stub LLM candidates,
ranked by stub-embedding cosine against the collection's chunks).
"""

MD = (
    b"# Vacation policy\n\n"
    b"Employees receive 27 vacation days per year.\n\n"
    b"## Expiry\n\nUnused vacation days expire on March 31.\n"
)

# the stub LLM's canned candidates (see app/generation/llm/stub.py)
STUB_CANDIDATES = {
    "What is the vacation policy?",
    "How many remote days are allowed?",
    "What is the travel allowance for France?",
    "When do unused vacation days expire?",
    "Who approves business trips?",
}


async def _create_collection(client, tenant):
    response = await client.post(
        "/v1/collections", json={"name": "Suggest Test"}, headers=tenant["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _upload(client, tenant, collection_id, filename="policy.md", content=MD):
    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": (filename, content, "text/markdown")},
        headers=tenant["headers"],
    )
    assert response.status_code == 202, response.text
    return response.json()


async def test_questions_generated_after_ingest(client, tenant):
    collection = await _create_collection(client, tenant)
    assert collection["suggested_questions"] is None  # nothing ingested yet

    await _upload(client, tenant, collection["id"])

    listing = await client.get("/v1/collections", headers=tenant["headers"])
    row = next(c for c in listing.json() if c["id"] == collection["id"])
    questions = row["suggested_questions"]
    assert questions is not None and len(questions) == 3
    assert {q["question"] for q in questions} <= STUB_CANDIDATES
    assert {q["min_role"] for q in questions} == {"employee"}  # nothing restricted here
    assert row["access_labels"] == []


async def test_ingest_status_reports_tokens_cost_and_questions(client, tenant):
    collection = await _create_collection(client, tenant)
    await _upload(client, tenant, collection["id"])

    response = await client.get(
        f"/v1/collections/{collection['id']}/ingest-status", headers=tenant["headers"]
    )
    assert response.status_code == 200, response.text
    status = response.json()
    assert status["ready"] == 1
    assert status["pending"] == 0 and status["processing"] == 0 and status["failed"] == 0
    assert status["embedded_tokens"] > 0
    assert status["embedding_model"] == "stub@1024"
    assert status["price_per_1m_tokens"] == 0.0
    assert status["embedding_cost_usd"] == 0.0
    assert status["eta_seconds"] is None  # nothing in flight
    assert len(status["suggested_questions"]) == 3


async def test_ingest_status_is_tenant_scoped(client, tenant, make_tenant):
    collection = await _create_collection(client, tenant)
    stranger = await make_tenant()
    response = await client.get(
        f"/v1/collections/{collection['id']}/ingest-status", headers=stranger["headers"]
    )
    assert response.status_code == 404  # foreign collection reads as not-found


async def test_delete_last_document_clears_questions(client, tenant):
    collection = await _create_collection(client, tenant)
    document = await _upload(client, tenant, collection["id"])

    listing = await client.get("/v1/collections", headers=tenant["headers"])
    row = next(c for c in listing.json() if c["id"] == collection["id"])
    assert row["suggested_questions"]  # generated

    response = await client.delete(f"/v1/documents/{document['id']}", headers=tenant["headers"])
    assert response.status_code == 204

    listing = await client.get("/v1/collections", headers=tenant["headers"])
    row = next(c for c in listing.json() if c["id"] == collection["id"])
    assert row["suggested_questions"] is None  # corpus is gone → cleared


# a single paragraph with a glued marker: its chunk is exactly this line, so the stub
# LLM's verbatim echo of the restricted excerpt embeds to the same vector (cosine 1.0)
FIN_NOTE = b"Access: Finance only. The CFO approves every card transaction above the limit.\n"


async def test_restricted_content_yields_a_locked_suggestion_and_labels(client, tenant):
    collection = await _create_collection(client, tenant)
    await _upload(client, tenant, collection["id"])
    note = await _upload(client, tenant, collection["id"], filename="FIN-note.md", content=FIN_NOTE)

    listing = await client.get("/v1/collections", headers=tenant["headers"])
    row = next(c for c in listing.json() if c["id"] == collection["id"])
    assert row["access_labels"] == ["finance"]
    questions = row["suggested_questions"]
    assert len(questions) == 3
    locked = [q for q in questions if q["min_role"] != "employee"]
    assert len(locked) == 1 and locked[0]["min_role"] == "finance"
    assert locked[0]["question"] == FIN_NOTE.decode().strip()

    status = (
        await client.get(
            f"/v1/collections/{collection['id']}/ingest-status", headers=tenant["headers"]
        )
    ).json()
    assert status["access"] == {
        "chunks_by_label": {"all": 1, "finance": 1},
        "restricted_chunks": 1,
    }
    assert status["suggested_questions"] == questions

    documents = (
        await client.get(f"/v1/collections/{collection['id']}/documents", headers=tenant["headers"])
    ).json()
    by_id = {d["id"]: d["access_labels"] for d in documents}
    assert by_id[note["id"]] == ["finance"]
    assert [labels for did, labels in by_id.items() if did != note["id"]] == [[]]

    single = (await client.get(f"/v1/documents/{note['id']}", headers=tenant["headers"])).json()
    assert single["access_labels"] == ["finance"]


async def test_suggestions_never_carry_figures(client, tenant):
    # the stub echoes the restricted excerpt; with a digit in it the anti-leak filter
    # must drop that candidate instead of exposing the value in a question
    collection = await _create_collection(client, tenant)
    await _upload(client, tenant, collection["id"])
    await _upload(
        client,
        tenant,
        collection["id"],
        filename="FIN-limit.md",
        content=b"Access: Finance only. The card limit is 1500 euro per transaction.\n",
    )
    listing = await client.get("/v1/collections", headers=tenant["headers"])
    row = next(c for c in listing.json() if c["id"] == collection["id"])
    assert row["access_labels"] == ["finance"]
    for q in row["suggested_questions"]:
        assert "1500" not in q["question"]
        assert q["min_role"] == "employee"  # the only locked candidate was dropped
