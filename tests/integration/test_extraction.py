"""Schemas → extraction → edit/delete/export, on the stub LLM and stub embeddings."""

import io

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from sqlalchemy import select

from app.ingestion.ocr.stub import STUB_TEXT_KEY

INVOICE_MD = b"""# Invoice INV-2026-042

Supplier: Acme Consulting Ltd
Customer: Kranich GmbH
Invoice number: INV-2026-042
Invoice date: 05.03.2026
Due date: 04.04.2026
Currency: EUR

## Positions

Consulting services: 1,000.00 EUR
Travel expenses: 250.00 EUR

Subtotal: 1,250.00 EUR
Tax: 237.50 EUR
Total: 1,487.50 EUR
"""

SCHEMA = {
    "name": "Invoice",
    "fields": [
        {"name": "invoice_number", "type": "string", "required": True},
        {"name": "invoice_date", "type": "date"},
        {"name": "due_date", "type": "date"},
        {"name": "supplier", "type": "string"},
        {"name": "currency", "type": "enum", "enum_values": ["EUR", "USD"]},
        {"name": "subtotal", "type": "number"},
        {"name": "tax", "type": "number"},
        {"name": "total", "type": "number", "required": True},
        {"name": "purchase_order", "type": "string"},
    ],
    "rules": ["abs(subtotal + tax - total) < 0.05", "due_date >= invoice_date"],
}


