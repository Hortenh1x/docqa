"""Full ingestion cycle on the stub embedding provider (Celery eager, no network)."""

import fitz
import pytest
from sqlalchemy import func, select

POLICY_MD = b"""# Vacation Policy

Employees receive 27 vacation days per year.

## Carryover

Unused days expire on March 31. Exceptions require HR approval.
"""


@pytest.fixture
async def collection_id(client, tenant) -> str:
    response = await client.post(
        "/v1/collections", json={"name": "Policies"}, headers=tenant["headers"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == "policies"
    assert body["embedding_model"] == "stub@1024"
    return body["id"]


def make_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "1. Introduction", fontsize=20)
    page.insert_text((72, 130), "This handbook covers travel rules.", fontsize=11)
    page2 = doc.new_page()
    page2.insert_text((72, 80), "2. Per-diems", fontsize=20)
    page2.insert_text((72, 130), "Daily allowances depend on the country.", fontsize=11)
    payload = doc.tobytes()
    doc.close()
    return payload


async def _chunk_rows(document_id: str):
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk

    async with get_sessionmaker()() as session:
        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        )
        return list(result.scalars().all())


async def test_markdown_upload_reaches_ready_with_chunks(client, tenant, collection_id):
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("policy.md", POLICY_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["id"]

    # celery eager: processing finished inside the request
    status = await client.get(f"/v1/documents/{document_id}", headers=tenant["headers"])
    body = status.json()
    assert body["status"] == "ready", body
    assert body["page_count"] is None  # markdown has no pages
    assert body["processed_at"] is not None
    assert body["error"] is None

    chunks = await _chunk_rows(document_id)
    assert chunks, "chunks must be stored"
    assert all(len(c.embedding) == 1024 for c in chunks)
    assert all(c.token_count > 0 for c in chunks)
    joined = " ".join(c.content for c in chunks)
    assert "27 vacation days" in joined
    # a short document merges into one chunk, whose breadcrumbs come from its first
    # section; exact nested-path behaviour is covered by the chunking unit tests
    carryover = [c for c in chunks if "expire on March 31" in c.content]
    assert carryover
    assert carryover[0].section_path is not None
    assert carryover[0].section_path.startswith("Vacation Policy")


async def test_pdf_upload_maps_pages(client, tenant, collection_id):
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("handbook.pdf", make_pdf(), "application/pdf")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["id"]

    body = (await client.get(f"/v1/documents/{document_id}", headers=tenant["headers"])).json()
    assert body["status"] == "ready", body
    assert body["page_count"] == 2

    chunks = await _chunk_rows(document_id)
    assert chunks
    assert chunks[0].page_start == 1
    assert max(c.page_end for c in chunks) == 2


async def test_duplicate_upload_is_409_with_existing_id(client, tenant, collection_id):
    first = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("policy.md", POLICY_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    duplicate = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("renamed.md", POLICY_MD, "text/markdown")},  # same bytes, new name
        headers=tenant["headers"],
    )
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["code"] == "duplicate_document"
    assert body["existing_document_id"] == first.json()["id"]


async def test_unsupported_type_is_415(client, tenant, collection_id):
    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("junk.bin", b"\x00\x01\x02\x03" * 100, "application/octet-stream")},
        headers=tenant["headers"],
    )
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_file_type"


async def test_broken_pdf_ends_as_failed(client, tenant, collection_id):
    """Magic bytes pass, parsing fails -> status failed with an error, no retries."""
    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("broken.pdf", b"%PDF-1.4 this is not really a pdf", "application/pdf")},
        headers=tenant["headers"],
    )
    assert response.status_code == 202
    document_id = response.json()["id"]

    body = (await client.get(f"/v1/documents/{document_id}", headers=tenant["headers"])).json()
    assert body["status"] == "failed"
    assert "parse error" in body["error"]
    assert await _chunk_rows(document_id) == []


async def test_delete_cascades_chunks(client, tenant, collection_id):
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk

    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("policy.md", POLICY_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    document_id = upload.json()["id"]
    assert await _chunk_rows(document_id)

    delete = await client.delete(f"/v1/documents/{document_id}", headers=tenant["headers"])
    assert delete.status_code == 204

    async with get_sessionmaker()() as session:
        remaining = await session.scalar(select(func.count()).select_from(Chunk))
    assert remaining == 0


async def test_document_file_served_inline(client, tenant, make_tenant, collection_id):
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("policy.md", POLICY_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    document_id = upload.json()["id"]

    response = await client.get(f"/v1/documents/{document_id}/file", headers=tenant["headers"])
    assert response.status_code == 200
    assert response.content == POLICY_MD
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].startswith("inline")

    # a foreign tenant gets the same 404 as for a document that never existed
    stranger = await make_tenant()
    foreign = await client.get(f"/v1/documents/{document_id}/file", headers=stranger["headers"])
    assert foreign.status_code == 404
