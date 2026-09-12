"""Background work uses the actual trigger's durable owner/network identity."""

import pytest

from app.billing.context import BillingActor
from app.billing.errors import BudgetUnavailableError
from app.billing.jobs import collection_billing
from app.db.base import get_sessionmaker
from app.db.models import Collection, Document, User
from tests.integration.test_billing import account as account
from tests.integration.test_billing import budget_browser as budget_browser
from tests.integration.test_billing import budget_config as budget_config


async def test_suggestion_identity_comes_from_trigger_not_latest_upload(account):
    async with get_sessionmaker()() as db:
        owner = await db.get(User, account)
        collection = Collection(
            tenant_id=owner.tenant_id,
            name="Private",
            slug="private",
            embedding_model="stub",
            suggestion_billing_user_id=owner.id,
            suggestion_billing_ip_digest="deletion-ip",
            data_version=7,
        )
        db.add(collection)
        await db.flush()
        db.add(
            Document(
                collection_id=collection.id,
                filename="test.txt",
                mime_type="text/plain",
                size_bytes=1,
                sha256="a" * 64,
                billing_user_id=owner.id,
                billing_ip_digest="old-upload-ip",
            )
        )
        await db.commit()
        cid = collection.id
    assert collection_billing(cid, data_version=7, expected_revision=0) == (
        BillingActor("deletion-ip", account),
        False,
    )
    with pytest.raises(BudgetUnavailableError):
        collection_billing(cid, data_version=6)


async def test_suggestion_cannot_guess_a_payer_when_trigger_is_missing(account):
    async with get_sessionmaker()() as db:
        owner = await db.get(User, account)
        collection = Collection(
            tenant_id=owner.tenant_id, name="Private", slug="private", embedding_model="stub"
        )
        db.add(collection)
        await db.commit()
        cid = collection.id
    with pytest.raises(BudgetUnavailableError):
        collection_billing(cid)


async def test_queued_old_suggestion_trigger_never_adopts_newer_payer(account, monkeypatch):
    from app.config import get_settings
    from app.generation import tasks

    async with get_sessionmaker()() as db:
        owner = await db.get(User, account)
        collection = Collection(
            tenant_id=owner.tenant_id,
            name="Private",
            slug="private",
            embedding_model="stub",
            suggestion_billing_user_id=account,
            suggestion_billing_ip_digest="newer-ip",
            suggestion_revision=2,
        )
        db.add(collection)
        await db.commit()
        cid = str(collection.id)
    monkeypatch.setattr(get_settings(), "suggested_questions_enabled", True)

    def forbidden(*args, **kwargs):
        pytest.fail("Superseded job must stop before loading excerpts or calling providers")

    monkeypatch.setattr(tasks, "sample_excerpts", forbidden)
    tasks.suggest_questions.run(cid, 1)


async def test_owner_can_retry_failed_original_with_current_network_identity(
    budget_browser, account, monkeypatch, make_tenant
):
    import hashlib
    import uuid

    from app.config import get_settings
    from app.ingestion.tasks import ingest_document
    from app.storage import get_storage

    client, payer, _ = budget_browser
    content = b"# Private handbook\n\nVacation is 27 days."
    digest = hashlib.sha256(content).hexdigest()
    async with get_sessionmaker()() as db:
        user = await db.get(User, account)
        user.email_verified = True
        collection = Collection(
            tenant_id=user.tenant_id,
            name="Personal",
            slug="personal",
            embedding_model=get_settings().embedding_model_id,
        )
        db.add(collection)
        await db.flush()
        document = Document(
            collection_id=collection.id,
            filename="handbook.md",
            mime_type="text/markdown",
            sha256=digest,
            size_bytes=len(content),
            status="failed",
            ingestion_attempts=4,
            error="quota_exceeded",
            billing_user_id=account,
            billing_ip_digest="old-ip",
        )
        db.add(document)
        await db.commit()
        did, tid = document.id, user.tenant_id
    source = get_settings().storage_dir / f"fixture-{uuid.uuid4()}"
    source.write_bytes(content)
    get_storage().store(str(tid), digest, ".md", source)
    stranger = await make_tenant()
    assert (
        await client.post(f"/v1/documents/{did}/reprocess", headers=stranger["headers"], json={})
    ).status_code == 404
    session = (await client.get("/v1/auth/session")).json()
    login = await client.post(
        "/v1/auth/login",
        json={"email": "quota@example.com", "password": "correct horse sunset lentils 9373"},
        headers={"Origin": "https://ui.test", "X-CSRF-Token": session["csrf_token"]},
    )
    assert login.status_code == 200
    headers = {"Origin": "https://ui.test", "X-CSRF-Token": login.json()["csrf_token"]}
    scheduled = []
    monkeypatch.setattr(ingest_document, "delay", lambda did: scheduled.append(did))
    response = await client.post(f"/v1/documents/{did}/reprocess", headers=headers, json={})
    assert response.status_code == 202, response.text
    assert scheduled == [str(did)]
    async with get_sessionmaker()() as db:
        document = await db.get(Document, did)
        assert document.status == "pending" and document.ingestion_attempts == 0
        assert document.billing_user_id == account
        assert document.billing_ip_digest == payer.ip_digest
    assert (await client.get(f"/v1/documents/{did}/file")).content == content
    repeat = await client.post(f"/v1/documents/{did}/reprocess", headers=headers, json={})
    assert repeat.status_code == 409