@pytest.fixture
async def collection_id(client, tenant) -> str:
    response = await client.post(
        "/v1/collections", json={"name": "Invoices"}, headers=tenant["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _upload(
    client, tenant, collection_id, name=b"invoice.md", payload=INVOICE_MD, mime="text/markdown"
):
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": (name.decode() if isinstance(name, bytes) else name, payload, mime)},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["id"]
    status = (await client.get(f"/v1/documents/{document_id}", headers=tenant["headers"])).json()
    assert status["status"] == "ready", status
    return document_id


async def _schema(client, tenant, **overrides):
    response = await client.post(
        "/v1/schemas", json={**SCHEMA, **overrides}, headers=tenant["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _extract(client, tenant, document_id, schema_id, **extra):
    response = await client.post(
        f"/v1/documents/{document_id}/extractions",
        json={"schema_id": schema_id, **extra},
        headers=tenant["headers"],
    )
    assert response.status_code == 202, response.text
    # eager celery: the run finished inside the request
    return (
        await client.get(f"/v1/extractions/{response.json()['id']}", headers=tenant["headers"])
    ).json()


async def test_schema_crud_and_templates(client, tenant, make_tenant):
    templates = await client.get("/v1/schemas/templates", headers=tenant["headers"])
    assert templates.status_code == 200
    assert {t["key"] for t in templates.json()} == {"invoice", "contract"}

    created = await _schema(client, tenant)
    assert created["fields"][0]["name"] == "invoice_number"
    assert created["rules"] == SCHEMA["rules"]

    duplicate = await client.post("/v1/schemas", json=SCHEMA, headers=tenant["headers"])
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "duplicate_schema"

    invalid = await client.post(
        "/v1/schemas",
        json={"name": "Bad", "fields": [{"name": "a"}], "rules": ["a == b"]},
        headers=tenant["headers"],
    )
    assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_schema"

    patched = await client.patch(
        f"/v1/schemas/{created['id']}",
        json={"name": "Supplier invoice", "rules": []},
        headers=tenant["headers"],
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Supplier invoice" and patched.json()["rules"] == []

    other = await make_tenant()
    assert (
        await client.get(f"/v1/schemas/{created['id']}", headers=other["headers"])
    ).status_code == 404
    assert (await client.get("/v1/schemas", headers=other["headers"])).json() == []

    deleted = await client.delete(f"/v1/schemas/{created['id']}", headers=tenant["headers"])
    assert deleted.status_code == 204
    assert (await client.get("/v1/schemas", headers=tenant["headers"])).json() == []


async def test_extraction_values_evidence_issues_and_export(client, tenant, collection_id):
    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant)
    extraction = await _extract(client, tenant, document_id, schema["id"])
    assert extraction["status"] == "ready", extraction
    assert extraction["model"] == "stub"
    assert extraction["prompt_tokens"] == 200

    fields = extraction["fields"]
    assert fields["invoice_number"]["value"] == "INV-2026-042"
    assert fields["invoice_date"]["value"] == "2026-03-05"
    assert fields["due_date"]["value"] == "2026-04-04"
    assert fields["currency"]["value"] == "EUR"
    assert fields["subtotal"]["value"] == 1250.0
    assert fields["tax"]["value"] == 237.5
    assert fields["total"]["value"] == 1487.5
    assert fields["purchase_order"] == {
        "value": None,
        "confidence": None,
        "evidence": None,
        "edited": False,
    }

    evidence = fields["total"]["evidence"]
    assert evidence["quote"] == "Total: 1,487.50 EUR"
    assert evidence["chunk_id"] > 0 and evidence["bbox"] is None
    assert fields["total"]["confidence"] == 0.75  # value rendered "1487.5" vs "1,487.50"
    assert fields["invoice_number"]["confidence"] == 0.9
    assert extraction["issues"] == []  # both rules hold

    listed = await client.get(f"/v1/documents/{document_id}/extractions", headers=tenant["headers"])
    assert [e["id"] for e in listed.json()] == [extraction["id"]]

    exported = await client.get(
        f"/v1/collections/{collection_id}/extractions",
        params={"schema_id": schema["id"], "format": "csv"},
        headers=tenant["headers"],
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    lines = exported.text.strip().splitlines()
    assert lines[0].startswith("document_id,filename,status,invoice_number,")
    assert "INV-2026-042" in lines[1] and "1487.5" in lines[1]

    as_json = await client.get(
        f"/v1/collections/{collection_id}/extractions",
        params={"schema_id": schema["id"]},
        headers=tenant["headers"],
    )
    assert as_json.json()["rows"][0]["values"]["total"] == 1487.5


async def test_edits_survive_reruns_until_forced(client, tenant, collection_id):
    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant)
    extraction = await _extract(client, tenant, document_id, schema["id"])

    patched = await client.patch(
        f"/v1/extractions/{extraction['id']}",
        json={"values": {"purchase_order": "PO-7"}, "clear": ["supplier"]},
        headers=tenant["headers"],
    )
    assert patched.status_code == 200, patched.text
    fields = patched.json()["fields"]
    assert fields["purchase_order"] == {
        "value": "PO-7",
        "confidence": 1.0,
        "edited": True,
        "evidence": None,
    }
    assert fields["supplier"]["value"] is None and fields["supplier"]["edited"] is True

    unknown = await client.patch(
        f"/v1/extractions/{extraction['id']}",
        json={"values": {"nope": 1}},
        headers=tenant["headers"],
    )
    assert unknown.status_code == 422

    rerun = await _extract(client, tenant, document_id, schema["id"])
    assert rerun["id"] == extraction["id"]
    assert rerun["fields"]["purchase_order"]["value"] == "PO-7"  # human edit kept
    assert rerun["fields"]["supplier"]["value"] is None
    assert rerun["fields"]["total"]["value"] == 1487.5

    forced = await _extract(client, tenant, document_id, schema["id"], force=True)
    assert forced["fields"]["purchase_order"]["value"] is None
    assert forced["fields"]["supplier"]["value"] == "Acme Consulting Ltd"

    deleted = await client.delete(f"/v1/extractions/{extraction['id']}", headers=tenant["headers"])
    assert deleted.status_code == 204
    assert (
        await client.get(f"/v1/extractions/{extraction['id']}", headers=tenant["headers"])
    ).status_code == 404


async def test_facts_chunk_is_indexed_and_removed_with_the_extraction(
    client, tenant, collection_id
):
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk

    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant, index_facts=True)
    extraction = await _extract(client, tenant, document_id, schema["id"])

    async with get_sessionmaker()() as session:
        facts = (
            await session.scalars(
                select(Chunk).where(
                    Chunk.document_id == document_id, Chunk.section_path == "Extracted fields"
                )
            )
        ).all()
    assert len(facts) == 1
    assert "invoice number: INV-2026-042" in facts[0].content
    assert "total: 1487.5" in facts[0].content
    assert facts[0].access_label == "all"

    # the facts are retrievable like any passage
    passages = await client.get(f"/v1/documents/{document_id}/passages", headers=tenant["headers"])
    assert any(p["section"] == "Extracted fields" for p in passages.json()["passages"])

    rerun = await _extract(client, tenant, document_id, schema["id"])
    assert rerun["status"] == "ready"
    async with get_sessionmaker()() as session:
        count = len(
            (
                await session.scalars(
                    select(Chunk.id).where(
                        Chunk.document_id == document_id, Chunk.section_path == "Extracted fields"
                    )
                )
            ).all()
        )
    assert count == 1  # replaced, not duplicated

    await client.delete(f"/v1/extractions/{extraction['id']}", headers=tenant["headers"])
    async with get_sessionmaker()() as session:
        remaining = (
            await session.scalars(
                select(Chunk.id).where(
                    Chunk.document_id == document_id, Chunk.section_path == "Extracted fields"
                )
            )
        ).all()
    assert remaining == []


async def test_extraction_from_a_scan_carries_boxes(client, tenant, collection_id):
    image = Image.new("RGB", (1200, 1600), "white")
    info = PngInfo()
    info.add_text(STUB_TEXT_KEY, "# Invoice\n\nInvoice number: SCAN-9\n\nTotal: 99.00 EUR")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", pnginfo=info)
    document_id = await _upload(
        client, tenant, collection_id, "scan.png", buffer.getvalue(), "image/png"
    )
    schema = await _schema(client, tenant)
    extraction = await _extract(client, tenant, document_id, schema["id"])
    total = extraction["fields"]["total"]
    assert total["value"] == 99.0
    assert total["evidence"]["page"] == 1
    # boxes live in the prepared-image space (here upscaled 2×), page_size says which
    bbox, size = total["evidence"]["bbox"], total["evidence"]["page_size"]
    assert size == [2400, 3200]
    assert 0 <= bbox[0] < bbox[2] <= size[0] and 0 <= bbox[1] < bbox[3] <= size[1]
    assert extraction["fields"]["invoice_number"]["value"] == "SCAN-9"


async def test_extraction_scope_and_readiness(client, tenant, make_tenant, collection_id):
    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant)
    other = await make_tenant()
    foreign = await client.post(
        f"/v1/documents/{document_id}/extractions",
        json={"schema_id": schema["id"]},
        headers=other["headers"],
    )
    assert foreign.status_code == 404
    extraction = await _extract(client, tenant, document_id, schema["id"])
    for method, path in (
        ("GET", f"/v1/extractions/{extraction['id']}"),
        ("PATCH", f"/v1/extractions/{extraction['id']}"),
        ("DELETE", f"/v1/extractions/{extraction['id']}"),
        ("GET", f"/v1/documents/{document_id}/extractions"),
    ):
        response = await client.request(
            method, path, headers=other["headers"], json={} if method == "PATCH" else None
        )
        assert response.status_code == 404, (method, path)


async def test_guest_cannot_read_owner_extraction_data(client, tenant, collection_id, monkeypatch):
    from app.config import get_settings

    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant)
    extraction = await _extract(client, tenant, document_id, schema["id"])
    settings = get_settings()
    monkeypatch.setattr(settings, "accounts_enabled", True)
    monkeypatch.setattr(settings, "public_tenant_id", tenant["id"])
    for path in (
        "/v1/schemas",
        f"/v1/schemas/{schema['id']}",
        f"/v1/extractions/{extraction['id']}",
        f"/v1/documents/{document_id}/extractions",
    ):
        response = await client.get(path)
        assert response.status_code == 404, (path, response.text)


