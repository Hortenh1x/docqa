import asyncio

from sqlalchemy import func, select

SAME_BYTES = b"# Same\n\nIdentical content uploaded twice concurrently.\n"


async def test_concurrent_identical_uploads_yield_exactly_one_document(client, tenant):
    """The unique constraint — not a SELECT-before-INSERT — must win the race."""
    from app.db.base import get_sessionmaker
    from app.db.models import Document

    created = await client.post("/v1/collections", json={"name": "Race"}, headers=tenant["headers"])
    collection_id = created.json()["id"]
    url = f"/v1/collections/{collection_id}/documents"

    async def upload(name: str):
        return await client.post(
            url, files={"file": (name, SAME_BYTES, "text/markdown")}, headers=tenant["headers"]
        )

    first, second = await asyncio.gather(upload("a.md"), upload("b.md"))
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [202, 409], (first.text, second.text)

    winner = first if first.status_code == 202 else second
    loser = second if first.status_code == 202 else first
    assert loser.json()["existing_document_id"] == winner.json()["id"]

    async with get_sessionmaker()() as session:
        count = (
            await session.execute(
                select(func.count(Document.id)).where(Document.collection_id == collection_id)
            )
        ).scalar_one()
    assert count == 1
