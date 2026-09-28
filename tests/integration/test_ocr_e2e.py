"""Scans and photos through the whole pipeline (stub OCR, stub embeddings, eager Celery)."""

import io

import fitz
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from sqlalchemy import select

from app.ingestion.ocr.stub import STUB_TEXT_KEY


def _png(text: str, size=(1200, 1600)) -> bytes:
    image = Image.new("RGB", size, "white")
    info = PngInfo()
    info.add_text(STUB_TEXT_KEY, text)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", pnginfo=info)
    return buffer.getvalue()


def _tiff(frames: int) -> bytes:
    images = [Image.new("L", (400, 300), 255) for _ in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="TIFF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


@pytest.fixture
async def collection_id(client, tenant) -> str:
    response = await client.post(
        "/v1/collections", json={"name": "Scans"}, headers=tenant["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _chunks(document_id: str) -> list[str]:
    from app.db.base import get_sessionmaker
    from app.db.models import Chunk

    async with get_sessionmaker()() as session:
        rows = await session.scalars(
            select(Chunk.content)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )
        return list(rows)


async def test_photo_upload_is_recognised_chunked_and_searchable(client, tenant, collection_id):
    payload = _png(
        "# Expense Policy\n\nAccess: finance only\n\nReceipts above 25 EUR are mandatory."
    )
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("receipt.png", payload, "image/png")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["id"]

    body = (await client.get(f"/v1/documents/{document_id}", headers=tenant["headers"])).json()
    assert body["status"] == "ready", body
    assert body["mime_type"] == "image/png"
    assert body["page_count"] == 1
    assert body["ocr_pages"] == 1
    assert body["ocr_confidence"] == 95.0
    assert body["searchable_pdf"] is True
    assert body["access_labels"] == ["finance"]  # the marker survived OCR → chunker

    text = "\n".join(await _chunks(document_id))
    assert "Receipts above 25 EUR are mandatory." in text

    original = await client.get(
        f"/v1/documents/{document_id}/file", headers=tenant["headers"], params={"role": "finance"}
    )
    assert original.status_code == 200
    assert original.headers["content-type"].startswith("image/png")

    searchable = await client.get(
        f"/v1/documents/{document_id}/file",
        headers=tenant["headers"],
        params={"role": "finance", "variant": "searchable"},
    )
    assert searchable.status_code == 200
    assert searchable.headers["content-type"].startswith("application/pdf")
    with fitz.open(stream=searchable.content, filetype="pdf") as pdf:
        assert "Receipts above 25 EUR" in pdf[0].get_text()

    # the derived copy goes with the document
    deleted = await client.delete(f"/v1/documents/{document_id}", headers=tenant["headers"])
    assert deleted.status_code == 204


async def test_multi_frame_tiff_pages_and_ocr_page_cap(client, tenant, collection_id, monkeypatch):
    from app.config import get_settings

    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("scan.tiff", _tiff(3), "image/tiff")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202, upload.text
    body = (
        await client.get(f"/v1/documents/{upload.json()['id']}", headers=tenant["headers"])
    ).json()
    # blank frames: recognised but empty — still a ready document with three pages
    assert body["status"] == "ready", body
    assert body["page_count"] == 3 and body["ocr_pages"] == 3
    assert body["ocr_confidence"] is None
    assert body["searchable_pdf"] is False  # nothing to lay over

    monkeypatch.setenv("OCR_MAX_PAGES", "2")
    get_settings.cache_clear()
    try:
        rejected = await client.post(
            f"/v1/collections/{collection_id}/documents",
            files={"file": ("big.tiff", _tiff(3), "image/tiff")},
            headers=tenant["headers"],
        )
    finally:
        get_settings.cache_clear()
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "too_many_pages"


async def test_unsupported_type_message_lists_images(client, tenant, collection_id):
    response = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("x.bin", b"\x00\x01\x02garbage", "application/octet-stream")},
        headers=tenant["headers"],
    )
    assert response.status_code == 415
    assert "HEIC" in response.json()["detail"]
