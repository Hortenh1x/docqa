"""Explicit public corpus publication and a permanent private-data cleanup boundary."""

import uuid

import pytest
from sqlalchemy import select

from app.db.base import get_sessionmaker
from app.db.models import Collection, Document, Tenant
from tests.integration.test_readiness_regressions import collection, upload


async def test_scheduled_wipe_never_removes_personal_originals(client, tenant):
    from app.cli import wipe_collection

    cid = uuid.UUID(await collection(client, tenant))
    document_id = uuid.UUID((await upload(client, tenant, str(cid))).json()["id"])
    async with get_sessionmaker()() as db:
        owner = await db.get(Tenant, tenant["id"])
        owner.kind = "personal"
        await db.commit()
    with pytest.raises(SystemExit):
        await wipe_collection(cid)
    async with get_sessionmaker()() as db:
        assert await db.get(Document, document_id) is not None


async def test_publication_is_explicit_configured_service_only(client, tenant, monkeypatch):
    from app.cli import publish_collection, wipe_collection
    from app.config import get_settings

    cid = uuid.UUID(await collection(client, tenant))
    with pytest.raises(SystemExit):
        await publish_collection(cid)
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(tenant["id"]))
    get_settings.cache_clear()
    try:
        await publish_collection(cid)
        async with get_sessionmaker()() as db:
            row = await db.get(Collection, cid)
            assert row.is_public and row.read_only
        with pytest.raises(SystemExit):
            await wipe_collection(cid)
        await publish_collection(cid, private=True)
        async with get_sessionmaker()() as db:
            row = await db.get(Collection, cid)
            assert not row.is_public and row.read_only
            owner = await db.scalar(select(Tenant).where(Tenant.id == tenant["id"]))
            owner.kind = "personal"
            await db.commit()
        with pytest.raises(SystemExit):
            await publish_collection(cid)
    finally:
        get_settings.cache_clear()