async def test_edit_invalidates_indexed_facts(client, tenant, collection_id):
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk

    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant, index_facts=True)
    extraction = await _extract(client, tenant, document_id, schema["id"])
    response = await client.patch(
        f"/v1/extractions/{extraction['id']}",
        json={"values": {"total": 99}},
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    async with get_sessionmaker()() as session:
        facts = await session.scalar(
            select(Chunk).where(
                Chunk.document_id == document_id, Chunk.section_path == "Extracted fields"
            )
        )
    assert facts is None  # outdated values must not remain answerable
    rerun = await _extract(client, tenant, document_id, schema["id"])
    assert rerun["fields"]["total"]["value"] == 99
    async with get_sessionmaker()() as session:
        facts = await session.scalar(
            select(Chunk).where(
                Chunk.document_id == document_id, Chunk.section_path == "Extracted fields"
            )
        )
        assert "total: 99" in facts.content


async def test_failed_reindex_does_not_orphan_old_facts(client, tenant, collection_id, monkeypatch):
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk
    from app.embeddings.base import EmbeddingError
    from app.extraction import service

    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant, index_facts=True)
    extraction = await _extract(client, tenant, document_id, schema["id"])

    class Unavailable:
        async def embed(self, texts):
            raise EmbeddingError("offline")

    monkeypatch.setattr(service, "get_embedding_provider", lambda settings: Unavailable())
    await _extract(client, tenant, document_id, schema["id"])
    response = await client.delete(f"/v1/extractions/{extraction['id']}", headers=tenant["headers"])
    assert response.status_code == 204
    async with get_sessionmaker()() as session:
        facts = await session.scalar(
            select(Chunk).where(
                Chunk.document_id == document_id, Chunk.section_path == "Extracted fields"
            )
        )
    assert facts is None


