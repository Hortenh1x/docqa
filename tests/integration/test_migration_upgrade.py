"""Apply additive readiness migrations to a disposable legacy schema and sample rows."""

import asyncio
import uuid

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.db.base import get_engine


async def test_upgrade_from_0006_preserves_documents_and_queries(app_env):
    config = Config("alembic.ini")
    await asyncio.to_thread(command.downgrade, config, "0006")
    tid, cid, did, qid = (uuid.uuid4() for _ in range(4))
    try:
        async with get_engine().begin() as db:
            await db.execute(
                text("INSERT INTO tenants (id,name) VALUES (:id,'legacy')"), {"id": tid}
            )
            await db.execute(
                text("""INSERT INTO collections
                (id,tenant_id,name,slug,embedding_model,read_only,suggested_questions)
                VALUES (:id,:tid,'legacy','legacy','stub@1024',true,
                '[{"question":"legacy suggestion","min_role":"finance"}]'::jsonb)"""),
                {"id": cid, "tid": tid},
            )
            await db.execute(
                text("""INSERT INTO documents
                (id,collection_id,filename,mime_type,size_bytes,sha256,status)
                VALUES (:id,:cid,'legacy.md','text/markdown',42,:sha,'processing')"""),
                {"id": did, "cid": cid, "sha": "a" * 64},
            )
            await db.execute(
                text("""INSERT INTO queries (id,tenant_id,collection_id,question,answer,role)
                VALUES (:id,:tid,:cid,'legacy question','legacy answer','finance')"""),
                {"id": qid, "tid": tid, "cid": cid},
            )
        await asyncio.to_thread(command.upgrade, config, "head")
        async with get_engine().connect() as db:
            document = (
                await db.execute(
                    text(
                        "SELECT filename,status,ingestion_attempts,processing_token,"
                        "lease_expires_at "
                        "FROM documents WHERE id=:id"
                    ),
                    {"id": did},
                )
            ).one()
            assert tuple(document) == ("legacy.md", "processing", 0, None, None)
            coll = (
                await db.execute(
                    text(
                        "SELECT read_only,data_version,suggested_questions "
                        "FROM collections WHERE id=:id"
                    ),
                    {"id": cid},
                )
            ).one()
            assert tuple(coll) == (
                True,
                0,
                None,
            )  # unsafe legacy suggestions intentionally discarded
            question = (
                await db.execute(
                    text("SELECT question,answer,role FROM queries WHERE id=:id"), {"id": qid}
                )
            ).one()
            assert tuple(question) == ("legacy question", "legacy answer", "finance")
    finally:
        await asyncio.to_thread(command.upgrade, config, "head")
