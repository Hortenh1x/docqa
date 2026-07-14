# CLAUDE.md

## Project

DocQA — multi-tenant document Q&A (RAG) API: upload PDF/DOCX/MD/TXT → background parse → section-aware chunking → embeddings → PostgreSQL/pgvector. Later weeks add hybrid retrieval (vector + FTS + RRF + rerank), LLM answers with page-level citations and honest refusals, SSE streaming, rate limiting, a Next.js UI and a public demo.

**Source of truth for scope, schedule and all design decisions:** `plans/` (local folder, intentionally not committed) — `docqa-week{1..4}-plan.md`, `docqa-ui-plan.md`, `docqa-corpus-prompt.md`. The week-1 file also holds the full-month architecture overview and the mini-ADR table. Re-read the relevant plan before implementing a feature; surface deviations explicitly instead of silently changing course.

## Status

- **Week 1 (done):** infra, config, logging, tenants + API keys + CLI, collections, document upload with dedup, parsers, chunking, embedding providers, Celery ingestion pipeline, unit + integration tests.
- Week 2: retrieval + generation + citations + SSE. Week 3: production hardening (rate limit, idempotency, Docker, CI). Week 4: demo corpus, eval, UI, deploy.

## Stack

Python 3.12 (pinned — parity with the week-3 `python:3.12-slim` prod image), uv, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 18 + pgvector, Redis 7, Celery, structlog, pytest + testcontainers, ruff + mypy (strict) + pre-commit.

## Commands

```bash
docker compose up -d                # dev Postgres (host port 5433!) + Redis
uv sync                             # deps (incl. dev)
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --no-access-log   # access log off: structlog middleware logs requests
uv run celery -A app.workers.celery_app worker -Q ingestion -c 2
uv run python -m app.cli create-tenant --name acme
uv run python -m app.cli create-key --tenant-id <uuid>
uv run python -m app.cli revoke-key --prefix <8 chars>
uv run pytest                       # integration tests need Docker (testcontainers)
uv run pytest tests/unit            # fast, no Docker
uv run ruff check . && uv run ruff format --check . && uv run mypy app
```

Host port **5433** for dev Postgres (5432 is occupied by another local project). Local Ollama note: the systemd ollama service uses `/var/lib/ollama` for models and does not see `~/.ollama/models` (where `bge-m3` lives); for live embedding tests run `OLLAMA_HOST=127.0.0.1:11435 ollama serve` as the user and set `OLLAMA_BASE_URL=http://localhost:11435`.

## Architecture principles

1. **Modular monolith, package-by-feature** — each module under `app/` is self-contained; shared pieces live in `app/core/`.
2. **Everything external sits behind a `typing.Protocol`** (embeddings, LLM, reranker, storage) with a stub implementation — tests and the offline demo run without a single API key.
3. **Fail-fast config** (`app/config.py`, pydantic-settings): missing required env vars → the app refuses to start. No secrets in the repo.
4. **Alembic migrations are the single schema source; additive only.** Naming convention is set on `MetaData` — never create unnamed constraints.
5. **Thin routers, fat services**: a router does validation + service call + error mapping, nothing else.

## Conventions

- **Tenant isolation:** every query that fetches a resource by id carries the tenant scope in the WHERE clause (filter, not post-check). Foreign/unknown resource → **404**, never 403 (403 confirms existence).
- **Errors:** RFC 9457 problem+json with machine-readable `code` and `request_id`. Services raise `DomainError` subclasses from `app/core/errors.py`; handlers map them.
- **Embeddings:** fixed **1024** dims (`vector(1024)`); `collections.embedding_model` pins the model per collection to prevent mixing.
- **DB access:** async engine + asyncpg in the API (`app/db/base.py`), sync engine + psycopg in the Celery worker (`app/db/sync.py`). Models are shared, SQLAlchemy 2.0 `Mapped[...]` style.
- **FTS:** generated `tsvector` column with the `'simple'` config (bilingual EN+DE corpus; no stemming by design).
- **Celery tasks:** idempotent via status check; enqueue only **after** the DB commit; `ParserError` → `failed` without retry (the file won't get any more valid); transient errors → exponential backoff, max 3 retries; chunks are deleted before re-insert on reprocessing.
- **API keys:** `dqa_live_<32 base62>`; DB stores only sha256 + 8-char prefix; plaintext is shown exactly once at creation.
- **Uploads:** streamed in 1 MB chunks with on-the-fly sha256; file type by magic bytes, not extension; dedup enforced by the DB unique constraint (`IntegrityError` → 409), not SELECT-before-INSERT.
- **Tests:** pytest-asyncio (auto mode); stub providers only, no network; integration via testcontainers with `task_always_eager` Celery.
- Lint/typing: ruff (line length 100), mypy strict on `app/` (relaxed for tests).

## Layout

```
app/
├── main.py            # FastAPI factory
├── config.py          # pydantic-settings, fail-fast
├── cli.py             # tenant/key admin (argparse)
├── api/deps.py        # get_db, get_current_tenant, get_collection_or_404
├── api/v1/            # health, collections, documents (+ query, usage in later weeks)
├── core/              # security, logging, errors (+ rate_limit, idempotency in week 3)
├── db/                # base.py (async), sync.py (worker), models/
├── ingestion/         # service, parsers/, chunking, tasks
├── embeddings/        # base (Protocol), openai, ollama, stub
├── storage/           # base (Protocol), local
└── workers/celery_app.py
alembic/               # async env, versions/
tests/                 # unit/, integration/ (testcontainers), conftest.py
```