async def test_recovery_republishes_pending_and_expires_worker_claims(
    client, tenant, collection_id, monkeypatch
):
    import uuid
    from datetime import UTC, datetime, timedelta

    from app.db.base import get_sessionmaker
    from app.db.models import Extraction
    from app.extraction import tasks

    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant)
    extraction = await _extract(client, tenant, document_id, schema["id"])
    extraction_id = uuid.UUID(extraction["id"])
    async with get_sessionmaker()() as session:
        row = await session.get(Extraction, extraction_id)
        row.status = "processing"
        row.processing_token = uuid.uuid4()
        row.updated_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()
    recovery = getattr(tasks, "recover_extractions", None)
    assert recovery is not None, "extractions need durable recovery"
    recovery()
    response = await client.get(f"/v1/extractions/{extraction_id}", headers=tenant["headers"])
    assert response.json()["status"] == "failed"
    async with get_sessionmaker()() as session:
        row = await session.get(Extraction, extraction_id)
        row.status = "pending"
        row.updated_at = datetime.now(UTC) - timedelta(minutes=2)
        await session.commit()
    recovery()
    response = await client.get(f"/v1/extractions/{extraction_id}", headers=tenant["headers"])
    assert response.json()["status"] == "ready"


@pytest.mark.parametrize("access_label", ["all", "finance"])
async def test_heading_free_text_is_extracted_and_keeps_access_label(
    client, tenant, collection_id, access_label
):
    from sqlalchemy import update

    from app.db.base import get_sessionmaker
    from app.db.models import Chunk

    document_id = await _upload(
        client,
        tenant,
        collection_id,
        "plain.txt",
        b"Invoice number: PLAIN-42\nTotal: 42.00 EUR\n",
        "text/plain",
    )
    async with get_sessionmaker()() as session:
        chunks = list(
            (await session.scalars(select(Chunk).where(Chunk.document_id == document_id))).all()
        )
        assert chunks and all(chunk.section_path is None for chunk in chunks)
        # Exercise labels independently of parser heading/access-marker heuristics.
        await session.execute(
            update(Chunk).where(Chunk.document_id == document_id).values(access_label=access_label)
        )
        await session.commit()
    schema = await _schema(client, tenant, index_facts=True)
    extraction = await _extract(client, tenant, document_id, schema["id"])
    assert extraction["fields"]["invoice_number"]["value"] == "PLAIN-42"
    assert extraction["fields"]["total"]["value"] == 42
    async with get_sessionmaker()() as session:
        facts = await session.scalar(
            select(Chunk).where(
                Chunk.document_id == document_id, Chunk.section_path == "Extracted fields"
            )
        )
        assert facts is not None and facts.access_label == access_label


async def test_facts_finalization_already_holds_collection_lock(
    client, tenant, collection_id, monkeypatch
):
    import uuid

    from sqlalchemy.exc import OperationalError

    from app.db.models import Collection
    from app.db.sync import sync_session
    from app.extraction import service

    document_id = await _upload(client, tenant, collection_id)
    schema = await _schema(client, tenant, index_facts=True)
    original = service._replace_facts
    collection_was_locked = []

    def probe(*args, **kwargs):
        # A competing document deletion acquires this lock first. Finalization
        # must already hold it before reaching the facts write transaction.
        try:
            with sync_session() as competing:
                competing.scalar(
                    select(Collection)
                    .where(Collection.id == uuid.UUID(collection_id))
                    .with_for_update(nowait=True)
                )
        except OperationalError as exc:
            assert exc.orig.sqlstate == "55P03"  # lock_not_available
            collection_was_locked.append(True)
        else:
            collection_was_locked.append(False)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_replace_facts", probe)
    result = await _extract(client, tenant, document_id, schema["id"])
    assert result["status"] == "ready"
    assert collection_was_locked == [True]
