"""Conversation-aware query pipeline contracts against real PostgreSQL."""

import hashlib
import json
import uuid

import pytest
from sqlalchemy import select

from tests.integration.test_accounts import account_client, capture_mail, csrf, register_login

__all__ = ["account_client", "capture_mail"]


POLICY_MD = b"# Policy\n\nEmployees receive 27 vacation days per year.\n"


def test_standalone_idempotency_fingerprint_keeps_legacy_json_spacing():
    from app.api.v1.query import _fingerprint

    parts = ["query", str(uuid.uuid4()), 3, "employee", ["all"], False, "Question"]
    historic = hashlib.sha256(json.dumps(parts).encode()).hexdigest()
    assert _fingerprint(parts, legacy_spacing=True) == historic
    assert _fingerprint(parts, legacy_spacing=False) != historic


async def ready_collection_and_conversation(client, tenant) -> tuple[str, str]:
    created = await client.post(
        "/v1/collections", json={"name": "Conversation query"}, headers=tenant["headers"]
    )
    assert created.status_code == 201, created.text
    collection_id = created.json()["id"]
    uploaded = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("policy.md", POLICY_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    assert uploaded.status_code == 202, uploaded.text
    conversation = await client.post(
        f"/v1/collections/{collection_id}/conversations",
        json={"title": "Policy questions"},
        headers=tenant["headers"],
    )
    assert conversation.status_code == 201, conversation.text
    return collection_id, conversation.json()["id"]


async def test_conversation_root_records_context_and_additive_done_contract(client, tenant):
    from app.conversations.context import access_fingerprint
    from app.db.base import get_sessionmaker
    from app.db.models import Collection, Query

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    response = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "parent_query_id": None,
            "question": "How many vacation days do employees receive?",
            "stream": False,
        },
        headers=tenant["headers"],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "answered"
    assert body["context"] == {"reset": False, "turns_used": 0}
    async with get_sessionmaker()() as db:
        query = await db.scalar(select(Query).where(Query.id == uuid.UUID(body["query_id"])))
        collection = await db.get(Collection, uuid.UUID(collection_id))
    assert query is not None and collection is not None
    assert query.conversation_id == uuid.UUID(conversation_id)
    assert query.parent_query_id is None
    assert query.outcome == "answered"
    assert query.source_generation == collection.source_generation
    assert query.access_fingerprint == access_fingerprint(
        __import__("app.access", fromlist=["resolve_principal"]).resolve_principal(
            __import__("app.config", fromlist=["get_settings"]).get_settings(), None
        )
    )


async def test_parent_without_conversation_is_rejected_before_pipeline(client, tenant, monkeypatch):
    from app.generation.llm.stub import StubLLM

    collection_id, _ = await ready_collection_and_conversation(client, tenant)
    calls_before = StubLLM.calls
    response = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "parent_query_id": str(uuid.uuid4()),
            "question": "And in 2022?",
            "stream": False,
        },
        headers=tenant["headers"],
    )

    assert response.status_code == 422
    assert StubLLM.calls == calls_before


@pytest.mark.parametrize(
    ("code", "error_type"),
    [
        ("query_persistence_failed", "QueryPersistenceError"),
        ("query_source_changed", "QuerySourceChangedError"),
    ],
)
async def test_json_collector_preserves_stable_contextual_persistence_code(code, error_type):
    from app.api.v1.query import _collect_json
    from app.core import errors
    from app.generation.service import ErrorEvent, MetaEvent

    async def events():
        yield MetaEvent(uuid.uuid4(), {})
        yield ErrorEvent(code, "stable failure")

    with pytest.raises(getattr(errors, error_type)) as caught:
        await _collect_json(events())
    assert caught.value.code == code


