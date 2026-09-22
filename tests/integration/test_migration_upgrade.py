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


async def test_upgrade_from_0013_backfills_only_proven_account_history(app_env):
    config = Config("alembic.ini")
    await asyncio.to_thread(command.downgrade, config, "0013")
    service_tid, personal_tid, cid, user_id, owned_qid, guest_qid = (uuid.uuid4() for _ in range(6))
    try:
        async with get_engine().begin() as db:
            await db.execute(
                text(
                    "INSERT INTO tenants (id,name,kind) VALUES "
                    "(:service,'service','service'),(:personal,'personal','personal')"
                ),
                {"service": service_tid, "personal": personal_tid},
            )
            await db.execute(
                text(
                    "INSERT INTO users "
                    "(id,tenant_id,email,password_hash,email_verified,is_active) "
                    "VALUES (:id,:tid,'legacy@example.com','hash',true,true)"
                ),
                {"id": user_id, "tid": personal_tid},
            )
            await db.execute(
                text(
                    "INSERT INTO collections "
                    "(id,tenant_id,name,slug,embedding_model,read_only,is_public) "
                    "VALUES (:id,:tid,'Public','public','stub@1024',true,true)"
                ),
                {"id": cid, "tid": service_tid},
            )
            await db.execute(
                text(
                    "INSERT INTO queries "
                    "(id,tenant_id,collection_id,question,answer,user_id) VALUES "
                    "(:owned,:tid,:cid,'owned question','owned answer',:uid),"
                    "(:guest,:tid,:cid,'guest question','guest answer',NULL)"
                ),
                {
                    "owned": owned_qid,
                    "guest": guest_qid,
                    "tid": service_tid,
                    "cid": cid,
                    "uid": user_id,
                },
            )

        await asyncio.to_thread(command.upgrade, config, "head")

        async with get_engine().connect() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT title,kind,tenant_id,collection_id,owner_user_id,"
                        "owner_guest_session_id,created_by_api_key_id,archived_at "
                        "FROM conversations"
                    )
                )
            ).all()
            assert len(rows) == 1
            row = rows[0]
            assert row.title == "Previous questions"
            assert row.kind == "legacy" and row.archived_at is not None
            assert row.tenant_id == service_tid and row.collection_id == cid
            assert row.owner_user_id == user_id
            assert row.owner_guest_session_id is None and row.created_by_api_key_id is None

            query_rows = (
                await db.execute(
                    text(
                        "SELECT id,conversation_id,outcome,parent_query_id,"
                        "source_generation,access_fingerprint,context_reset "
                        "FROM queries WHERE id IN (:owned,:guest)"
                    ),
                    {"owned": owned_qid, "guest": guest_qid},
                )
            ).mappings()
            queries = {row["id"]: row for row in query_rows}
            assert queries[owned_qid]["conversation_id"] is not None
            assert queries[guest_qid]["conversation_id"] is None
            assert queries[owned_qid]["outcome"] is None
            assert queries[owned_qid]["parent_query_id"] is None
            assert queries[owned_qid]["source_generation"] is None
            assert queries[owned_qid]["access_fingerprint"] is None
            assert queries[owned_qid]["context_reset"] is False

            generation = await db.scalar(
                text("SELECT source_generation FROM collections WHERE id=:id"), {"id": cid}
            )
            assert generation == 0
    finally:
        await asyncio.to_thread(command.upgrade, config, "head")
