"""Negative HTTP boundaries on disposable tenants; no external provider requests."""

import uuid

import pytest
from sqlalchemy import select

from app.db.base import get_sessionmaker
from app.db.models import Collection, Document
from tests.integration.test_ingestion_e2e import make_pdf
from tests.integration.test_readiness_regressions import CONTENT, collection, upload


@pytest.mark.parametrize("question", ["", "x" * 4001, {"$ne": None}])
async def test_query_schema_rejects_invalid_inputs(client, tenant, question):
    cid = await collection(client, tenant)
    response = await client.post(
        "/v1/query",
        json={"collection_id": cid, "question": question, "stream": False},
        headers=tenant["headers"],
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_extra_privileged_fields_do_not_change_collection_authority(
    client, tenant, make_tenant
):
    stranger = await make_tenant()
    forged_id = str(uuid.uuid4())
    name = "Policy'; DROP TABLE collections; --"
    response = await client.post(
        "/v1/collections",
        json={
            "name": name,
            "tenant_id": str(stranger["id"]),
            "id": forged_id,
            "read_only": True,
            "embedding_model": "forged",
        },
        headers=tenant["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] != forged_id
    assert body["name"] == name
    assert body["read_only"] is False
    assert body["embedding_model"] == "stub@1024"
    async with get_sessionmaker()() as db:
        row = await db.get(Collection, uuid.UUID(body["id"]))
        assert row.tenant_id == tenant["id"]
    assert (await client.get("/v1/collections", headers=stranger["headers"])).json() == []


@pytest.mark.parametrize(
    ("filename", "content", "mime"),
    [
        ("empty.md", b"", "text/markdown"),
        ("pretend.pdf", b"not a PDF", "application/pdf"),
        ("page.html", b"<script>window.xss=true</script>", "text/html"),
        ("broken.md", b"\xff\xfe\x00", "text/markdown"),
    ],
)
async def test_rejected_upload_leaves_no_row_or_temp_file(client, tenant, filename, content, mime):
    from app.config import get_settings

    cid = await collection(client, tenant)
    response = await client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": (filename, content, mime)},
        headers=tenant["headers"],
    )
    assert response.status_code == 415
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(Document.id)) is None
    assert list((get_settings().storage_dir / "tmp").iterdir()) == []


async def test_pdf_page_limit_rejects_before_ingestion(client, tenant, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_pages", 1)
    cid = await collection(client, tenant)
    response = await client.post(
        f"/v1/collections/{cid}/documents",
        files={"file": ("two-pages.pdf", make_pdf(), "application/pdf")},
        headers=tenant["headers"],
    )
    assert response.status_code == 422
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(Document.id)) is None


async def test_original_filename_is_header_safe_and_does_not_select_storage_path(client, tenant):
    cid = await collection(client, tenant)
    did = (await upload(client, tenant, cid)).json()["id"]
    # An existing/imported row may carry characters normalized by a multipart client.
    async with get_sessionmaker()() as db:
        row = await db.get(Document, uuid.UUID(did))
        row.filename = '../../bericht-ä"\\\r\nX-Injected: true.md'
        await db.commit()
    response = await client.get(f"/v1/documents/{did}/file", headers=tenant["headers"])
    assert response.status_code == 200
    assert response.content == CONTENT
    header = response.headers["content-disposition"]
    assert "\r" not in header and "\n" not in header
    assert "%0D%0A" in header and "%C3%A4" in header
    assert "x-injected" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_upload_does_not_import_a_user_supplied_url(client, tenant):
    cid = await collection(client, tenant)
    response = await client.post(
        f"/v1/collections/{cid}/documents",
        json={"url": "http://127.0.0.1:9/private"},
        headers=tenant["headers"],
    )
    assert response.status_code == 400
