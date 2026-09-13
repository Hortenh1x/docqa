"""Document passages (the reader's highlight surface) and conversation history."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from tests.integration.test_accounts import account_client, capture_mail, csrf, register_login

__all__ = ["account_client", "capture_mail"]

HANDBOOK_MD = b"""# Handbook

## Leave

Employees receive 27 vacation days per year. Unused days expire on March 31.

## Remote work

Remote work is allowed two days a week. Equipment is provided by the company.

## Salary bands

Access: leadership only

Band A pays 100k. Band B pays 80k.
"""


@pytest.fixture
async def handbook(client, tenant) -> tuple[str, str]:
    created = await client.post(
        "/v1/collections", json={"name": "Handbook"}, headers=tenant["headers"]
    )
    collection_id = created.json()["id"]
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("handbook.md", HANDBOOK_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202, upload.text
    return collection_id, upload.json()["id"]


# --- passages ---


async def test_passages_follow_the_role_in_the_where_clause(client, tenant, handbook):
    _, document_id = handbook
    employee = await client.get(f"/v1/documents/{document_id}/passages", headers=tenant["headers"])
    assert employee.status_code == 200, employee.text
    page = employee.json()
    assert page["total"] == len(page["passages"]) == int(employee.headers["x-total-count"])
    assert all(p["access_label"] == "all" for p in page["passages"])
    assert not any("Band A" in p["content"] for p in page["passages"])
    assert [p["chunk_index"] for p in page["passages"]] == sorted(
        p["chunk_index"] for p in page["passages"]
    )

    leadership = await client.get(
        f"/v1/documents/{document_id}/passages",
        params={"role": "leadership"},
        headers=tenant["headers"],
    )
    full = leadership.json()
    assert full["total"] == page["total"] + 1
    restricted = next(p for p in full["passages"] if p["access_label"] == "leadership")
    assert "Band A pays 100k" in restricted["content"]
    assert restricted["section"] and "Salary bands" in restricted["section"]
    assert restricted["pages"] is None  # markdown has no pages


async def test_passages_page_around_a_chunk(client, tenant, handbook):
    _, document_id = handbook
    full = (
        await client.get(
            f"/v1/documents/{document_id}/passages",
            params={"role": "leadership"},
            headers=tenant["headers"],
        )
    ).json()
    target = full["passages"][-1]["chunk_index"]
    page = (
        await client.get(
            f"/v1/documents/{document_id}/passages",
            params={"role": "leadership", "around": target, "limit": 1},
            headers=tenant["headers"],
        )
    ).json()
    assert [p["chunk_index"] for p in page["passages"]] == [target]
    assert page["offset"] == full["total"] - 1
    # an unknown role is rejected, a foreign document is invisible
    assert (
        await client.get(
            f"/v1/documents/{document_id}/passages",
            params={"role": "ceo"},
            headers=tenant["headers"],
        )
    ).status_code == 422


async def test_passages_foreign_document_is_404(client, make_tenant, handbook):
    _, document_id = handbook
    stranger = await make_tenant()
    response = await client.get(
        f"/v1/documents/{document_id}/passages", headers=stranger["headers"]
    )
    assert response.status_code == 404


# --- history ---


async def ask(client, headers, collection_id, question):
    response = await client.post(
        "/v1/query",
        json={"collection_id": collection_id, "question": question, "stream": False},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_api_key_history_lists_the_tenant_log_with_quotes(client, tenant, handbook):
    collection_id, document_id = handbook
    first = await ask(client, tenant["headers"], collection_id, "How many vacation days?")
    refused = await ask(client, tenant["headers"], collection_id, "Any sabbatical policy?")
    assert refused["refused"] is True

    page = await client.get(f"/v1/collections/{collection_id}/queries", headers=tenant["headers"])
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["has_more"] is False
    assert [q["id"] for q in body["queries"]] == [refused["query_id"], first["query_id"]]
    newest, oldest = body["queries"]
    assert newest["refused"] is True and newest["answer"] is None
    assert newest["reason"] == "not_in_documents" and newest["sources"] == []
    assert oldest["answer"] == first["answer"] and oldest["role"] == "employee"
    assert oldest["usage"]["prompt_tokens"] == 100 and oldest["created_at"]
    cited = [s for s in oldest["sources"] if s["quotes"] is not None]
    assert [s["n"] for s in cited] == [1]
    assert cited[0]["document_id"] == document_id and cited[0]["content"]
    [quote] = cited[0]["quotes"]
    assert quote["text"] == "Employees receive 27 vacation days per year"
    assert cited[0]["content"][quote["start"] : quote["end"]] == quote["text"]
    assert all(s["content"] is None for s in oldest["sources"] if s["quotes"] is None)

    # keyset paging: `before` walks backwards, an unknown anchor yields an empty page
    older = await client.get(
        f"/v1/collections/{collection_id}/queries",
        params={"limit": 1, "before": refused["query_id"]},
        headers=tenant["headers"],
    )
    assert [q["id"] for q in older.json()["queries"]] == [first["query_id"]]
    limited = await client.get(
        f"/v1/collections/{collection_id}/queries", params={"limit": 1}, headers=tenant["headers"]
    )
    assert limited.json()["has_more"] is True
    assert (
        await client.get(
            f"/v1/collections/{collection_id}/queries",
            params={"before": document_id},
            headers=tenant["headers"],
        )
    ).json() == {"queries": [], "has_more": False}


async def test_rows_recorded_before_pinpoint_quotes_get_a_fallback_span(client, tenant, handbook):
    from app.db.base import get_sessionmaker
    from app.db.models import QueryCitation

    collection_id, _ = handbook
    answered = await ask(client, tenant["headers"], collection_id, "How many vacation days?")
    async with get_sessionmaker()() as db:
        await db.execute(update(QueryCitation).values(quotes=None))
        await db.commit()
    page = (
        await client.get(f"/v1/collections/{collection_id}/queries", headers=tenant["headers"])
    ).json()
    [item] = page["queries"]
    assert item["id"] == answered["query_id"]
    cited = next(s for s in item["sources"] if s["n"] == 1)
    assert cited["quotes"] and "27 vacation days" in cited["quotes"][0]["text"]


async def test_accounts_see_only_their_own_history_and_guests_none(
    account_client, capture_mail, make_tenant, monkeypatch
):
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    client, application = account_client
    public_tenant = await make_tenant()
    monkeypatch.setenv("SUGGESTED_QUESTIONS_ENABLED", "false")
    get_settings.cache_clear()
    # seed while the collection is still the service tenant's private, writable one —
    # once published (and the tenant is the public one) its key counts as a guest
    async with get_sessionmaker()() as db:
        published = Collection(
            tenant_id=public_tenant["id"],
            name="Public",
            slug="public",
            embedding_model=get_settings().embedding_model_id,
        )
        db.add(published)
        await db.commit()
        public_id = str(published.id)
    upload = await client.post(
        f"/v1/collections/{public_id}/documents",
        files={"file": ("handbook.md", HANDBOOK_MD, "text/markdown")},
        headers=public_tenant["headers"],
    )
    assert upload.status_code == 202, upload.text
    async with get_sessionmaker()() as db:
        await db.execute(
            update(Collection)
            .where(Collection.id == published.id)
            .values(is_public=True, read_only=True)
        )
        await db.commit()
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(public_tenant["id"]))
    get_settings.cache_clear()

    # a guest asks; the guest's history is client-side, so the API returns an empty page
    guest_headers = await csrf(client)
    guest_answer = await ask(client, guest_headers, public_id, "How many vacation days?")
    guest_page = await client.get(f"/v1/collections/{public_id}/queries", headers=guest_headers)
    assert guest_page.status_code == 200 and guest_page.json() == {
        "queries": [],
        "has_more": False,
    }
    # …and a guest cannot claim anything
    denied = await client.post(
        "/v1/queries/claim", headers=guest_headers, json={"query_ids": [guest_answer["query_id"]]}
    )
    assert denied.status_code == 401

    # Alice signs in and claims the guest exchange: it appears in her thread
    alice, alice_headers = await register_login(client, capture_mail)
    claimed = await client.post(
        "/v1/queries/claim",
        headers=alice_headers,
        json={"query_ids": [guest_answer["query_id"], public_id]},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json() == {"claimed": 1}
    own = await ask(client, alice_headers, public_id, "What about remote work?")
    alice_page = (await client.get(f"/v1/collections/{public_id}/queries")).json()
    assert [q["id"] for q in alice_page["queries"]] == [own["query_id"], guest_answer["query_id"]]
    assert alice_page["queries"][1]["question"] == "How many vacation days?"
    # a second claim of the same rows moves nothing
    again = await client.post(
        "/v1/queries/claim", headers=alice_headers, json={"query_ids": [guest_answer["query_id"]]}
    )
    assert again.json() == {"claimed": 0}

    # Bob sees none of it, and cannot take Alice's rows either
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as other:
        _, bob_headers = await register_login(other, capture_mail, email="bob@example.com")
        bob_page = (await other.get(f"/v1/collections/{public_id}/queries")).json()
        assert bob_page == {"queries": [], "has_more": False}
        stolen = await other.post(
            "/v1/queries/claim",
            headers=bob_headers,
            json={"query_ids": [guest_answer["query_id"], own["query_id"]]},
        )
        assert stolen.json() == {"claimed": 0}

    from app.db.models import Query

    async with get_sessionmaker()() as db:
        owners = dict((await db.execute(select(Query.id, Query.user_id))).all())
    assert {str(k): str(v) for k, v in owners.items()} == {
        guest_answer["query_id"]: alice["user"]["id"],
        own["query_id"]: alice["user"]["id"],
    }