async def test_contextual_json_idempotency_replays_one_query_without_provider_calls(client, tenant):
    from sqlalchemy import func

    from app.db.base import get_sessionmaker
    from app.db.models import Query
    from app.generation.llm.stub import StubLLM

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    headers = {**tenant["headers"], "Idempotency-Key": "conversation-root"}
    payload = {
        "collection_id": collection_id,
        "conversation_id": conversation_id,
        "parent_query_id": None,
        "question": "How many vacation days do employees receive?",
        "stream": False,
    }
    calls_before = StubLLM.calls
    first = await client.post("/v1/query", json=payload, headers=headers)
    calls_after_first = StubLLM.calls
    second = await client.post("/v1/query", json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["query_id"] == second.json()["query_id"]
    assert second.headers["x-idempotency-replay"] == "true"
    assert calls_after_first - calls_before == 2
    assert StubLLM.calls == calls_after_first
    async with get_sessionmaker()() as db:
        count = await db.scalar(
            select(func.count(Query.id)).where(Query.conversation_id == uuid.UUID(conversation_id))
        )
    assert count == 1


async def test_contextual_idempotency_rejects_changed_parent_and_source_generation(client, tenant):
    from sqlalchemy import update

    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    headers = {**tenant["headers"], "Idempotency-Key": "conversation-versioned"}
    payload = {
        "collection_id": collection_id,
        "conversation_id": conversation_id,
        "parent_query_id": None,
        "question": "How many vacation days do employees receive?",
        "stream": False,
    }
    first = await client.post("/v1/query", json=payload, headers=headers)
    assert first.status_code == 200, first.text

    changed_parent = await client.post(
        "/v1/query",
        json={**payload, "parent_query_id": first.json()["query_id"]},
        headers=headers,
    )
    assert changed_parent.status_code == 422
    assert changed_parent.json()["code"] == "idempotency_key_reused"

    async with get_sessionmaker()() as db:
        await db.execute(
            update(Collection)
            .where(Collection.id == uuid.UUID(collection_id))
            .values(source_generation=Collection.source_generation + 1)
        )
        await db.commit()
    source_changed = await client.post("/v1/query", json=payload, headers=headers)
    assert source_changed.status_code == 422
    assert source_changed.json()["code"] == "idempotency_key_reused"


async def test_followup_uses_normalized_question_and_records_parent(client, tenant, monkeypatch):
    from app.conversations.normalizer import NORMALIZER_SYSTEM_PROMPT
    from app.db.base import get_sessionmaker
    from app.db.models import Query
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.planning import PLANNER_SYSTEM_PROMPT

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    root = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "question": "How many vacation days do employees receive?",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    assert root.status_code == 200, root.text
    prompts = []

    class FollowupLLM:
        model_name = "deepseek-flash"

        async def stream(self, system, user):
            prompts.append((system, user))
            if system == NORMALIZER_SYSTEM_PROMPT:
                yield TextDelta(
                    '{"action":"search","effective_question":'
                    '"How many vacation days do employees receive?"}'
                )
                yield StreamUsage(7, 2)
                return
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(11, 3)
                return
            yield TextDelta("Employees receive 27 vacation days [1].")
            yield StreamUsage(101, 19)

    monkeypatch.setattr(service, "get_llm_provider", lambda settings: FollowupLLM())
    followup = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "parent_query_id": root.json()["query_id"],
            "question": "And how many was that?",
            "stream": False,
        },
        headers=tenant["headers"],
    )

    assert followup.status_code == 200, followup.text
    body = followup.json()
    assert body["outcome"] == "answered"
    assert body["context"] == {"reset": False, "turns_used": 1}
    assert body["usage"]["prompt_tokens"] == 119
    assert [system for system, _ in prompts] == [
        NORMALIZER_SYSTEM_PROMPT,
        PLANNER_SYSTEM_PROMPT,
        service.SYSTEM_PROMPT,
    ]
    assert "Original user wording: And how many was that?" in prompts[-1][1]
    assert (
        "Standalone retrieval interpretation: How many vacation days do employees receive?"
        in prompts[-1][1]
    )
    async with get_sessionmaker()() as db:
        row = await db.get(Query, uuid.UUID(body["query_id"]))
    assert row is not None
    assert row.question == "And how many was that?"
    assert str(row.parent_query_id) == root.json()["query_id"]


