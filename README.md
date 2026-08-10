# DocQA

[![CI](https://github.com/Hortenh1x/docqa/actions/workflows/ci.yml/badge.svg)](https://github.com/Hortenh1x/docqa/actions/workflows/ci.yml)
![coverage](https://img.shields.io/badge/coverage-89.6%25-brightgreen)
![python](https://img.shields.io/badge/python-3.12-blue)

**Ask questions about your documents. Get answers with page-level citations — or an honest "not found".**

Multi-tenant document Q&A API built on FastAPI, PostgreSQL + pgvector, Redis and Celery. Upload PDF / DOCX / Markdown, and DocQA parses, chunks and embeds them in the background — ready for hybrid retrieval and grounded, citation-backed answers.

> Built in four milestones: multi-tenant foundation and ingestion → hybrid retrieval and grounded answers over SSE → production hardening (rate limiting, idempotency, Docker, CI) → demo corpus with engineered traps, measured eval, and a Next.js UI. Remaining before the public link: pushing to GitHub (CI) and the VPS deploy — see [deploy/runbook.md](deploy/runbook.md).

## What works today

**Ask questions, get grounded answers:**

- **Hybrid retrieval** — pgvector HNSW (cosine) + Postgres FTS fused with Reciprocal Rank Fusion; optional reranking (Cohere `rerank-v3.5`, local `bge-reranker-v2-m3`, or none)
- **Cheap honest refusals** — an off-corpus question is refused *before* the LLM is called (retrieval gate, $0); a model-side `NO_ANSWER` is intercepted mid-stream and converted to a refusal (generation gate)
- **Citations that resolve** — every `[n]` maps to a document, page range, section breadcrumbs and snippet; out-of-range citations are stripped before the answer is final
- **SSE streaming** — `meta → sources → delta… → done`; sources arrive *before* the first token, so you see where the answer will come from earlier than the answer. Plain JSON mode for API clients
- **Any OpenAI-compatible LLM** — one provider class covers OpenAI, DeepSeek, Ollama and vLLM via `base_url`; Anthropic planned
- **Usage accounting** — every query (refusals included) records tokens, cost, latency and its context blocks

**Feed it documents:**

- **Multi-tenant API** — API keys (`dqa_live_…`, sha256-at-rest, shown once), tenant-scoped resources, admin CLI
- **Document upload** — streaming multipart with on-the-fly sha256, size limit (413), magic-byte type detection (415), duplicate detection via DB constraint (409 with the existing document id)
- **Background ingestion** — Celery worker: parse → section-aware chunking (~450 tokens, 60 overlap, tables kept atomic) → embeddings → bulk insert; status `pending → processing → ready | failed`
- **Parsers** — PDF (PyMuPDF, font-size heading heuristics → section breadcrumbs), DOCX (headings + tables → Markdown), MD, TXT
- **Embedding providers** — OpenAI (`text-embedding-3-small@1024`), Ollama (`bge-m3`), and a deterministic stub: tests and offline mode need zero API keys
**Run it like a service:**

- **Per-key rate limiting** — Redis token bucket (atomic Lua), per endpoint class (query 30/min, upload 10/min, default 120/min); 429 with `Retry-After` and `X-RateLimit-*`; fails open when Redis is down (availability beats quota enforcement)
- **Idempotency** — `Idempotency-Key` on uploads and non-streaming queries: concurrent duplicate → 409 `request_in_flight`, repeat → stored response replayed with `X-Idempotency-Replay: true`
- **Strict tenant isolation** — every query carries the tenant scope in its WHERE clause; a foreign resource is indistinguishable from a missing one (404, never 403); covered by an IDOR test matrix and a concurrent-dedup race test
- **Docker** — multi-stage uv image, non-root; `docker-compose.prod.yml` runs api + worker + Postgres + Redis with healthchecks, DB/Redis ports unpublished, `noeviction` Redis (a broker must never drop messages)
- **CI** — GitHub Actions: ruff, strict mypy, full test suite (testcontainers) with an 80% coverage gate on core modules (currently ~89%); Dependabot for deps and actions
- **Ops hygiene** — fail-fast config, structured JSON logs with `request_id`, RFC 9457 problem+json errors everywhere, additive Alembic migrations, `/v1/usage` aggregates, 77 tests

**Use it from a browser:**

- **Next.js UI** ([ui/](ui/)) — an "archivist's desk" interface: preset questions, sources rendered *before* the answer streams, inline citation stamps that open a source panel (file, pages, section, highlighted snippet), refusals as a first-class amber state, a library screen with upload and live ingestion statuses. `cd ui && npm install && npm run dev` against a running API.

## Measured, not promised

The repo ships a synthetic corpus (21 corporate policy documents, EN+DE) with deliberately engineered traps — a version conflict, cross-document answers, an exception buried mid-section, near-duplicate policies — plus a 30-question golden set ([eval/golden.yaml](eval/golden.yaml)). On real `bge-m3` embeddings:

| Category | Questions | Recall@8 |
| --- | --- | --- |
| direct | 10 | 1.00 |
| table | 4 | 1.00 |
| multi-doc (all sources found) | 3 | 1.00 |
| version conflict | 3 | 1.00 |
| buried exception | 2 | 1.00 |
| German | 3 | 1.00 |
| **all answerable** | **25** | **1.00** |

Off-corpus questions separate cleanly (mean gate score 0.49 vs 0.61 for answerable), and the `REFUSAL_THRESHOLD=0.50` default comes from a measured sweep — details and the reproduce command in [eval/results.md](eval/results.md). The corpus is small (41 chunks), so perfect recall says less than the score separation does; the answer-layer metrics (citation precision, faithfulness) run with `--with-answers` once an LLM is configured.

## Architecture

```mermaid
flowchart LR
  UI[client] -->|SSE| API[FastAPI]
  CLI[admin CLI] --> API
  API --> PG[(Postgres + pgvector)]
  API -->|enqueue| R[(Redis)]
  R --> W[Celery worker]
  W -->|parse · chunk · embed| PG
  W --> EMB[Embeddings: bge-m3 / OpenAI / stub]
  API --> RER[Reranker: Cohere / local / none] --> LLM[LLM: any OpenAI-compatible]
```

- **One database** for metadata, chunks, vectors (HNSW) and full-text (`tsvector`) — transactional consistency, one thing to deploy.
- **Async SQLAlchemy** in the API, **sync** engine in the worker — Celery tasks stay loop-free.
- **Everything external is a `Protocol`** with a stub implementation — the whole test suite runs offline.

## Quickstart

Requires Docker and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env          # defaults work out of the box (stub embeddings)
docker compose up -d          # Postgres (host port 5433) + Redis
uv sync
uv run alembic upgrade head

# create a tenant and an API key (key is printed once)
uv run python -m app.cli create-tenant --name acme
uv run python -m app.cli create-key --tenant-id <tenant-uuid>

# run the API and the ingestion worker
uv run uvicorn app.main:app --reload --no-access-log
uv run celery -A app.workers.celery_app worker -Q ingestion -c 2
```

Upload a document and watch it become queryable:

```bash
export KEY=dqa_live_...

curl -s -X POST localhost:8000/v1/collections \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"name": "Policies"}'

curl -s -X POST localhost:8000/v1/collections/<collection-id>/documents \
  -H "Authorization: Bearer $KEY" -F "file=@handbook.pdf"
# → 202 {"id": "…", "status": "pending"}

curl -s localhost:8000/v1/documents/<document-id> -H "Authorization: Bearer $KEY"
# → {"status": "ready", "page_count": 12, …}
```

Ask a question (SSE stream):

```bash
curl -N -X POST localhost:8000/v1/query \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"collection_id": "<collection-id>", "question": "How many vacation days do employees get?"}'

# event: meta     {"query_id": "…"}
# event: sources  {"sources": [{"n": 1, "filename": "handbook.pdf", "pages": [3, 4], …}]}
# event: delta    {"text": "Employees receive 27 vacation days per year [1]"}
# event: done     {"answer": "…", "refused": false, "confidence": 0.91,
#                  "usage": {"prompt_tokens": 2810, "completion_tokens": 142, "cost_usd": 0.0007}, …}
```

Or plain JSON (`"stream": false`) — same pipeline, one response. A question the documents can't answer returns `"refused": true` instead of a hallucination — and in most cases without spending a single LLM token.

Interactive docs: http://localhost:8000/docs

### Seed the demo corpus

```bash
uv run python -m scripts.build_corpus     # md -> PDF/DOCX (no pandoc needed)
uv run python -m scripts.seed_demo        # tenant + collections through the API
uv run python -m eval.run_eval --collection <policies-en id>   # reproduce the numbers
```

### Production-shaped stack

```bash
docker compose -f docker-compose.prod.yml up -d --build   # api + worker + db + redis
```

Single multi-stage image (non-root), migrations on start, healthchecked dependencies, database and Redis not exposed to the host. The public-demo overlay (UI + Caddy TLS, demo quotas, nightly sandbox wipe) is documented in [deploy/runbook.md](deploy/runbook.md).

## Configuration

Copy `.env.example` and adjust. Highlights:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — (required) | asyncpg DSN for the API |
| `DATABASE_URL_SYNC` | derived | psycopg DSN for the worker |
| `REDIS_URL` | — (required) | Celery broker & app cache |
| `EMBEDDING_PROVIDER` | `stub` | `stub` \| `openai` \| `ollama` |
| `EMBEDDING_DIM` | `1024` | fixed vector dimension |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | for `ollama` provider (`bge-m3`) |
| `OPENAI_API_KEY` | — | for `openai` provider |
| `LLM_PROVIDER` | `stub` | `openai_compat` \| `stub` |
| `LLM_BASE_URL` / `LLM_MODEL` | OpenAI | any OpenAI-compatible endpoint (DeepSeek, Ollama `/v1`, vLLM) |
| `RERANK_PROVIDER` | `none` | `cohere` \| `local` \| `none` \| `stub` |
| `REFUSAL_THRESHOLD` | `0.35` | rerank score below this → refuse without an LLM call |
| `RATE_LIMIT_ENABLED` | `true` | per-key token buckets (query 30/min, upload 10/min, default 120/min) |
| `MAX_UPLOAD_MB` | `25` | upload size cap → 413 |
| `MAX_PAGES` | `300` | PDF page cap → 422 |

## Design decisions

- **pgvector in the main DB, not a dedicated vector store** — transactional with metadata, one instance to run; HNSW is plenty at this scale (see Known limits).
- **RRF instead of weighted score fusion** — cosine similarity and `ts_rank` live on incomparable scales; RRF works on ranks alone, needs no normalization or weight tuning, and a chunk found by both searches naturally rises to the top.
- **Refusals are engineered, not hoped for** — two gates: retrieval (top rerank score below threshold → refuse for $0, no LLM call) and generation (the model's `NO_ANSWER` is buffered and intercepted before a single token reaches the client).
- **Sources stream before the answer** — the user sees *where* the answer will come from before the answer itself; trust is the product.
- **Fixed 1024-dim embeddings** — native for `bge-m3`, supported by OpenAI via matryoshka `dimensions=1024`; one column covers all providers, `collections.embedding_model` prevents mixing.
- **Dedup via unique constraint, not SELECT-then-INSERT** — the DB wins the race; concurrent identical uploads yield exactly one document and a 409.
- **`tsvector` with the `'simple'` config** — the corpus is bilingual (EN/DE); language-specific stemming would break one of them. FTS supplies exact matches (IDs, numbers); semantics is the vector's job.
- **Foreign tenant's resource → 404, not 403** — a 403 confirms the resource exists; that's an information leak.
- **Parser errors don't retry** — the file will not become more valid; transient (network/provider) errors retry with exponential backoff.
- **`rerank=none` for the demo is a decision, not a gap** — recall@8 is already 1.00 on this corpus and the cosine gate separates off-corpus questions cleanly (mean 0.49 vs 0.61), so a cross-encoder would add latency and an API key for no measurable gain at this scale. The pluggable path stays ready (Cohere `rerank-v3.5` or local `bge-reranker-v2-m3`); switching providers means retuning `REFUSAL_THRESHOLD` with `eval/run_eval.py` — rerank score scales differ.
- **Query stats survive disconnects** — recording runs in a cancellation-shielded `finally`; a closed laptop lid doesn't lose usage data.

## Known limits

- pgvector/HNSW is the right tool up to roughly ~10M vectors; beyond that, revisit (partitioning or a dedicated vector DB).
- Files are stored on local disk behind a `StorageProtocol` — S3/MinIO is a drop-in later, not a rewrite.
- Heading detection in PDFs is heuristic (font-size clustering); exotic layouts degrade gracefully to flat chunking.

## Roadmap

- **Live demo** — VPS deploy behind Caddy (runbook ready), demo GIF for this README
- **Answer-layer eval** — citation precision + LLM-as-judge faithfulness once a hosted LLM key is configured
- **Nice-to-haves** — Anthropic streaming provider, Prometheus metrics, Sentry
