"""Actor-scoped, access-filtered conversation context selection in PostgreSQL."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import Request
from sqlalchemy import select

from app.access.roles import Principal
from app.accounts.actor import Actor
from app.config import get_settings
from app.conversations.context import access_fingerprint, load_conversation_context
from app.core.errors import (
    ConversationArchivedError,
    ConversationReadOnlyError,
    InvalidConversationParentError,
    NotFoundError,
)


def request() -> Request:
    return Request({"type": "http", "headers": []})


async def make_collection(client, tenant) -> uuid.UUID:
    response = await client.post(
        "/v1/collections",
        json={"name": f"Context {uuid.uuid4().hex[:6]}"},
        headers=tenant["headers"],
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


async def owner_actor(tenant) -> Actor:
    from app.db.base import get_sessionmaker
    from app.db.models import ApiKey

    async with get_sessionmaker()() as db:
        key_id = await db.scalar(select(ApiKey.id).where(ApiKey.tenant_id == tenant["id"]))
    return Actor("api_key", None, tenant["id"], key_id)


async def add_conversation(db, tenant_id, collection_id, api_key_id, *, archived=False):
    from app.db.models import Conversation

    conversation = Conversation(
        tenant_id=tenant_id,
        collection_id=collection_id,
        title="Context chain",
        created_by_api_key_id=api_key_id,
        archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(conversation)
    await db.flush()
    return conversation


async def add_query(
    db,
    tenant_id,
    collection_id,
    conversation_id,
    question,
    fingerprint,
    *,
    parent=None,
    outcome="answered",
    generation=0,
    reset=False,
    answer="assistant answer secret",
):
    from app.db.models import Query

    query = Query(
        tenant_id=tenant_id,
        collection_id=collection_id,
        conversation_id=conversation_id,
        parent_query_id=parent,
        question=question,
        answer=answer,
        refused=outcome == "refused",
        outcome=outcome,
        source_generation=generation,
        access_fingerprint=fingerprint,
        context_reset=reset,
    )
    db.add(query)
    await db.flush()
    return query


async def test_parent_validation_is_actor_collection_and_conversation_scoped(
    client, tenant, make_tenant
):
    from app.db.base import get_sessionmaker

    collection_id = await make_collection(client, tenant)
    other_collection_id = await make_collection(client, tenant)
    actor = await owner_actor(tenant)
    principal = Principal("employee", ("all",))
    fingerprint = access_fingerprint(principal)
    async with get_sessionmaker()() as db:
        conversation = await add_conversation(db, tenant["id"], collection_id, actor.api_key_id)
        other = await add_conversation(db, tenant["id"], collection_id, actor.api_key_id)
        other_collection = await add_conversation(
            db, tenant["id"], other_collection_id, actor.api_key_id
        )
        good = await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Good parent",
            fingerprint,
        )
        wrong_conversation = await add_query(
            db,
            tenant["id"],
            collection_id,
            other.id,
            "Other conversation",
            fingerprint,
        )
        wrong_collection = await add_query(
            db,
            tenant["id"],
            other_collection_id,
            other_collection.id,
            "Other collection",
            fingerprint,
        )
        failed = await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Failed parent",
            fingerprint,
            outcome="failed",
        )
        await db.commit()

    async with get_sessionmaker()() as db:
        valid = await load_conversation_context(
            db,
            request(),
            actor,
            collection_id,
            conversation.id,
            good.id,
            principal,
            get_settings(),
        )
        assert [turn.question for turn in valid.turns] == ["Good parent"]
        with pytest.raises(NotFoundError):
            await load_conversation_context(
                db,
                request(),
                actor,
                collection_id,
                conversation.id,
                wrong_conversation.id,
                principal,
                get_settings(),
            )
        with pytest.raises(NotFoundError):
            await load_conversation_context(
                db,
                request(),
                actor,
                collection_id,
                conversation.id,
                wrong_collection.id,
                principal,
                get_settings(),
            )
        with pytest.raises(InvalidConversationParentError):
            await load_conversation_context(
                db,
                request(),
                actor,
                collection_id,
                conversation.id,
                failed.id,
                principal,
                get_settings(),
            )

    stranger = await make_tenant()
    with pytest.raises(NotFoundError):
        async with get_sessionmaker()() as db:
            await load_conversation_context(
                db,
                request(),
                await owner_actor(stranger),
                collection_id,
                conversation.id,
                good.id,
                principal,
                get_settings(),
            )


async def test_archived_and_legacy_conversations_reject_new_context(client, tenant):
    from app.db.base import get_sessionmaker

    collection_id = await make_collection(client, tenant)
    actor = await owner_actor(tenant)
    principal = Principal("employee", ("all",))
    async with get_sessionmaker()() as db:
        archived = await add_conversation(
            db, tenant["id"], collection_id, actor.api_key_id, archived=True
        )
        legacy = await add_conversation(
            db, tenant["id"], collection_id, actor.api_key_id, archived=True
        )
        legacy.kind = "legacy"
        await db.commit()
    async with get_sessionmaker()() as db:
        with pytest.raises(ConversationArchivedError):
            await load_conversation_context(
                db,
                request(),
                actor,
                collection_id,
                archived.id,
                None,
                principal,
                get_settings(),
            )
        with pytest.raises(ConversationReadOnlyError):
            await load_conversation_context(
                db,
                request(),
                actor,
                collection_id,
                legacy.id,
                None,
                principal,
                get_settings(),
            )


async def test_chain_is_bounded_excludes_siblings_and_stops_at_reset_boundary(client, tenant):
    from app.db.base import get_sessionmaker

    collection_id = await make_collection(client, tenant)
    actor = await owner_actor(tenant)
    principal = Principal("employee", ("all",))
    fingerprint = access_fingerprint(principal)
    async with get_sessionmaker()() as db:
        conversation = await add_conversation(db, tenant["id"], collection_id, actor.api_key_id)
        parent = None
        chain = []
        for index in range(1, 7):
            query = await add_query(
                db,
                tenant["id"],
                collection_id,
                conversation.id,
                f"Question {index}",
                fingerprint,
                parent=parent.id if parent else None,
                reset=index == 4,
            )
            chain.append(query)
            parent = query
        await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Sibling secret",
            fingerprint,
            parent=chain[4].id,
        )
        await db.commit()
    async with get_sessionmaker()() as db:
        context = await load_conversation_context(
            db,
            request(),
            actor,
            collection_id,
            conversation.id,
            chain[-1].id,
            principal,
            get_settings(),
        )
    assert [turn.question for turn in context.turns] == ["Question 4", "Question 5", "Question 6"]
    assert context.reset is False
    assert "Sibling secret" not in [turn.question for turn in context.turns]


@pytest.mark.parametrize("old_value", [(1, None), (0, "old-access")])
async def test_reset_boundary_does_not_reintroduce_older_mismatched_context(
    client, tenant, old_value
):
    from app.db.base import get_sessionmaker

    collection_id = await make_collection(client, tenant)
    actor = await owner_actor(tenant)
    principal = Principal("employee", ("all",))
    fingerprint = access_fingerprint(principal)
    old_generation, old_fingerprint = old_value
    async with get_sessionmaker()() as db:
        conversation = await add_conversation(db, tenant["id"], collection_id, actor.api_key_id)
        old = await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Old subject",
            old_fingerprint or fingerprint,
            generation=old_generation,
        )
        reset = await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Fresh subject",
            fingerprint,
            parent=old.id,
            reset=True,
        )
        current = await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Fresh follow-up",
            fingerprint,
            parent=reset.id,
        )
        await db.commit()
    async with get_sessionmaker()() as db:
        context = await load_conversation_context(
            db,
            request(),
            actor,
            collection_id,
            conversation.id,
            current.id,
            principal,
            get_settings(),
        )
    assert [turn.question for turn in context.turns] == ["Fresh subject", "Fresh follow-up"]
    assert context.reset is False


async def test_chain_without_boundary_keeps_only_four_most_recent_turns(client, tenant):
    from app.db.base import get_sessionmaker

    collection_id = await make_collection(client, tenant)
    actor = await owner_actor(tenant)
    principal = Principal("employee", ("all",))
    fingerprint = access_fingerprint(principal)
    async with get_sessionmaker()() as db:
        conversation = await add_conversation(db, tenant["id"], collection_id, actor.api_key_id)
        parent = None
        chain = []
        for index in range(1, 7):
            parent = await add_query(
                db,
                tenant["id"],
                collection_id,
                conversation.id,
                f"Question {index}",
                fingerprint,
                parent=parent.id if parent else None,
            )
            chain.append(parent)
        await db.commit()
    async with get_sessionmaker()() as db:
        context = await load_conversation_context(
            db,
            request(),
            actor,
            collection_id,
            conversation.id,
            chain[-1].id,
            principal,
            get_settings(),
        )
    assert [turn.question for turn in context.turns] == [
        "Question 3",
        "Question 4",
        "Question 5",
        "Question 6",
    ]


@pytest.mark.parametrize("mismatch", ["generation", "access"])
async def test_any_selected_version_or_access_mismatch_resets_all_context(client, tenant, mismatch):
    from app.db.base import get_sessionmaker

    collection_id = await make_collection(client, tenant)
    actor = await owner_actor(tenant)
    principal = Principal("employee", ("all",))
    fingerprint = access_fingerprint(principal)
    async with get_sessionmaker()() as db:
        conversation = await add_conversation(db, tenant["id"], collection_id, actor.api_key_id)
        first = await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Old question",
            "old" if mismatch == "access" else fingerprint,
            generation=1 if mismatch == "generation" else 0,
        )
        parent = await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Current follow-up",
            fingerprint,
            parent=first.id,
        )
        await db.commit()
    async with get_sessionmaker()() as db:
        context = await load_conversation_context(
            db,
            request(),
            actor,
            collection_id,
            conversation.id,
            parent.id,
            principal,
            get_settings(),
        )
    assert context.reset is True
    assert context.turns == () and context.references == ()


async def test_authorized_cited_references_win_cap_without_content_or_hidden_metadata(
    client, tenant
):
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk, Collection, Document, DocumentStatus, QueryCitation

    collection_id = await make_collection(client, tenant)
    actor = await owner_actor(tenant)
    principal = Principal("employee", ("all",))
    fingerprint = access_fingerprint(principal)
    async with get_sessionmaker()() as db:
        collection = await db.get(Collection, collection_id)
        conversation = await add_conversation(db, tenant["id"], collection_id, actor.api_key_id)
        parent = await add_query(
            db,
            tenant["id"],
            collection_id,
            conversation.id,
            "Which source did that use?",
            fingerprint,
            answer="Grounded answer [8] [9]",
        )
        public_doc = Document(
            collection_id=collection_id,
            filename="public.md",
            mime_type="text/markdown",
            size_bytes=10,
            sha256="a" * 64,
            status=DocumentStatus.READY,
        )
        secret_doc = Document(
            collection_id=collection_id,
            filename="restricted-secret.md",
            mime_type="text/markdown",
            size_bytes=10,
            sha256="b" * 64,
            status=DocumentStatus.READY,
        )
        db.add_all([public_doc, secret_doc])
        await db.flush()
        chunks = [
            Chunk(
                document_id=public_doc.id,
                chunk_index=index,
                content=f"passage content secret {index}",
                token_count=4,
                page_start=None,
                page_end=None,
                section_path=f"Section {index}",
                access_label="all",
                embedding=[0.0] * 1024,
            )
            for index in range(1, 9)
        ]
        restricted = Chunk(
            document_id=secret_doc.id,
            chunk_index=1,
            content="restricted fact 999",
            token_count=3,
            page_start=None,
            page_end=None,
            section_path="Restricted section",
            access_label="finance",
            embedding=[0.0] * 1024,
        )
        db.add_all([*chunks, restricted])
        await db.flush()
        db.add_all(
            [
                QueryCitation(
                    query_id=parent.id,
                    rank=index,
                    chunk_id=chunk.id,
                    score=1.0,
                    quotes=[{"start": 0, "end": 7}] if index == 7 else None,
                )
                for index, chunk in enumerate(chunks, start=1)
            ]
            + [
                QueryCitation(
                    query_id=parent.id,
                    rank=9,
                    chunk_id=restricted.id,
                    score=1.0,
                    quotes=[{"start": 0, "end": 10}],
                )
            ]
        )
        await db.commit()
        generation = collection.source_generation
    async with get_sessionmaker()() as db:
        context = await load_conversation_context(
            db,
            request(),
            actor,
            collection_id,
            conversation.id,
            parent.id,
            principal,
            get_settings(),
        )
    assert context.source_generation == generation
    assert len(context.references) == 6
    assert chunks[7].id in [reference.chunk_id for reference in context.references]
    assert restricted.id not in [reference.chunk_id for reference in context.references]
    serialized = str(context.prompt_payload())
    assert "restricted-secret" not in serialized
    assert "restricted fact" not in serialized
    assert "passage content secret" not in serialized
    assert "quotes" not in serialized and "access_label" not in serialized