async def test_malformed_normalizer_returns_persisted_clarification_without_retrieval(
    client, tenant, monkeypatch
):
    from app.conversations.normalizer import GENERIC_CLARIFICATION, NORMALIZER_SYSTEM_PROMPT
    from app.db.base import get_sessionmaker
    from app.db.models import Query
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    root = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "question": "How many vacation days do employees receive?",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    retrieval_calls = 0
    real_retrieve = service.retrieve

    async def counted_retrieve(*args, **kwargs):
        nonlocal retrieval_calls
        retrieval_calls += 1
        return await real_retrieve(*args, **kwargs)

    class MalformedNormalizer:
        model_name = "deepseek-flash"

        async def stream(self, system, user):
            assert system == NORMALIZER_SYSTEM_PROMPT
            yield TextDelta("not-json")
            yield StreamUsage(13, 5)

    monkeypatch.setattr(service, "retrieve", counted_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: MalformedNormalizer())
    response = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "parent_query_id": root.json()["query_id"],
            "question": "What about it?",
            "stream": False,
        },
        headers=tenant["headers"],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert retrieval_calls == 0
    assert body["answer"] == GENERIC_CLARIFICATION
    assert body["outcome"] == "clarification"
    assert body["reason"] == "context_clarification"
    assert body["sources"] == [] and body["citations"] == []
    async with get_sessionmaker()() as db:
        row = await db.get(Query, uuid.UUID(body["query_id"]))
    assert row is not None
    assert row.outcome == "clarification" and row.outcome_reason == "context_clarification"


async def test_failed_parent_and_new_send_to_archived_chat_fail_in_preflight(client, tenant):
    from sqlalchemy import update

    from app.db.base import get_sessionmaker
    from app.db.models import Query
    from app.generation.llm.stub import StubLLM

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    root = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "question": "How many vacation days do employees receive?",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    assert root.status_code == 200
    async with get_sessionmaker()() as db:
        await db.execute(
            update(Query)
            .where(Query.id == uuid.UUID(root.json()["query_id"]))
            .values(outcome="failed", outcome_reason="provider_unavailable")
        )
        await db.commit()
    calls_before = StubLLM.calls
    invalid_parent = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "parent_query_id": root.json()["query_id"],
            "question": "And that?",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    assert invalid_parent.status_code == 422
    assert invalid_parent.json()["code"] == "invalid_conversation_parent"
    assert StubLLM.calls == calls_before

    archived = await client.patch(
        f"/v1/conversations/{conversation_id}",
        json={"archived": True},
        headers=tenant["headers"],
    )
    assert archived.status_code == 200
    rejected = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "question": "A new root",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "conversation_archived"
    assert StubLLM.calls == calls_before


async def test_guest_answer_finishing_after_login_uses_current_conversation_owner(
    account_client, capture_mail, make_tenant, monkeypatch
):
    import asyncio

    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import Collection, Conversation, Query
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.planning import PLANNER_SYSTEM_PROMPT

    client, _ = account_client
    public_tenant = await make_tenant()
    created = await client.post(
        "/v1/collections", json={"name": "Public context"}, headers=public_tenant["headers"]
    )
    collection_id = created.json()["id"]
    uploaded = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("policy.md", POLICY_MD, "text/markdown")},
        headers=public_tenant["headers"],
    )
    assert uploaded.status_code == 202
    async with get_sessionmaker()() as db:
        collection = await db.get(Collection, uuid.UUID(collection_id))
        assert collection is not None
        collection.is_public = True
        collection.read_only = True
        await db.commit()
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(public_tenant["id"]))
    get_settings.cache_clear()
    guest_headers = await csrf(client)
    created_chat = await client.post(
        f"/v1/collections/{collection_id}/conversations",
        json={"title": "Guest stream"},
        headers=guest_headers,
    )
    assert created_chat.status_code == 201, created_chat.text
    conversation_id = created_chat.json()["id"]
    answer_started = asyncio.Event()
    resume_answer = asyncio.Event()

    class PausedAnswerLLM:
        model_name = "stub"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(0, 0)
                return
            answer_started.set()
            await resume_answer.wait()
            yield TextDelta("Employees receive 27 vacation days [1].")
            yield StreamUsage(10, 3)

    monkeypatch.setattr(service, "get_llm_provider", lambda settings: PausedAnswerLLM())
    asking = asyncio.create_task(
        client.post(
            "/v1/query",
            json={
                "collection_id": collection_id,
                "conversation_id": conversation_id,
                "question": "How many vacation days do employees receive?",
                "stream": False,
            },
            headers=guest_headers,
        )
    )
    await asyncio.wait_for(answer_started.wait(), timeout=5)
    account, _ = await register_login(client, capture_mail)
    resume_answer.set()
    answered = await asyncio.wait_for(asking, timeout=5)

    assert answered.status_code == 200, answered.text
    async with get_sessionmaker()() as db:
        conversation = await db.get(Conversation, uuid.UUID(conversation_id))
        query = await db.get(Query, uuid.UUID(answered.json()["query_id"]))
    assert conversation is not None and query is not None
    assert str(conversation.owner_user_id) == account["user"]["id"]
    assert query.user_id == conversation.owner_user_id
    assert query.conversation_id == conversation.id
    get_settings.cache_clear()


