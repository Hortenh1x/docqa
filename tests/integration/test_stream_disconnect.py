import uuid

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import Query
from tests.integration.test_readiness_regressions import collection, upload


@pytest.mark.parametrize("frames", [1, 2])
async def test_closing_sse_after_meta_or_sources_records_once(client, tenant, frames):
    from app.api.v1.query import _sse_stream
    from app.generation.service import run_query

    cid = await collection(client, tenant)
    await upload(client, tenant, cid)
    events = run_query(tenant["id"], uuid.UUID(cid), "How many vacation days?", get_settings())
    stream = _sse_stream(events)
    for _ in range(frames):
        await anext(stream)
    await stream.aclose()
    async with get_sessionmaker()() as db:
        rows = (await db.scalars(select(Query).where(Query.collection_id == uuid.UUID(cid)))).all()
        assert len(rows) == 1
        assert rows[0].answer is None
