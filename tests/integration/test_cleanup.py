import uuid

import pytest
from sqlalchemy import func, select

from app.db.base import get_sessionmaker
from app.db.models import Collection, Query
from tests.integration.test_readiness_regressions import collection, upload


async def test_wipe_removes_questions_and_cached_answers(client, tenant):
    from app.cli import wipe_collection
    from app.core.redis import get_redis

    cid = await collection(client, tenant)
    await upload(client, tenant, cid)
    response = await client.post(
        "/v1/query",
        json={"collection_id": cid, "question": "How many vacation days?", "stream": False},
        headers={**tenant["headers"], "Idempotency-Key": "private-question"},
    )
    assert response.status_code == 200
    async with get_sessionmaker()() as db:
        before = await db.scalar(select(Collection.source_generation).where(Collection.id == cid))
    await wipe_collection(uuid.UUID(cid))
    async with get_sessionmaker()() as db:
        assert (
            await db.scalar(
                select(func.count(Query.id)).where(Query.collection_id == uuid.UUID(cid))
            )
            == 0
        )
        after = await db.scalar(select(Collection.source_generation).where(Collection.id == cid))
        assert after == before + 1
    assert not [key async for key in get_redis().scan_iter(f"idem:{tenant['id']}:*")]


async def test_empty_wipe_preserves_source_generation(client, tenant):
    from app.cli import wipe_collection
    from app.db.models import Collection

    cid = await collection(client, tenant)
    await wipe_collection(uuid.UUID(cid))
    async with get_sessionmaker()() as db:
        result = await db.get(Collection, uuid.UUID(cid))
        assert result is not None
        assert result.data_version == 1
        assert result.source_generation == 0


@pytest.mark.parametrize("operation", ["delete", "wipe"])
async def test_chunk_store_and_cleanup_share_collection_then_document_lock_order(
    client, tenant, monkeypatch, operation
):
    import asyncio
    import threading

    from sqlalchemy.orm import Session

    from app.cli import wipe_collection
    from app.db.models import Document, DocumentStatus
    from app.ingestion.chunking import ChunkDraft
    from app.ingestion.parsers import ParsedDocument, ParsedPage
    from app.ingestion.tasks import _store_chunks

    cid = await collection(client, tenant)
    uploaded = await upload(client, tenant, cid)
    did = uuid.UUID(uploaded.json()["id"])
    token = uuid.uuid4()
    async with get_sessionmaker()() as db:
        document = await db.get(Document, did)
        document.status = DocumentStatus.PROCESSING
        document.processing_token = token
        await db.commit()

    collection_locked = threading.Event()
    resume_worker = threading.Event()
    original_get = Session.get

    def pause_after_collection_lock(self, entity, ident, **kwargs):
        value = original_get(self, entity, ident, **kwargs)
        if entity is Collection and kwargs.get("with_for_update"):
            collection_locked.set()
            assert resume_worker.wait(10)
        return value

    monkeypatch.setattr(Session, "get", pause_after_collection_lock)
    parsed = ParsedDocument([ParsedPage(number=None, text="Replacement")])
    drafts = [ChunkDraft(0, "Replacement", 1, None, None, None)]
    storing = asyncio.create_task(
        asyncio.to_thread(_store_chunks, did, parsed, drafts, [[0.0] * 1024], token)
    )
    assert await asyncio.to_thread(collection_locked.wait, 10)

    async def cleanup():
        if operation == "wipe":
            await wipe_collection(uuid.UUID(cid))
        else:
            response = await client.delete(f"/v1/documents/{did}", headers=tenant["headers"])
            assert response.status_code == 204, response.text

    removing = asyncio.create_task(cleanup())
    await asyncio.sleep(0.1)  # cleanup is now waiting behind the worker's collection lock
    resume_worker.set()
    assert await asyncio.wait_for(storing, 10) is True
    await asyncio.wait_for(removing, 10)
    async with get_sessionmaker()() as db:
        assert await db.get(Document, did) is None
        result = await db.get(Collection, uuid.UUID(cid))
        assert result is not None and result.source_generation == 3


async def test_wipe_fences_an_answer_already_in_flight(client, tenant, monkeypatch):
    import asyncio

    from app.cli import wipe_collection
    from app.core.redis import get_redis
    from app.generation import service
    from app.generation.llm import TextDelta

    cid = await collection(client, tenant)
    await upload(client, tenant, cid)
    started, resume = asyncio.Event(), asyncio.Event()

    class SlowLLM:
        model_name = "stub"

        async def stream(self, system, user):
            started.set()
            await resume.wait()
            yield TextDelta("A private answer to remove [1].")

    monkeypatch.setattr(service, "get_llm_provider", lambda _: SlowLLM())
    request = asyncio.create_task(
        client.post(
            "/v1/query",
            json={"collection_id": cid, "question": "How many vacation days?", "stream": False},
            headers={**tenant["headers"], "Idempotency-Key": "in-flight-cleanup"},
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        await wipe_collection(uuid.UUID(cid))
    finally:
        resume.set()
        await request
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(func.count(Query.id))) == 0
    assert not [key async for key in get_redis().scan_iter(f"idem:{tenant['id']}:*")]


async def test_replay_checks_cleanup_version_before_returning_cached_body(tenant):
    import pytest

    from app.core.errors import IdempotencyKeyReusedError
    from app.core.idempotency import run_idempotent

    async def handler():
        return 200, {"answer": "private"}

    async def invalid():
        return False

    await run_idempotent(tenant["id"], "stale", handler, "fp")
    with pytest.raises(IdempotencyKeyReusedError):
        await run_idempotent(tenant["id"], "stale", handler, "fp", invalid)


@pytest.mark.parametrize("operation", ["delete", "wipe"])
async def test_cleanup_cannot_be_undone_by_an_in_flight_suggestion(
    client, tenant, monkeypatch, operation
):
    import asyncio
    import threading

    from app.cli import wipe_collection
    from app.config import get_settings
    from app.db.models import Collection
    from app.generation import tasks

    cid = await collection(client, tenant)
    response = await upload(client, tenant, cid)
    did = response.json()["id"]
    started, resume = threading.Event(), threading.Event()
    monkeypatch.setattr(get_settings(), "suggested_questions_enabled", True)

    async def paused_draft(settings, excerpts):
        started.set()
        assert await asyncio.to_thread(resume.wait, 10)
        return ["An old question"], [[0.0] * 1024]

    monkeypatch.setattr(tasks, "draft_candidates", paused_draft)
    monkeypatch.setattr(
        tasks,
        "rank_questions",
        lambda *args: [{"question": "An old question", "min_role": "employee"}],
    )
    monkeypatch.setattr(tasks.suggest_questions, "delay", lambda *args: None)
    task = asyncio.create_task(asyncio.to_thread(tasks.suggest_questions.run, cid))
    try:
        assert await asyncio.to_thread(started.wait, 10)
        if operation == "wipe":
            await wipe_collection(uuid.UUID(cid))
        else:
            deleted = await client.delete(f"/v1/documents/{did}", headers=tenant["headers"])
            assert deleted.status_code == 204
    finally:
        resume.set()
        await task
    async with get_sessionmaker()() as db:
        result = await db.get(Collection, uuid.UUID(cid))
        assert result is not None
        assert result.suggested_questions is None
