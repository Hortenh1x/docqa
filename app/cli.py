"""Admin CLI — the whole "admin panel" of v1.

Usage:
    python -m app.cli create-tenant --name acme
    python -m app.cli create-key --tenant-id <uuid> [--name ci]
    python -m app.cli revoke-key --prefix <8 chars>
    python -m app.cli list-tenants
    python -m app.cli mark-readonly --collection-id <uuid>
    python -m app.cli wipe-collection --collection-id <uuid>   # sandbox nightly cron
    python -m app.cli reprocess --collection-id <uuid> [--suffix .md]   # re-chunk in place
"""

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.core.security import display_key, generate_api_key
from app.db.base import dispose_engine, get_sessionmaker
from app.db.models import ApiKey, Collection, Document, DocumentStatus, Query, Tenant
from app.ingestion.service import delete_document_file_if_unreferenced
from app.storage.lifecycle import lock_tenant_files


async def create_tenant(name: str) -> None:
    async with get_sessionmaker()() as session:
        tenant = Tenant(name=name)
        session.add(tenant)
        await session.commit()
        print(f"tenant created: id={tenant.id} name={tenant.name!r}")


async def create_key(tenant_id: uuid.UUID, name: str) -> None:
    async with get_sessionmaker()() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            print(f"error: tenant {tenant_id} not found", file=sys.stderr)
            raise SystemExit(1)
        if tenant.kind != "service":
            print("error: personal accounts cannot receive service API keys", file=sys.stderr)
            raise SystemExit(1)
        plaintext, prefix, key_hash = generate_api_key()
        session.add(ApiKey(tenant_id=tenant_id, prefix=prefix, key_hash=key_hash, name=name))
        await session.commit()
        print(f"api key created for tenant {tenant.name!r} (key name: {name!r})")
        print(f"  {plaintext}")
        print("store it now — the key is shown only once and cannot be recovered")


async def revoke_key(prefix: str) -> None:
    async with get_sessionmaker()() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None))
        )
        keys = result.scalars().all()
        if not keys:
            print(f"error: no active key with prefix {prefix!r}", file=sys.stderr)
            raise SystemExit(1)
        for key in keys:
            key.revoked_at = datetime.now(UTC)
        await session.commit()
        for key in keys:
            print(f"revoked {display_key(key.prefix)} (id={key.id})")


async def mark_readonly(collection_id: uuid.UUID, writable: bool = False) -> None:
    async with get_sessionmaker()() as session:
        collection = await session.get(Collection, collection_id)
        if collection is None:
            print(f"error: collection {collection_id} not found", file=sys.stderr)
            raise SystemExit(1)
        await lock_tenant_files(session, collection.tenant_id)
        await session.refresh(collection, with_for_update=True)
        if writable and collection.is_public:
            print("error: unpublish the collection before making it writable", file=sys.stderr)
            raise SystemExit(1)
        collection.read_only = not writable
        await session.commit()
        state = "writable" if writable else "read-only"
        print(f"collection {collection.slug!r} is now {state}")


async def publish_collection(collection_id: uuid.UUID, private: bool = False) -> None:
    """Explicitly expose reviewed demo data; personal data can never be published."""
    from app.config import get_settings

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                select(Collection, Tenant)
                .join(Tenant, Collection.tenant_id == Tenant.id)
                .where(Collection.id == collection_id)
            )
        ).one_or_none()
        if row is None:
            print("error: collection not found", file=sys.stderr)
            raise SystemExit(1)
        collection, tenant = row
        if tenant.kind != "service" or (
            not private and (tenant.id != get_settings().public_tenant_id or not tenant.is_active)
        ):
            print("error: only the configured public service tenant can publish", file=sys.stderr)
            raise SystemExit(1)
        await lock_tenant_files(session, collection.tenant_id)
        await session.refresh(collection, with_for_update=True)
        collection.is_public = not private
        collection.read_only = True
        collection.data_version += 1
        await session.commit()
        print(f"collection {collection.slug!r} is now {'private' if private else 'public'}")