async def test_accepted_stream_may_finish_after_archive_but_new_send_is_rejected(
    client, tenant, monkeypatch
):
    import asyncio

    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.planning import PLANNER_SYSTEM_PROMPT

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    answer_started = asyncio.Event()
    resume_answer = asyncio.Event()

    class PausedAnswerLLM:
        model_name = "stub"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(0, 0)
                return
            answer_started.set()
            await resume_answer.wait()
            yield TextDelta("Employees receive 27 vacation days [1].")
            yield StreamUsage(10, 3)

    monkeypatch.setattr(service, "get_llm_provider", lambda settings: PausedAnswerLLM())
    asking = asyncio.create_task(
        client.post(
            "/v1/query",
            json={
                "collection_id": collection_id,
                "conversation_id": conversation_id,
                "question": "How many vacation days do employees receive?",
                "stream": False,
            },
            headers=tenant["headers"],
        )
    )
    await asyncio.wait_for(answer_started.wait(), timeout=5)
    archived = await client.patch(
        f"/v1/conversations/{conversation_id}",
        json={"archived": True},
        headers=tenant["headers"],
    )
    assert archived.status_code == 200
    resume_answer.set()
    finished = await asyncio.wait_for(asking, timeout=5)
    assert finished.status_code == 200, finished.text
    assert finished.json()["outcome"] == "answered"

    rejected = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "question": "Another vacation question",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "conversation_archived"


async def test_slow_older_query_keeps_acceptance_order_after_fast_newer_completion(
    client, tenant, monkeypatch
):
    import asyncio

    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.planning import PLANNER_SYSTEM_PROMPT

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    slow_started = asyncio.Event()
    resume_slow = asyncio.Event()

    class OrderedLLM:
        model_name = "stub"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(0, 0)
                return
            if "Slow accepted: How many vacation days do employees receive?" in user:
                slow_started.set()
                await resume_slow.wait()
            yield TextDelta("Employees receive 27 vacation days [1].")
            yield StreamUsage(10, 3)

    monkeypatch.setattr(service, "get_llm_provider", lambda settings: OrderedLLM())
    slow = asyncio.create_task(
        client.post(
            "/v1/query",
            json={
                "collection_id": collection_id,
                "conversation_id": conversation_id,
                "question": "Slow accepted: How many vacation days do employees receive?",
                "stream": False,
            },
            headers=tenant["headers"],
        )
    )
    await asyncio.wait_for(slow_started.wait(), timeout=5)
    fast = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "question": "Fast newer: How many vacation days do employees receive?",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    assert fast.status_code == 200, fast.text
    resume_slow.set()
    slow_result = await asyncio.wait_for(slow, timeout=5)
    assert slow_result.status_code == 200, slow_result.text

    transcript = await client.get(
        f"/v1/conversations/{conversation_id}/queries", headers=tenant["headers"]
    )
    assert transcript.status_code == 200
    assert [row["question"] for row in transcript.json()["queries"]] == [
        "Fast newer: How many vacation days do employees receive?",
        "Slow accepted: How many vacation days do employees receive?",
    ]


