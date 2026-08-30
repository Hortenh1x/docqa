# CLAUDE.md

## Project

DocQA — multi-tenant document Q&A (RAG) API: upload PDF/DOCX/MD/TXT → background parse → section-aware chunking → embeddings → PostgreSQL/pgvector. Later weeks add hybrid retrieval (vector + FTS + RRF + rerank), LLM answers with page-level citations and honest refusals, SSE streaming, rate limiting, a Next.js UI and a public demo.

**Source of truth for scope, schedule and all design decisions:** `plans/` (local folder, intentionally not committed) — `docqa-week{1..4}-plan.md`, `docqa-ui-plan.md`, `docqa-corpus-prompt.md`. The week-1 file also holds the full-month architecture overview and the mini-ADR table. Re-read the relevant plan before implementing a feature; surface deviations explicitly instead of silently changing course.

## Status

- **Week 1 (done):** infra, config, logging, tenants + API keys + CLI, collections, document upload with dedup, parsers, chunking, embedding providers, Celery ingestion pipeline, unit + integration tests.
- **Week 2 (done):** hybrid retrieval (vector + FTS + RRF), pluggable rerankers, `POST /v1/query` with SSE (`meta → sources → delta… → done`) and JSON modes, two refusal gates (retrieval threshold — $0; NO_ANSWER sentinel interception), citation validation/mapping, queries + query_citations recording with per-model costs.
- **Week 3 (done):** per-key rate limiting (Lua token bucket, fail-open), Idempotency-Key replay (upload + non-stream query), IntegrityError safety net, OpenAPI security schemes/tags/examples, `/v1/usage`, multi-stage non-root Docker image + `docker-compose.prod.yml`, GitHub Actions CI with an 80% coverage gate (core modules; actual ~89%), Dependabot.
- **Week 4 (done):** demo corpus (`corpus/`, 18 EN + 3 DE with engineered traps; builder in `scripts/build_corpus.py`), golden set + eval harness (`eval/`, recall@8=1.00 on bge-m3, threshold tuned to 0.50), seed script (`scripts/seed_demo.py`, 429-aware), demo mode (read-only collections, sandbox quotas, `wipe-collection`), CORS, Next.js UI (`ui/`), deploy assets (`deploy/`: Caddy, compose overlay, runbook).
- **Post-week-4 (done):** pushed to GitHub (CI live), README GIF, answer-layer eval with hosted DeepSeek on a 447-question large set (`eval/golden_large.yaml` → `eval/results_large.md`), docs split: `README.md` = quickstart only, `docs.md` = full documentation. Remaining: VPS deploy per `deploy/runbook.md`.

## Corpus & eval notes

- `corpus/*.md` are the sources; `corpus/build/` holds upload-ready PDFs/DOCX/MD. Never edit numeric facts casually — they are pinned by `plans/docqa-corpus-prompt.md` (fact registry + traps); the grep checklist lives in week-4 plan day 1.
- Refusal gate with `rerank=none` uses the best vector cosine (not normalized RRF); threshold semantics change per rerank provider **and per embedding model** — retune via `eval/run_eval.py`.
- Large eval set: `eval/golden_large.yaml` (447 EN questions; run with `--golden`/`--results`/`--concurrency`). LLM-judge runs must pass `--judge-model deepseek-chat`: plain `deepseek-v4-flash` non-deterministically burns the completion budget on hidden reasoning → empty content → verdicts parse as fails. The same quirk can empty pipeline answers when `LLM_MAX_TOKENS` is tight (2/447 observed at 1024) — hence `LLM_MAX_TOKENS=4096` in configs (thinking allowed by decision) and the pipeline's empty-completion→refusal backstop (`reason: empty_completion`).
- Seeded demo collections are pinned to `bge-m3`: querying them requires `EMBEDDING_PROVIDER=ollama` with a user-level ollama on 11435 (see `.env` comments).
- Local live-LLM runs: the same 11435 ollama serves the answer side via `LLM_PROVIDER=openai_compat` + `LLM_BASE_URL=http://localhost:11435/v1` (`qwen2.5:7b-instruct`, or `qwen2.5:3b-instruct` when VRAM is scarce — both pulled; `bge-m3` is pinned `num_gpu 0` there so embeddings never evict the LLM). `eval/run_eval.py --with-answers --judge` adds citation precision + LLM-judged faithfulness/correctness on top of the retrieval layer.

## Stack

Python 3.12 (pinned — parity with the week-3 `python:3.12-slim` prod image), uv, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 18 + pgvector, Redis 7, Celery, structlog, pytest + testcontainers, ruff + mypy (strict) + pre-commit.

## Commands

```bash
./scripts/dev.sh                    # the whole dev stack in one command (Ctrl+C stops it)
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
npm --prefix ui run dev             # Next.js UI → http://localhost:3002 (3000/3001 belong to other local apps)
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
├── config.py          # pydantic-settings, fail-fast; all tuning knobs
├── cli.py             # tenant/key admin (argparse)
├── api/deps.py        # get_db, get_current_tenant, fetch_collection
├── api/v1/            # health, collections, documents, query (+ usage in week 3)
├── core/              # security, logging, errors (+ rate_limit, idempotency in week 3)
├── db/                # base.py (async), sync.py (worker), models/
├── ingestion/         # service, parsers/, chunking, tasks
├── embeddings/        # base (Protocol), openai, ollama, stub
├── retrieval/         # vector, fulltext, fusion (RRF), rerank/, service
├── generation/        # prompts, sentinel, citations, llm/, service (query pipeline)
├── usage/costs.py     # model -> price table; unknown model -> NULL cost
├── storage/           # base (Protocol), local
└── workers/celery_app.py
alembic/               # async env, versions/
tests/                 # unit/, integration/ (testcontainers), conftest.py
```

## Query pipeline notes (week 2)

- `run_query` is an async generator of typed events; **record the query row before the
  final `yield DoneEvent`** — a JSON-mode collector stops consuming at `done`, so code
  after that yield never runs.
- The pipeline never holds a DB connection while the LLM streams: retrieval and
  recording each use their own short session from `get_sessionmaker()`.
- Recording is wrapped in `anyio.CancelScope(shield=True)` inside `finally` — stats
  survive client disconnects mid-stream.
- Routes returning `StreamingResponse | JSONResponse` need `response_model=None`.