async def wipe_collection(collection_id: uuid.UUID) -> None:
    """Remove all documents (and their chunks/files) — the sandbox nightly reset."""
    async with get_sessionmaker()() as session:
        collection = await session.get(Collection, collection_id)
        if collection is None:
            print(f"error: collection {collection_id} not found", file=sys.stderr)
            raise SystemExit(1)
        await lock_tenant_files(session, collection.tenant_id)
        await session.refresh(collection, with_for_update=True)
        tenant = await session.get(Tenant, collection.tenant_id)
        if tenant is None or tenant.kind != "service" or collection.is_public:
            print(
                "error: sandbox wipe is forbidden for personal or public collections",
                file=sys.stderr,
            )
            raise SystemExit(1)
        documents = (
            (await session.execute(select(Document).where(Document.collection_id == collection_id)))
            .scalars()
            .all()
        )
        await session.execute(delete(Document).where(Document.collection_id == collection_id))
        await session.execute(delete(Query).where(Query.collection_id == collection_id))
        collection.data_version += 1
        collection.suggested_questions = None  # stale once the documents are gone
        await session.commit()
        for document in documents:
            await delete_document_file_if_unreferenced(
                session, collection.tenant_id, document.sha256, document.mime_type
            )
        await session.commit()
        # Also remove answers from Redis. A failed purge is a failed command, so
        # scheduled jobs can alert/retry; never silently claim complete cleanup.
        from app.core.idempotency import purge_tenant_cache

        await purge_tenant_cache(collection.tenant_id)
        print(f"wiped {len(documents)} documents from {collection.slug!r}")


async def reprocess_documents(collection_id: uuid.UUID, suffix: str | None) -> None:
    """Re-run ingestion for stored documents (after a parser or chunker change): status
    back to pending, then one task per document — the worker re-parses the file it
    already has, replaces the chunks and refreshes the suggested questions when done.
    No upload, so neither the demo cap nor the rate limiter is involved."""
    from app.ingestion.tasks import ingest_document

    async with get_sessionmaker()() as session:
        collection = await session.get(Collection, collection_id)
        if collection is None:
            print(f"error: collection {collection_id} not found", file=sys.stderr)
            raise SystemExit(1)
        await lock_tenant_files(session, collection.tenant_id)
        await session.refresh(collection, with_for_update=True)
        documents = (
            (await session.execute(select(Document).where(Document.collection_id == collection_id)))
            .scalars()
            .all()
        )
        targets = [
            d for d in documents if suffix is None or d.filename.lower().endswith(suffix.lower())
        ]
        if targets:
            collection.data_version += 1
            collection.suggested_questions = None
        for document in targets:
            document.status = DocumentStatus.PENDING
            document.error = None
            document.ingestion_attempts = 0
            document.processing_token = None
            document.lease_expires_at = None
            document.next_attempt_at = None
            document.last_enqueued_at = None
        await session.commit()
        ids = [str(d.id) for d in targets]
    # enqueue only after the commit — the worker must see 'pending'
    for document_id in ids:
        ingest_document.delay(document_id)
    print(f"re-enqueued {len(ids)} of {len(documents)} documents")


async def list_tenants() -> None:
    async with get_sessionmaker()() as session:
        result = await session.execute(select(Tenant).order_by(Tenant.created_at))
        rows = result.scalars().all()
        if not rows:
            print("no tenants")
            return
        for t in rows:
            state = "active" if t.is_active else "inactive"
            print(f"{t.id}  {state:8}  {t.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="DocQA admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-tenant", help="create a tenant")
    p.add_argument("--name", required=True)

    p = sub.add_parser("create-key", help="create an API key (printed once)")
    p.add_argument("--tenant-id", required=True, type=uuid.UUID)
    p.add_argument("--name", default="default")

    p = sub.add_parser("revoke-key", help="revoke an API key by its 8-char prefix")
    p.add_argument("--prefix", required=True)

    sub.add_parser("list-tenants", help="list tenants")

    p = sub.add_parser("mark-readonly", help="make a collection read-only (demo)")
    p.add_argument("--collection-id", required=True, type=uuid.UUID)
    p.add_argument("--writable", action="store_true", help="undo: make writable again")

    p = sub.add_parser("publish-collection", help="publish an explicitly reviewed public demo")
    p.add_argument("--collection-id", required=True, type=uuid.UUID)
    p.add_argument("--private", action="store_true", help="remove public access, keep read-only")

    p = sub.add_parser("reprocess", help="re-chunk a collection's stored documents in place")
    p.add_argument("--collection-id", type=uuid.UUID, required=True)
    p.add_argument("--suffix", default=None, help="only filenames ending with this, e.g. .md")
    p = sub.add_parser("wipe-collection", help="delete all documents in a collection (sandbox)")
    p.add_argument("--collection-id", required=True, type=uuid.UUID)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    async def run() -> None:
        try:
            if args.command == "create-tenant":
                await create_tenant(args.name)
            elif args.command == "create-key":
                await create_key(args.tenant_id, args.name)
            elif args.command == "revoke-key":
                await revoke_key(args.prefix)
            elif args.command == "list-tenants":
                await list_tenants()
            elif args.command == "mark-readonly":
                await mark_readonly(args.collection_id, writable=args.writable)
            elif args.command == "publish-collection":
                await publish_collection(args.collection_id, private=args.private)
            elif args.command == "wipe-collection":
                await wipe_collection(args.collection_id)
            elif args.command == "reprocess":
                await reprocess_documents(args.collection_id, args.suffix)
        finally:
            await dispose_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
