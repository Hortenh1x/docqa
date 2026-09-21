"""Conversation lifecycle and actor-scoped ownership against real PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from tests.integration.test_accounts import (
    PASSWORD,
    account_client,
    capture_mail,
    csrf,
    register_login,
)

__all__ = ["account_client", "capture_mail"]


async def _second_key(tenant_id: uuid.UUID) -> dict[str, str]:
    from app.core.security import generate_api_key
    from app.db.base import get_sessionmaker
    from app.db.models import ApiKey

    plaintext, prefix, key_hash = generate_api_key()
    async with get_sessionmaker()() as db:
        db.add(ApiKey(tenant_id=tenant_id, prefix=prefix, key_hash=key_hash))
        await db.commit()
    return {"Authorization": f"Bearer {plaintext}"}


async def _private_collection(client, tenant) -> str:
    response = await client.post(
        "/v1/collections", json={"name": "Private"}, headers=tenant["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _public_collection(make_tenant, monkeypatch) -> tuple[dict, str]:
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    tenant = await make_tenant()
    async with get_sessionmaker()() as db:
        collection = Collection(
            tenant_id=tenant["id"],
            name="Public",
            slug=f"public-{uuid.uuid4().hex[:6]}",
            embedding_model=get_settings().embedding_model_id,
            read_only=True,
            is_public=True,
        )
        db.add(collection)
        await db.commit()
        collection_id = str(collection.id)
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(tenant["id"]))
    get_settings.cache_clear()
    return tenant, collection_id


async def test_private_api_keys_share_tenant_conversations_and_hide_foreign_ids(
    client, tenant, make_tenant
):
    collection_id = await _private_collection(client, tenant)
    peer_headers = await _second_key(tenant["id"])
    created = await client.post(
        f"/v1/collections/{collection_id}/conversations",
        json={"title": "  First chat  "},
        headers=tenant["headers"],
    )
    assert created.status_code == 201, created.text
    conversation = created.json()
    assert conversation["title"] == "First chat"
    assert conversation["archived"] is False and conversation["legacy"] is False
    assert conversation["preview"] is None

    peer = await client.get(f"/v1/collections/{collection_id}/conversations", headers=peer_headers)
    assert [row["id"] for row in peer.json()["conversations"]] == [conversation["id"]]

    stranger = await make_tenant()
    hidden = await client.patch(
        f"/v1/conversations/{conversation['id']}",
        json={"title": "stolen"},
        headers=stranger["headers"],
    )
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "not_found"


async def test_conversation_lifecycle_archive_pagination_and_transcript(client, tenant):
    from app.db.base import get_sessionmaker
    from app.db.models import Conversation, Query

    collection_id = await _private_collection(client, tenant)
    created = []
    for title in ("One", "Two", "Three"):
        response = await client.post(
            f"/v1/collections/{collection_id}/conversations",
            json={"title": title},
            headers=tenant["headers"],
        )
        assert response.status_code == 201, response.text
        created.append(response.json())

    first_page = await client.get(
        f"/v1/collections/{collection_id}/conversations?limit=2", headers=tenant["headers"]
    )
    assert first_page.status_code == 200, first_page.text
    page = first_page.json()
    assert len(page["conversations"]) == 2 and page["has_more"] is True
    assert page["next_cursor"]
    second_page = await client.get(
        f"/v1/collections/{collection_id}/conversations",
        params={"limit": 2, "before": page["next_cursor"]},
        headers=tenant["headers"],
    )
    ids = [row["id"] for row in page["conversations"] + second_page.json()["conversations"]]
    assert len(ids) == len(set(ids)) == 3

    target = created[0]
    renamed = await client.patch(
        f"/v1/conversations/{target['id']}",
        json={"title": "Renamed", "archived": True},
        headers=tenant["headers"],
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Renamed" and renamed.json()["archived"] is True
    unchanged = await client.patch(
        f"/v1/conversations/{target['id']}",
        json={"title": "Renamed", "archived": True},
        headers=tenant["headers"],
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["updated_at"] == renamed.json()["updated_at"]
    archived = await client.get(
        f"/v1/collections/{collection_id}/conversations?archived=true",
        headers=tenant["headers"],
    )
    assert [row["id"] for row in archived.json()["conversations"]] == [target["id"]]
    active = await client.get(
        f"/v1/collections/{collection_id}/conversations?archived=false",
        headers=tenant["headers"],
    )
    assert target["id"] not in [row["id"] for row in active.json()["conversations"]]

    async with get_sessionmaker()() as db:
        conversation = await db.get(Conversation, uuid.UUID(target["id"]))
        query = Query(
            tenant_id=tenant["id"],
            collection_id=uuid.UUID(collection_id),
            conversation_id=conversation.id,
            question="Historical question",
            answer="Historical answer",
            refused=False,
            outcome="answered",
            outcome_reason=None,
            context_reset=True,
        )
        db.add(query)
        await db.commit()
        query_id = str(query.id)

    transcript = await client.get(
        f"/v1/conversations/{target['id']}/queries", headers=tenant["headers"]
    )
    assert transcript.status_code == 200, transcript.text
    [item] = transcript.json()["queries"]
    assert item["id"] == query_id and item["conversation_id"] == target["id"]
    assert item["outcome"] == "answered" and item["context_reset"] is True
    assert item["answer"] == "Historical answer"

    restored = await client.patch(
        f"/v1/conversations/{target['id']}",
        json={"archived": False},
        headers=tenant["headers"],
    )
    assert restored.status_code == 200 and restored.json()["archived"] is False


async def test_legacy_conversation_is_read_only_but_keeps_historical_answer(client, tenant):
    from app.db.base import get_sessionmaker
    from app.db.models import ApiKey, Conversation, Query

    collection_id = await _private_collection(client, tenant)
    async with get_sessionmaker()() as db:
        conversation = Conversation(
            tenant_id=tenant["id"],
            collection_id=uuid.UUID(collection_id),
            title="Previous questions",
            kind="legacy",
            created_by_api_key_id=await db.scalar(
                select(ApiKey.id).where(ApiKey.tenant_id == tenant["id"])
            ),
            archived_at=datetime.now(UTC),
        )
        db.add(conversation)
        await db.flush()
        db.add(
            Query(
                tenant_id=tenant["id"],
                collection_id=uuid.UUID(collection_id),
                conversation_id=conversation.id,
                question="Old",
                answer="Still readable",
                refused=False,
            )
        )
        await db.commit()
        conversation_id = str(conversation.id)

    rejected = await client.patch(
        f"/v1/conversations/{conversation_id}",
        json={"archived": False},
        headers=tenant["headers"],
    )
    assert rejected.status_code == 409
    unchanged = await client.patch(
        f"/v1/conversations/{conversation_id}",
        json={"archived": True},
        headers=tenant["headers"],
    )
    assert unchanged.status_code == 200 and unchanged.json()["archived"] is True
    history = await client.get(
        f"/v1/conversations/{conversation_id}/queries", headers=tenant["headers"]
    )
    [item] = history.json()["queries"]
    assert item["outcome"] == "legacy_unknown" and item["answer"] == "Still readable"


async def test_guest_conversations_are_cookie_scoped_even_on_same_ip_and_claim_on_login(
    account_client, capture_mail, make_tenant, monkeypatch
):
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import Conversation, Query

    first, application = account_client
    public_tenant, collection_id = await _public_collection(make_tenant, monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as second:
        first_headers = await csrf(first)
        await csrf(second)
        made = await first.post(
            f"/v1/collections/{collection_id}/conversations",
            json={"title": "Guest chat"},
            headers=first_headers,
        )
        assert made.status_code == 201, made.text
        conversation_id = made.json()["id"]
        other = await second.get(f"/v1/collections/{collection_id}/conversations")
        assert other.status_code == 200 and other.json()["conversations"] == []

        async with get_sessionmaker()() as db:
            conversation = await db.get(Conversation, uuid.UUID(conversation_id))
            assert conversation.tenant_id == public_tenant["id"]
            assert conversation.owner_guest_session_id is not None
            db.add(
                Query(
                    tenant_id=public_tenant["id"],
                    collection_id=uuid.UUID(collection_id),
                    conversation_id=conversation.id,
                    question="Guest question",
                    answer="Guest answer",
                    refused=False,
                    outcome="answered",
                )
            )
            await db.commit()

        account, _ = await register_login(first, capture_mail)
        owned = await first.get(f"/v1/collections/{collection_id}/conversations")
        assert [row["id"] for row in owned.json()["conversations"]] == [conversation_id]
        async with get_sessionmaker()() as db:
            conversation = await db.get(Conversation, uuid.UUID(conversation_id))
            assert str(conversation.owner_user_id) == account["user"]["id"]
            assert conversation.owner_guest_session_id is None
            query_owner = await db.scalar(
                select(Query.user_id).where(Query.conversation_id == conversation.id)
            )
            assert query_owner == conversation.owner_user_id
    get_settings.cache_clear()


async def test_public_demo_key_cannot_use_conversations_without_guest_session(
    account_client, make_tenant, monkeypatch
):
    client, _ = account_client
    public_tenant, collection_id = await _public_collection(make_tenant, monkeypatch)
    response = await client.post(
        f"/v1/collections/{collection_id}/conversations",
        json={"title": "Shared by accident"},
        headers=public_tenant["headers"],
    )
    assert response.status_code == 401
    assert response.json()["code"] == "guest_session_required"


async def test_login_rotation_cannot_race_an_orphan_guest_conversation(
    account_client, capture_mail, make_tenant, monkeypatch
):
    import asyncio

    from app.accounts import router as accounts_router
    from app.conversations.service import claim_guest_conversations as real_claim
    from app.db.base import get_sessionmaker
    from app.db.models import AccountSession, Conversation

    client, _ = account_client
    account, account_headers = await register_login(client, capture_mail)
    assert (await client.post("/v1/auth/logout", headers=account_headers)).status_code == 204
    _, collection_id = await _public_collection(make_tenant, monkeypatch)
    headers = await csrf(client)
    login_locked, resume_login = asyncio.Event(), asyncio.Event()

    async def paused_claim(db, session_id, user_id):
        locked = await db.scalar(
            select(AccountSession).where(AccountSession.id == session_id).with_for_update()
        )
        assert locked is not None
        login_locked.set()
        await resume_login.wait()
        return await real_claim(db, session_id, user_id)

    monkeypatch.setattr(accounts_router, "claim_guest_conversations", paused_claim)
    logging_in = asyncio.create_task(
        client.post(
            "/v1/auth/login",
            json={"email": account["user"]["email"], "password": PASSWORD},
            headers=headers,
        )
    )
    await asyncio.wait_for(login_locked.wait(), 5)
    creating = asyncio.create_task(
        client.post(
            f"/v1/collections/{collection_id}/conversations",
            json={"title": "Must not be orphaned"},
            headers=headers,
        )
    )
    await asyncio.sleep(0.1)
    resume_login.set()
    login_response, create_response = await asyncio.gather(logging_in, creating)
    assert login_response.status_code == 200
    assert create_response.status_code == 401
    assert create_response.json()["code"] == "invalid_session"
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(Conversation)) is None


async def test_password_rotation_failure_rolls_back_guest_conversation_claim(
    account_client, capture_mail, make_tenant, monkeypatch
):
    from app.accounts import router as accounts_router
    from app.db.base import get_sessionmaker
    from app.db.models import Conversation

    client, _ = account_client
    account, account_headers = await register_login(client, capture_mail)
    assert (await client.post("/v1/auth/logout", headers=account_headers)).status_code == 204
    _, collection_id = await _public_collection(make_tenant, monkeypatch)
    headers = await csrf(client)
    created = await client.post(
        f"/v1/collections/{collection_id}/conversations", json={}, headers=headers
    )
    conversation_id = uuid.UUID(created.json()["id"])

    async def fail_rotation(*args, **kwargs):
        raise RuntimeError("synthetic session rotation failure")

    monkeypatch.setattr(accounts_router, "create_authenticated_session", fail_rotation)
    with pytest.raises(RuntimeError, match="synthetic session rotation failure"):
        await client.post(
            "/v1/auth/login",
            json={"email": account["user"]["email"], "password": PASSWORD},
            headers=headers,
        )
    async with get_sessionmaker()() as db:
        conversation = await db.get(Conversation, conversation_id)
        assert conversation.owner_user_id is None
        assert conversation.owner_guest_session_id is not None


async def test_conversation_id_does_not_bypass_current_public_collection_scope(
    account_client, make_tenant, monkeypatch
):
    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    client, _ = account_client
    _, collection_id = await _public_collection(make_tenant, monkeypatch)
    headers = await csrf(client)
    created = await client.post(
        f"/v1/collections/{collection_id}/conversations", json={}, headers=headers
    )
    assert created.status_code == 201
    async with get_sessionmaker()() as db:
        await db.execute(
            update(Collection)
            .where(Collection.id == uuid.UUID(collection_id))
            .values(is_public=False, read_only=False)
        )
        await db.commit()
    hidden = await client.get(f"/v1/conversations/{created.json()['id']}/queries")
    assert hidden.status_code == 404


async def test_anonymous_session_renews_inside_bounded_ttl(account_client, monkeypatch):
    from app.accounts.sessions import token_hash
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import AccountSession

    monkeypatch.setenv("AUTH_GUEST_SESSION_TTL_S", "3600")
    get_settings.cache_clear()
    client, _ = account_client
    await client.get("/v1/auth/session")
    raw = client.cookies.get("__Host-docqa_session")
    async with get_sessionmaker()() as db:
        await db.execute(
            update(AccountSession)
            .where(AccountSession.token_hash == token_hash(raw))
            .values(expires_at=datetime.now(UTC) + timedelta(seconds=60))
        )
        await db.commit()
    renewed = await client.get("/v1/auth/session")
    assert renewed.status_code == 200
    assert "Max-Age=3600" in renewed.headers["set-cookie"]
    assert client.cookies.get("__Host-docqa_session") == raw
    async with get_sessionmaker()() as db:
        expires = await db.scalar(
            select(AccountSession.expires_at).where(AccountSession.token_hash == token_hash(raw))
        )
        assert expires > datetime.now(UTC) + timedelta(minutes=50)


async def test_legacy_uuid_claim_endpoint_is_disabled(account_client):
    client, _ = account_client
    headers = await csrf(client)
    response = await client.post(
        "/v1/queries/claim", headers=headers, json={"query_ids": [str(uuid.uuid4())]}
    )
    assert response.status_code == 410
    assert response.json()["code"] == "legacy_guest_claim_disabled"


async def test_invalid_cursors_and_empty_patch_fail_without_cross_conversation_authority(
    client, tenant
):
    collection_id = await _private_collection(client, tenant)
    first = (
        await client.post(
            f"/v1/collections/{collection_id}/conversations",
            json={},
            headers=tenant["headers"],
        )
    ).json()
    second = (
        await client.post(
            f"/v1/collections/{collection_id}/conversations",
            json={"title": "Second"},
            headers=tenant["headers"],
        )
    ).json()
    malformed = await client.get(
        f"/v1/collections/{collection_id}/conversations",
        params={"before": "not-a-cursor"},
        headers=tenant["headers"],
    )
    assert malformed.status_code == 400 and malformed.json()["code"] == "invalid_cursor"
    assert (
        await client.patch(f"/v1/conversations/{first['id']}", json={}, headers=tenant["headers"])
    ).status_code == 400

    from app.db.base import get_sessionmaker
    from app.db.models import Query

    async with get_sessionmaker()() as db:
        foreign_anchor = Query(
            tenant_id=tenant["id"],
            collection_id=uuid.UUID(collection_id),
            conversation_id=uuid.UUID(second["id"]),
            question="Other branch",
            answer="answer",
            refused=False,
            outcome="answered",
        )
        db.add(foreign_anchor)
        await db.commit()
    response = await client.get(
        f"/v1/conversations/{first['id']}/queries",
        params={"before": str(foreign_anchor.id)},
        headers=tenant["headers"],
    )
    assert response.status_code == 404


async def test_conversation_constraints_parent_delete_and_collection_cascade(client, tenant):
    from app.db.base import get_sessionmaker
    from app.db.models import ApiKey, Collection, Conversation, Query

    collection_id = await _private_collection(client, tenant)
    async with get_sessionmaker()() as db:
        api_key_id = await db.scalar(select(ApiKey.id).where(ApiKey.tenant_id == tenant["id"]))
        conversation = Conversation(
            tenant_id=tenant["id"],
            collection_id=uuid.UUID(collection_id),
            title="Chain",
            created_by_api_key_id=api_key_id,
        )
        db.add(conversation)
        await db.flush()
        parent = Query(
            tenant_id=tenant["id"],
            collection_id=uuid.UUID(collection_id),
            conversation_id=conversation.id,
            question="Parent",
            answer="answer",
            refused=False,
            outcome="answered",
        )
        db.add(parent)
        await db.flush()
        child = Query(
            tenant_id=tenant["id"],
            collection_id=uuid.UUID(collection_id),
            conversation_id=conversation.id,
            parent_query_id=parent.id,
            question="Child",
            answer="answer",
            refused=False,
            outcome="answered",
        )
        db.add(child)
        await db.commit()
        child_id, conversation_id = child.id, conversation.id

        await db.delete(parent)
        await db.commit()
        await db.refresh(child)
        assert child.parent_query_id is None

        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(
                    Conversation(
                        tenant_id=tenant["id"],
                        collection_id=uuid.UUID(collection_id),
                        title="Invalid owner",
                    )
                )
                await db.flush()
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(
                    Conversation(
                        tenant_id=tenant["id"],
                        collection_id=uuid.UUID(collection_id),
                        title="Legacy must be archived",
                        kind="legacy",
                        created_by_api_key_id=api_key_id,
                    )
                )
                await db.flush()
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(
                    Query(
                        tenant_id=tenant["id"],
                        collection_id=uuid.UUID(collection_id),
                        conversation_id=conversation.id,
                        question="Invalid outcome",
                        answer=None,
                        refused=False,
                        outcome="unknown",
                    )
                )
                await db.flush()

        collection = await db.get(Collection, uuid.UUID(collection_id))
        await db.delete(collection)
        await db.commit()
    async with get_sessionmaker()() as db:
        assert await db.get(Conversation, conversation_id) is None
        assert await db.get(Query, child_id) is None


async def test_tenant_cascade_removes_api_key_owned_conversations(client, make_tenant):
    from app.db.base import get_sessionmaker
    from app.db.models import ApiKey, Conversation, Query, Tenant

    owner = await make_tenant()
    collection_id = await _private_collection(client, owner)
    async with get_sessionmaker()() as db:
        api_key_id = await db.scalar(select(ApiKey.id).where(ApiKey.tenant_id == owner["id"]))
        conversation = Conversation(
            tenant_id=owner["id"],
            collection_id=uuid.UUID(collection_id),
            title="Tenant cascade",
            created_by_api_key_id=api_key_id,
        )
        db.add(conversation)
        await db.flush()
        query = Query(
            tenant_id=owner["id"],
            collection_id=uuid.UUID(collection_id),
            conversation_id=conversation.id,
            question="Question",
            answer="answer",
            refused=False,
            outcome="answered",
        )
        db.add(query)
        await db.commit()
        conversation_id, query_id = conversation.id, query.id
        service_tenant = await db.get(Tenant, owner["id"])
        await db.delete(service_tenant)
        await db.commit()
    async with get_sessionmaker()() as db:
        assert await db.get(Conversation, conversation_id) is None
        assert await db.get(Query, query_id) is None
