"""Seed the demo tenant with the corpus — through the public API, not around it.

Going through the API on purpose: the seed doubles as an end-to-end smoke test of
auth, upload validation, dedup and the ingestion worker.

Prerequisites: API + worker running, corpus built (``uv run python -m scripts.build_corpus``),
embedding provider configured (the collections get pinned to it).

Usage:
    uv run python -m scripts.seed_demo [--api http://localhost:8000] [--readonly]
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx

from app.cli import create_key, create_tenant  # noqa: F401  (imported for doc purposes)
from app.core.security import generate_api_key
from app.db.base import dispose_engine, get_sessionmaker
from app.db.models import ApiKey, Collection, Tenant
from app.ingestion.mime import DOCX_MIME, MARKDOWN_MIME, PDF_MIME

BUILD = Path("corpus/build")

MIME_BY_EXT = {".pdf": PDF_MIME, ".docx": DOCX_MIME, ".md": MARKDOWN_MIME}


async def _create_tenant_with_key(name: str) -> tuple[str, str]:
    async with get_sessionmaker()() as session:
        tenant = Tenant(name=name)
        session.add(tenant)
        await session.flush()
        plaintext, prefix, key_hash = generate_api_key()
        session.add(ApiKey(tenant_id=tenant.id, prefix=prefix, key_hash=key_hash, name="demo"))
        await session.commit()
        return str(tenant.id), plaintext


async def _mark_readonly(collection_id: str) -> None:
    async with get_sessionmaker()() as session:
        collection = await session.get(Collection, collection_id)
        assert collection is not None
        collection.read_only = True
        await session.commit()


async def seed(api: str, readonly: bool) -> None:
    files = sorted(BUILD.iterdir()) if BUILD.exists() else []
    if not files:
        print("corpus/build is empty — run: uv run python -m scripts.build_corpus", file=sys.stderr)
        raise SystemExit(1)

    de_files = [f for f in files if "-DE" in f.stem]
    en_files = [f for f in files if "-DE" not in f.stem]

    tenant_id, api_key = await _create_tenant_with_key("demo")
    headers = {"Authorization": f"Bearer {api_key}"}
    print(f"tenant: {tenant_id}")
    print(f"api key: {api_key}")

    async with httpx.AsyncClient(base_url=api, headers=headers, timeout=60) as client:
        plan = [
            ("Company Policies (EN)", "policies-en", en_files),
            ("Richtlinien (DE)", "policies-de", de_files),
            ("Sandbox — try your own files", "sandbox", []),
        ]
        collections: dict[str, str] = {}
        for name, slug, batch in plan:
            response = await client.post("/v1/collections", json={"name": name, "slug": slug})
            response.raise_for_status()
            collections[slug] = response.json()["id"]
            print(f"collection {slug}: {collections[slug]}")

            document_ids = []
            for path in batch:
                # a well-behaved client: respect 429 + Retry-After from our own limiter
                while True:
                    upload = await client.post(
                        f"/v1/collections/{collections[slug]}/documents",
                        files={"file": (path.name, path.read_bytes(), MIME_BY_EXT[path.suffix])},
                    )
                    if upload.status_code == 429:
                        wait = int(upload.headers.get("retry-after", "5"))
                        print(f"  rate limited, retrying {path.name} in {wait}s…")
                        await asyncio.sleep(wait)
                        continue
                    break
                if upload.status_code != 202:
                    print(f"  UPLOAD FAILED {path.name}: {upload.status_code} {upload.text}")
                    raise SystemExit(1)
                document_ids.append(upload.json()["id"])
                print(f"  uploaded {path.name}")

            # poll until the worker finishes every document
            deadline = time.monotonic() + 600
            pending = set(document_ids)
            while pending and time.monotonic() < deadline:
                await asyncio.sleep(2)
                listing = await client.get(f"/v1/collections/{collections[slug]}/documents")
                for doc in listing.json():
                    if doc["id"] in pending and doc["status"] in ("ready", "failed"):
                        pending.discard(doc["id"])
                        marker = "✓" if doc["status"] == "ready" else "✗ FAILED"
                        print(f"  {marker} {doc['filename']} ({doc['status']})")
                        if doc["status"] == "failed":
                            print(f"    error: {doc['error']}")
                            raise SystemExit(1)
            if pending:
                print(f"  timeout: {len(pending)} documents still processing", file=sys.stderr)
                raise SystemExit(1)

    if readonly:
        await _mark_readonly(collections["policies-en"])
        await _mark_readonly(collections["policies-de"])
        print("policies collections marked read-only (sandbox stays writable)")

    print("\nseed complete:")
    print(f"  policies-en: {collections['policies-en']}")
    print(f"  policies-de: {collections['policies-de']}")
    print(f"  sandbox:     {collections['sandbox']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument(
        "--readonly", action="store_true", help="mark policies collections read-only (public demo)"
    )
    args = parser.parse_args()

    async def _run() -> None:
        try:
            await seed(args.api, args.readonly)
        finally:
            await dispose_engine()  # same loop as the engine — asyncpg insists

    asyncio.run(_run())


if __name__ == "__main__":
    main()