async def test_contextual_guest_idempotency_is_scoped_by_session_on_same_ip(
    account_client, make_tenant, monkeypatch
):
    from httpx import ASGITransport, AsyncClient

    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import Collection

    first, application = account_client
    public_tenant = await make_tenant()
    created = await first.post(
        "/v1/collections", json={"name": "Public replay"}, headers=public_tenant["headers"]
    )
    collection_id = created.json()["id"]
    uploaded = await first.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("policy.md", POLICY_MD, "text/markdown")},
        headers=public_tenant["headers"],
    )
    assert uploaded.status_code == 202
    async with get_sessionmaker()() as db:
        collection = await db.get(Collection, uuid.UUID(collection_id))
        assert collection is not None
        collection.is_public = True
        collection.read_only = True
        await db.commit()
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(public_tenant["id"]))
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as second:
        first_headers = await csrf(first)
        second_headers = await csrf(second)
        first_chat = await first.post(
            f"/v1/collections/{collection_id}/conversations",
            json={"title": "First guest"},
            headers=first_headers,
        )
        second_chat = await second.post(
            f"/v1/collections/{collection_id}/conversations",
            json={"title": "Second guest"},
            headers=second_headers,
        )
        assert first_chat.status_code == second_chat.status_code == 201
        key = "same-browser-key"

        def payload(conversation_id):
            return {
                "collection_id": collection_id,
                "conversation_id": conversation_id,
                "question": "How many vacation days do employees receive?",
                "stream": False,
            }

        first_answer = await first.post(
            "/v1/query",
            json=payload(first_chat.json()["id"]),
            headers={**first_headers, "Idempotency-Key": key},
        )
        second_answer = await second.post(
            "/v1/query",
            json=payload(second_chat.json()["id"]),
            headers={**second_headers, "Idempotency-Key": key},
        )
        replay = await first.post(
            "/v1/query",
            json=payload(first_chat.json()["id"]),
            headers={**first_headers, "Idempotency-Key": key},
        )

    assert first_answer.status_code == second_answer.status_code == replay.status_code == 200
    assert first_answer.json()["query_id"] != second_answer.json()["query_id"]
    assert replay.json()["query_id"] == first_answer.json()["query_id"]
    assert replay.headers["x-idempotency-replay"] == "true"
    get_settings.cache_clear()


async def test_contextual_provider_error_is_persisted_failed_before_response(
    client, tenant, monkeypatch
):
    from app.db.base import get_sessionmaker
    from app.db.models import Query
    from app.generation import service
    from app.generation.llm import GenerationError, StreamUsage, TextDelta
    from app.retrieval.planning import PLANNER_SYSTEM_PROMPT

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)

    class FailingAnswerLLM:
        model_name = "stub"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(2, 1)
                return
            yield StreamUsage(3, 1)
            raise GenerationError("provider failed")

    monkeypatch.setattr(service, "get_llm_provider", lambda settings: FailingAnswerLLM())
    response = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "question": "How many vacation days do employees receive?",
            "stream": False,
        },
        headers=tenant["headers"],
    )

    assert response.status_code == 503
    assert response.json()["code"] == "provider_unavailable"
    async with get_sessionmaker()() as db:
        row = await db.scalar(
            select(Query).where(Query.conversation_id == uuid.UUID(conversation_id))
        )
    assert row is not None
    assert row.outcome == "failed" and row.outcome_reason == "provider_unavailable"
    assert (row.prompt_tokens, row.completion_tokens) == (5, 2)


