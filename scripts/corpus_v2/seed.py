"""Seed (or refresh) a collection from a build directory through the API.

Creates the collection when the slug does not exist, uploads every file whose sha256 is
not already there (deleting an older upload with the same filename first), then waits
until nothing is in flight. Rate-limit aware (429 + Retry-After).

Usage:
  uv run python -m scripts.corpus_v2.seed --api http://localhost:8000 --api-key <key> \
      --slug kranich --name "Kranich (EN+DE)" --build corpus/large/build
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import httpx

MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--build", type=Path, default=Path("corpus/large/build"))
    args = parser.parse_args()

    files = [p for p in sorted(args.build.iterdir()) if p.suffix in MIME]
    if not files:
        raise SystemExit(f"{args.build} is empty — run the build first")
    headers = {"Authorization": f"Bearer {args.api_key}"}
    with httpx.Client(base_url=args.api, headers=headers, timeout=300) as client:
        collections = {c["slug"]: c for c in client.get("/v1/collections").json()}
        if args.slug in collections:
            collection_id = collections[args.slug]["id"]
            print(f"collection {args.slug} exists: {collection_id}")
        else:
            r = client.post(
                "/v1/collections", json={"name": args.name or args.slug, "slug": args.slug}
            )
            r.raise_for_status()
            collection_id = r.json()["id"]
            print(f"collection {args.slug} created: {collection_id}")

        existing: dict[str, dict] = {}
        offset = 0
        while True:
            r = client.get(
                f"/v1/collections/{collection_id}/documents",
                params={"limit": 100, "offset": offset},
            )
            r.raise_for_status()
            page = r.json()
            for d in page:
                existing[d["filename"]] = d
            if len(page) < 100:
                break
            offset += 100

        changed = 0
        for path in files:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            current = existing.get(path.name)
            if current and current["sha256"] == digest:
                continue
            if current:
                client.delete(f"/v1/documents/{current['id']}").raise_for_status()
            while True:
                r = client.post(
                    f"/v1/collections/{collection_id}/documents",
                    files={"file": (path.name, path.read_bytes(), MIME[path.suffix])},
                )
                if r.status_code == 429:
                    time.sleep(int(r.headers.get("retry-after", "5")))
                    continue
                break
            if r.status_code != 202:
                print(f"UPLOAD FAILED {path.name}: {r.status_code} {r.text}")
                sys.exit(1)
            changed += 1
            if changed % 25 == 0:
                print(f"  uploaded {changed}…")
        print(f"{changed} files uploaded, waiting for ingestion…")

        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            status = client.get(f"/v1/collections/{collection_id}/ingest-status").json()
            if status["failed"]:
                print(f"{status['failed']} documents failed — inspect the library")
            if status["pending"] + status["processing"] == 0:
                break
            print(
                f"  in flight: {status['pending'] + status['processing']} (eta {status['eta_seconds']}s)"  # noqa: E501
            )
            time.sleep(10)
        status = client.get(f"/v1/collections/{collection_id}/ingest-status").json()
        print(
            f"ready={status['ready']} failed={status['failed']} tokens={status['embedded_tokens']} "
            f"cost=${status['embedding_cost_usd']} access={status['access']}"
        )
        print(f"collection id: {collection_id}")


if __name__ == "__main__":
    main()
