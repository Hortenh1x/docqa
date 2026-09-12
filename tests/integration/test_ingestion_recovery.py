"""Durable ingestion acceptance, retry and ownership regressions."""

import uuid

from app.db.base import get_sessionmaker
from app.db.models import Document
from tests.integration.test_readiness_regressions import collection, upload


async def test_broker_outage_preserves_accepted_upload(client, tenant, monkeypatch):
    from app.ingestion.tasks import ingest_document

    cid = await collection(client, tenant)
    with monkeypatch.context() as patch:

        def unavailable(*args, **kwargs):
            raise ConnectionError("synthetic broker outage")

        patch.setattr(ingest_document, "delay", unavailable)
        accepted = await upload(client, tenant, cid, key="durable")
    assert accepted.status_code == 202
    doc_id = accepted.json()["id"]
    from app.ingestion.tasks import recover_ingestion

    recover_ingestion()
    status = await client.get(f"/v1/documents/{doc_id}", headers=tenant["headers"])
    assert status.json()["status"] == "ready"
    replay = await upload(client, tenant, cid, key="durable")
    assert replay.json() == accepted.json()


async def test_transient_embeddings_retry_reaches_ready(client, tenant, monkeypatch):
    from app.embeddings.base import EmbeddingError
    from app.ingestion import tasks

    cid = await collection(client, tenant)
    with monkeypatch.context() as patch:
        patch.setattr(tasks.ingest_document, "delay", lambda *_: None)
        doc_id = (await upload(client, tenant, cid)).json()["id"]
    provider = tasks.get_embedding_provider(tasks.get_settings())
    real_embed = provider.embed
    calls = 0

    async def flaky(texts):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise EmbeddingError("synthetic transient")
        return await real_embed(texts)

    monkeypatch.setattr(provider, "embed", flaky)
    monkeypatch.setattr(tasks, "get_embedding_provider", lambda _: provider)
    tasks.ingest_document.apply(args=[doc_id], throw=False)
    async with get_sessionmaker()() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        assert doc.status == "ready"
        assert doc.ingestion_attempts == 2
    assert calls == 2


async def test_exhausted_retry_is_terminal_and_duplicate_delivery_is_noop(
    client, tenant, monkeypatch
):
    from app.embeddings.base import EmbeddingError
    from app.ingestion import tasks

    monkeypatch.setattr(tasks.celery_app.conf, "task_eager_propagates", False)
    cid = await collection(client, tenant)
    with monkeypatch.context() as patch:
        patch.setattr(tasks.ingest_document, "delay", lambda *_: None)
        doc_id = (await upload(client, tenant, cid)).json()["id"]
    provider = tasks.get_embedding_provider(tasks.get_settings())
    calls = 0

    async def unavailable(texts):
        nonlocal calls
        calls += 1
        raise EmbeddingError("synthetic persistent failure")

    monkeypatch.setattr(provider, "embed", unavailable)
    monkeypatch.setattr(tasks, "get_embedding_provider", lambda _: provider)
    tasks.ingest_document.apply(args=[doc_id], throw=False)
    tasks.ingest_document.apply(args=[doc_id], throw=False)
    async with get_sessionmaker()() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        assert doc.status == "failed"
        assert doc.ingestion_attempts == 4
    assert calls == 4


async def test_obsolete_worker_cannot_replace_chunks_or_mark_new_owner_failed(client, tenant):
    from sqlalchemy import func, select

    from app.db.models import Chunk
    from app.ingestion import tasks
    from app.ingestion.parsers import ParsedDocument

    cid = await collection(client, tenant)
    doc_id = uuid.UUID((await upload(client, tenant, cid)).json()["id"])
    token = uuid.uuid4()
    async with get_sessionmaker()() as db:
        document = await db.get(Document, doc_id)
        document.processing_token = token
        document.status = "processing"
        await db.commit()
    obsolete = uuid.uuid4()
    assert tasks._store_chunks(doc_id, ParsedDocument(pages=[]), [], [], obsolete) is False
    tasks._mark_failed(doc_id, "obsolete failure", obsolete)
    async with get_sessionmaker()() as db:
        document = await db.get(Document, doc_id)
        assert document.processing_token == token and document.status == "processing"
        assert await db.scalar(select(func.count(Chunk.id)).where(Chunk.document_id == doc_id)) == 1