async def test_contextual_generator_close_persists_partial_as_cancelled(
    client, tenant, monkeypatch
):
    from app.access import resolve_principal
    from app.config import get_settings
    from app.conversations.context import ConversationContext, access_fingerprint
    from app.db.base import get_sessionmaker
    from app.db.models import Collection, Query
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.planning import PLANNER_SYSTEM_PROMPT

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    principal = resolve_principal(get_settings(), None)
    async with get_sessionmaker()() as db:
        collection = await db.get(Collection, uuid.UUID(collection_id))
        assert collection is not None
        data_version = collection.data_version
        source_generation = collection.source_generation
    context = ConversationContext(
        conversation_id=uuid.UUID(conversation_id),
        parent_query_id=None,
        source_generation=source_generation,
        access_fingerprint=access_fingerprint(principal),
        reset=False,
        turns=(),
        references=(),
    )

    class PartialAnswerLLM:
        model_name = "stub"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(2, 1)
                return
            yield StreamUsage(3, 1)
            yield TextDelta("A partial grounded-looking answer [1].")
            yield TextDelta("This must never complete.")

    monkeypatch.setattr(service, "get_llm_provider", lambda settings: PartialAnswerLLM())
    events = service.run_query(
        tenant["id"],
        uuid.UUID(collection_id),
        "How many vacation days do employees receive?",
        get_settings(),
        principal,
        data_version,
        conversation_context=context,
    )
    assert isinstance(await anext(events), service.MetaEvent)
    assert isinstance(await anext(events), service.SourcesEvent)
    partial = await anext(events)
    assert isinstance(partial, service.DeltaEvent)
    await events.aclose()

    async with get_sessionmaker()() as db:
        row = await db.scalar(
            select(Query).where(Query.conversation_id == uuid.UUID(conversation_id))
        )
    assert row is not None
    assert row.outcome == "cancelled" and row.outcome_reason == "client_cancelled"
    assert row.answer == partial.text
    assert row.refused is False


async def test_contextual_persistence_failure_returns_no_done_and_no_query_row(
    client, tenant, monkeypatch
):
    from sqlalchemy import func

    from app.db.base import get_sessionmaker
    from app.db.models import Query
    from app.generation import service

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)

    async def failed_record(**kwargs):
        return "failed"

    monkeypatch.setattr(service, "_record_query", failed_record)
    response = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "conversation_id": conversation_id,
            "question": "How many vacation days do employees receive?",
            "stream": False,
        },
        headers=tenant["headers"],
    )

    assert response.status_code == 503
    assert response.json()["code"] == "query_persistence_failed"
    async with get_sessionmaker()() as db:
        count = await db.scalar(
            select(func.count(Query.id)).where(Query.conversation_id == uuid.UUID(conversation_id))
        )
    assert count == 0


async def test_contextual_source_wipe_during_answer_returns_source_changed_without_query(
    client, tenant, monkeypatch
):
    import asyncio

    from sqlalchemy import func

    from app.cli import wipe_collection
    from app.db.base import get_sessionmaker
    from app.db.models import Query
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.planning import PLANNER_SYSTEM_PROMPT

    collection_id, conversation_id = await ready_collection_and_conversation(client, tenant)
    answer_started = asyncio.Event()
    resume_answer = asyncio.Event()

    class PausedAnswerLLM:
        model_name = "stub"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(0, 0)
                return
            answer_started.set()
            await resume_answer.wait()
            yield TextDelta("Employees receive 27 vacation days [1].")
            yield StreamUsage(10, 3)

    monkeypatch.setattr(service, "get_llm_provider", lambda settings: PausedAnswerLLM())
    asking = asyncio.create_task(
        client.post(
            "/v1/query",
            json={
                "collection_id": collection_id,
                "conversation_id": conversation_id,
                "question": "How many vacation days do employees receive?",
                "stream": False,
            },
            headers=tenant["headers"],
        )
    )
    await asyncio.wait_for(answer_started.wait(), timeout=5)
    await wipe_collection(uuid.UUID(collection_id))
    resume_answer.set()
    response = await asyncio.wait_for(asking, timeout=5)

    assert response.status_code == 409
    assert response.json()["code"] == "query_source_changed"
    async with get_sessionmaker()() as db:
        count = await db.scalar(
            select(func.count(Query.id)).where(Query.conversation_id == uuid.UUID(conversation_id))
        )
    assert count == 0
