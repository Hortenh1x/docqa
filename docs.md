# DocQA — full documentation

The [README](README.md) covers the quick start; this file holds everything else: features, measured evaluation results, architecture, configuration and design decisions. Deployment lives in [deploy/runbook.md](deploy/runbook.md).

## What works today

**Ask questions, get grounded answers:**

- **Hybrid retrieval** — pgvector HNSW (cosine) + Postgres FTS fused with Reciprocal Rank Fusion; optional reranking (Cohere `rerank-v3.5`, local `bge-reranker-v2-m3`, or none)
- **Cheap honest refusals** — an off-corpus question is refused *before* the LLM is called (retrieval gate, $0); a model-side `NO_ANSWER` is intercepted mid-stream and converted to a refusal (generation gate)
- **Citations that resolve** — every `[n]` maps to a document, page range, section breadcrumbs and snippet; out-of-range citations are stripped before the answer is final
- **SSE streaming** — `meta → sources → delta… → done`; sources arrive *before* the first token, so you see where the answer will come from earlier than the answer. Plain JSON mode for API clients
- **Any OpenAI-compatible LLM** — one provider class covers OpenAI, DeepSeek, Ollama and vLLM via `base_url`; Anthropic planned
- **Usage accounting** — every query (refusals included) records tokens, cost, latency, the access role and its context blocks
- **Access-aware retrieval** — sections of a document can be restricted to a group (`Access: Finance only` in the text); every chunk carries that label and retrieval filters on it *in the WHERE clause* before ranking, so a restricted passage never reaches the prompt, the sources or the citations. The caller states its role (`role` on `POST /v1/query`, roles from `GET /v1/roles`); in demo reveal mode the response also says how many relevant passages the role could not see and which group unlocks them. Details below

**Feed it documents:**

- **Multi-tenant API** — API keys (`dqa_live_…`, sha256-at-rest, shown once), tenant-scoped resources, admin CLI
- **Document upload** — streaming multipart with on-the-fly sha256, size limit (413), magic-byte type detection (415), duplicate detection via DB constraint (409 with the existing document id)
- **Background ingestion** — Celery worker: parse → section-aware chunking (~450 tokens, 60 overlap, tables kept atomic) → embeddings → bulk insert; status `pending → processing → ready | failed`
- **Parsers** — PDF (PyMuPDF, font-size heading heuristics → section breadcrumbs), DOCX (headings + tables → Markdown), MD, TXT
- **Embedding providers** — OpenAI (`text-embedding-3-small@1024`), Ollama (`bge-m3`), and a deterministic stub: tests and offline mode need zero API keys
- **Suggested questions** — once a collection's ingestion settles, the answering LLM drafts starter questions from a corpus sample (count+2 candidates, ranked by their own retrieval score so the least grounded fall off; corpus-language aware — the German set gets German questions); each question carries the least-privileged role that can answer it (`min_role`), and a collection with restricted content always gets at least one locked question; stored on the collection, refreshed after uploads/deletes, cleared on wipe
- **Ingestion progress & cost** — `GET /v1/collections/{id}/ingest-status`: document counts by status, tokens embedded so far priced at the collection's embedding model (e.g. the whole 21-doc demo corpus ≈ $0.0004 on `text-embedding-3-small`), and an ETA for in-flight documents derived from recently measured throughput

**Run it like a service:**

- **Per-key rate limiting** — Redis token bucket (atomic Lua), per endpoint class (query 30/min, upload 10/min, default 120/min); 429 with `Retry-After` and `X-RateLimit-*`; fails open when Redis is down (availability beats quota enforcement)
- **Demo cost cap** — optional daily query quota per (api key, client address), so a public demo where every visitor shares one key still bounds spend per visitor: at `deepseek-v4-flash` prices a worst-case query is ~$0.001, so `RATE_LIMIT_QUERY_PER_DAY=900` keeps one visitor under **$1/day**; 429 `daily_quota_exceeded` with `Retry-After` to UTC midnight and `X-Quota-Daily-*` headers
- **Idempotency** — `Idempotency-Key` on uploads and non-streaming queries: concurrent duplicate → 409 `request_in_flight`, repeat → stored response replayed with `X-Idempotency-Replay: true`
- **Strict tenant isolation** — every query carries the tenant scope in its WHERE clause; a foreign resource is indistinguishable from a missing one (404, never 403); covered by an IDOR test matrix and a concurrent-dedup race test
- **Docker** — multi-stage uv image, non-root; `docker-compose.prod.yml` runs api + worker + Postgres + Redis with healthchecks, DB/Redis ports unpublished, `noeviction` Redis (a broker must never drop messages)
- **CI** — GitHub Actions: ruff, strict mypy, full test suite (testcontainers) with an 80% coverage gate on core modules (currently ~89%); Dependabot for deps and actions
- **Ops hygiene** — fail-fast config, structured JSON logs with `request_id`, RFC 9457 problem+json errors everywhere, additive Alembic migrations, `/v1/usage` aggregates, 77 tests

**Use it from a browser:**

- **Next.js UI** ([ui/](ui/)) — an "archivist's desk" interface: each collection's own suggested questions as starter chips (LLM-generated after ingestion; no static fallback — an empty collection shows no chips; a lock marks questions the current role cannot answer), a "Viewing as" role switch in the top bar, sources rendered *before* the answer streams (restricted passages wear their group's tag), inline citation stamps that open a source panel (file, pages, section, access, highlighted snippet), refusals as a first-class amber state — including "not available at your access level" with a one-click "View as Finance" — a library screen with upload, live ingestion statuses, per-document access tags and a progress line (ETA + embedded tokens + running cost + restricted passages). `cd ui && npm install && npm run dev` against a running API.

## Measured, not promised

The repo ships a synthetic corpus (21 corporate policy documents, EN+DE) with deliberately engineered traps — a version conflict, cross-document answers, an exception buried mid-section, near-duplicate policies, five guaranteed knowledge gaps — plus two golden sets:

- [eval/golden.yaml](eval/golden.yaml) — the original 30 questions (incl. 3 German)
- [eval/golden_large.yaml](eval/golden_large.yaml) — **447 English questions**: direct(167), table(40), multi-doc(40), version(30), buried(20), and 150 must-refuse questions (the five engineered gaps plus 17 grep-verified absent topics)

### Large set, full pipeline (bge-m3 retrieval, `deepseek-v4-flash` answers)

| Retrieval (recall@8) | Result |
| --- | --- |
| direct (167) | 0.99 |
| table (40) | 0.97 |
| multi-doc, all sources found (40) | 0.97 |
| version conflict (30) | 1.00 |
| buried exception (20) | 1.00 |
| **all answerable (297)** | **0.99** |

| Answer-layer metric | Result |
| --- | --- |
| End-to-end refusals on 150 off-corpus questions | 149/150 — **zero invented answers** |
| Citation precision (cited docs ∈ expected docs) | 281/282 (99.6%) |
| Faithfulness — every claim supported by retrieved excerpts (LLM-judged) | **278/278 (100%)** |
| Correctness vs the golden answer (LLM-judged) | 272/278 (97.8%) |
| False refusals on answerable questions | 18/297 (6%) |

Reading the failures, not just the rates:

- All 6 correctness misses are **faithful but incomplete** (a secondary fact dropped, or over-hedging); one traces to a retrieval miss, not generation. No hallucinations anywhere.
- 15 of 18 false refusals are $0 retrieval-gate refusals with scores 0.442–0.500 — just under the threshold; the sweep on this set recommends `REFUSAL_THRESHOLD=0.48` (97% answerable pass rate, 31% of off-corpus refused for free).
- The single off-corpus "non-refusal" returned an empty answer, not an invented one (see the DeepSeek note in Known limits).
- The 3 retrieval misses are honest limitations: `'simple'` FTS does no stemming ("project" ≠ "projects"), one table-heavy chunk lost the fusion, one multi-hop pair needed a document that never surfaced.

Details, threshold sweep and the reproduce command: [eval/results_large.md](eval/results_large.md). Judge runs use `--judge-model deepseek-chat` (the non-thinking alias of the same model — see Known limits for why).

The same 447 questions were also run end-to-end on **OpenAI `text-embedding-3-small@1024`** (the deploy configuration): recall@8 stays 0.99, faithfulness 292/292, correctness 287/292 (98.3%), citation precision 294/297, and the NO_ANSWER sentinel alone refuses 149/150 off-corpus questions with only 5/297 false refusals — the one "leak" is a correct grounded negative, not an invention. The cosine scale differs per embedding model, so the gate threshold is measured per provider: 0.28 for OpenAI vs 0.48 for bge-m3 — analysis in [eval/results_large_openai.md](eval/results_large_openai.md).

### Access levels (32-question set, OpenAI embeddings + `deepseek-v4-flash`)

[eval/golden_access.yaml](eval/golden_access.yaml) asks about the eight restricted passages (F25–F32) under roles that may and may not read them, plus three partial questions that mix an open and a restricted fact. Results ([eval/results_access.md](eval/results_access.md)):

| Access metric | Result |
| --- | --- |
| Retrieval leaks — a chunk outside the role's labels surfaced (15 restricted questions) | **0/15** |
| End-to-end leaks — an answer instead of a refusal | **0/15** |
| Reveal hint names the label that unlocks the passage | 15/15 |
| Unlock questions (asked under the right role), recall@8 | 17/17 |
| Citation precision on unlock questions | 17/17 |
| False refusals | 1/17 — a partial question (open equipment budget + restricted write-off threshold) that the model answered with `NO_ANSWER` instead of the open half |

The classic 30-question set keeps recall@8 = 1.00 under both `leadership` and `employee` — restricting sections did not disturb retrieval of the open ones.

### Original 30-question set (local `qwen2.5:7b-instruct`)

The same pipeline measured fully offline — recall@8 = 1.00 on all 25 answerable questions (incl. German → bge-m3 is multilingual), 5/5 refusals, citation precision 24/24, faithfulness 20/21, correctness 19/21. A 7B model plays it safe: 3 of its 4 false refusals were `NO_ANSWER` on paraphrase-heavy traps — the hosted rerun above reclaimed them. Details: [eval/results.md](eval/results.md).

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

## Production-shaped stack

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
| `LLM_MAX_TOKENS` | `1024` | completion budget; raise to ~4096 if the model spends hidden reasoning tokens (see Known limits) |
| `RERANK_PROVIDER` | `none` | `cohere` \| `local` \| `none` \| `stub` |
| `REFUSAL_THRESHOLD` | `0.50` | retrieval-gate score below this → refuse without an LLM call; the scale is provider-specific (best vector cosine when `rerank=none`) — measured: `0.28` for `text-embedding-3-small@1024`, `~0.48` for `bge-m3`; retune with `eval/run_eval.py` after switching embeddings or reranker |
| `SUGGESTED_QUESTIONS_ENABLED` | `true` | LLM-drafted starter questions per collection, refreshed when ingestion settles |
| `SUGGESTED_QUESTIONS_COUNT` | `3` | how many suggested questions are kept (count+2 drafted, ranked by retrieval score) |
| `ACCESS_ROLES` | employee/manager/hr/finance/leadership | JSON map role → readable content labels; every role must include `all` (see Access-aware retrieval) |
| `ACCESS_DEFAULT_ROLE` | `employee` | role assumed when a query names none — least privilege by design |
| `ACCESS_REVEAL_HIDDEN` | `false` | demo mode: report how many relevant passages the role could not see and which labels unlock them (this confirms restricted content exists — keep it off where that matters) |
| `RATE_LIMIT_ENABLED` | `true` | per-key token buckets (query 30/min, upload 10/min, default 120/min) |
| `RATE_LIMIT_QUERY_PER_DAY` | `0` (off) | daily query quota per key+address; `900` ≈ ≤ $1/day per visitor on `deepseek-v4-flash` |
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
- **`rerank=none` for the demo is a decision, not a gap** — recall@8 is 0.99 on the 447-question set and the cosine gate separates off-corpus questions, so a cross-encoder would add latency and an API key for little measurable gain at this scale. The pluggable path stays ready (Cohere `rerank-v3.5` or local `bge-reranker-v2-m3`); switching providers means retuning `REFUSAL_THRESHOLD` with `eval/run_eval.py` — rerank score scales differ.
- **Query stats survive disconnects** — recording runs in a cancellation-shielded `finally`; a closed laptop lid doesn't lose usage data.
- **Access control is a retrieval filter, not an answer filter** — see the next section.

## Access-aware retrieval

Real corporate documents mix audiences: the expense policy everyone reads has a card-limit section only Finance should see; the offboarding checklist has a for-cause procedure meant for managers. DocQA models that at the level it actually occurs — the **section**, not the document.

**Labels and roles are two different vocabularies.** A *label* classifies content (`all`, `managers`, `hr`, `finance`, `leadership`). A *role* describes who is asking (`employee`, `manager`, `hr`, `finance`, `leadership`). `ACCESS_ROLES` maps each role to the labels it may read; the map is a partial order on purpose — HR and Finance are siblings, not rungs of one ladder — so "Finance sees HR content" never happens by accident.

**Where labels come from.** A visible line right after a heading — `Access: Managers only`, `Zugriff: nur Finanzen` — labels that section and its sub-sections until the next heading of the same or a higher level; a marker before the first heading labels the whole document. The marker stays in the text (the model reads it like a person would). This is what real documents look like, it is deterministic, and it survives PDF/DOCX rendering. An unknown group name fails **closed** (the section becomes `leadership`) with a warning; the per-label counts on `ingest-status` make such mistakes visible.

**Where filtering happens.** In the `WHERE` clause of both searches (`chunks.access_label IN (:labels)`), before ranking, fusion and reranking — the same discipline as tenant isolation. Post-filtering was rejected: it would let restricted text into the candidate set and into the prompt. Two consequences follow: a chunk carries exactly one label, so the chunker never merges neighbouring sections with different labels (the leak that would otherwise happen silently); and a role that sees a small slice of the corpus still gets a full `top_k`, because HNSW scans iteratively (`hnsw.iterative_scan = relaxed_order`, pgvector ≥ 0.8) instead of stopping after `ef_search` candidates.

**Who asserts the role.** The API key identifies a trusted client (an integrator's backend); `role` on the query is that client's claim about its end user, exactly as with any RAG API behind an identity provider. A missing role resolves to the least-privileged one — never to "everything". Binding allowed roles to the key is the natural hardening step and is not implemented.

**The 403-versus-404 trade-off, made explicit.** Everywhere else DocQA answers a foreign resource with 404, because a 403 confirms it exists. For access-filtered retrieval the honest default is the same: an employee asking about salary bands gets "not in the documents". A demo that behaves that way looks broken, so `ACCESS_REVEAL_HIDDEN=true` adds one extra vector query over the *complement* of the role's labels and reports only a count and the labels involved — never content. A hidden passage counts when it scores at least as well as the best passage the role can see (minus a small margin) and above the refusal threshold, so the hint names the group that actually holds the answer rather than every restricted section loosely related to the question. The UI turns that into "3 passages are restricted to Leadership — view as Leadership". Production deployments that must not confirm existence leave the flag off; the response then carries `hidden_passages: null`.

**Things that had to be made role-aware too.** `Idempotency-Key` results are fingerprinted with (collection, role, question): the same key under another role is refused (422 `idempotency_key_reused`) instead of replaying an answer produced with different access. Suggested questions are scored under every role and stored with a `min_role`; a question drafted from a restricted excerpt must not carry the figure it asks about, so candidates containing digits or currency signs are dropped. The eval harness runs with `--role leadership` for the classic categories and, for the `access` category, checks that a hidden document never surfaces under a restricted role.

**Out of scope, on purpose.** The original file (`GET /v1/documents/{id}/file`) and the Library are the administrator's view and are not filtered; the role governs what the question-answering path may read.

## Corpus v2: a 300-document company, generated facts-first

The 21-document Kranich corpus saturates retrieval (recall@8 = 0.99: top-8 is 13% of the corpus). Corpus v2 is the same fictional company at realistic scale — **298 documents, ~230k words, EN + DE in one collection** — built so that every number in it is traceable to a registry and the golden set is derived from that registry rather than written by hand.

**How it is made** ([scripts/corpus_v2/](scripts/corpus_v2/), sources in [corpus/large/](corpus/large/)):

1. `spec.py` describes the world: 28 policies with 1–3 versions each (older versions carry older values, some without a "superseded" banner), six country handbooks with the same structure and different figures, per-year rate sheets, HR/Finance/Security/Engineering/Operations guides, leadership memos, meeting notes whose decisions change over time, FAQs (six of them stale, still quoting an old value), customer-facing pages and 30 German mirrors. `make_spec.py` materializes `facts.yaml` (218 facts; pinned v1 values where the topics overlap, seeded random values elsewhere, unique per unit so a figure traces to one fact) and `manifest.yaml` (which facts, sections, access labels and cross references each document carries).
2. `generate.py` writes one document per LLM call (`deepseek-chat`) from the document's own fact slice; the model never sees the rest of the registry. `validate.py` rejects a draft when a value is missing from its section, a value of *another* document appears, any digit outside the whitelist appears (section numbers, ids, versions, dates, years), a forbidden topic is mentioned, a marker is misplaced or the length is off — and the findings go back into the prompt for up to three regenerations. German mirrors translate the accepted English text with German number formatting.
3. `make_golden.py` derives `eval/golden_v2.yaml`: two paraphrased questions per fact (the LLM sees one fact at a time and may not use digits), expected sources from the manifest, categories from fact metadata — `direct`, `table`, `version` / `version_history`, `buried`, `distractor_country`, `multi_doc` (cross references), `stale_faq`, `as_of_date`, `german`, `access` (refuse/unlock pairs), `partial`, and grep-verified `no_answer` questions about topics that do not exist in the corpus.
4. `build_corpus.py --src corpus/large/docs --manifest …` renders PDF/DOCX/MD by family; `seed.py` uploads the build through the API into the `kranich` collection.

**Traps at scale:** version conflicts across 28 policies, cross-document references without values, exceptions buried in long handbooks, the same tables per country and per year, stale FAQs that contradict the current policy, meeting decisions superseded by later meetings, restricted sections and fully restricted documents.

### Measured on corpus v2

Retrieval layer, 602 answerable questions (of 828), asked as `leadership` so nothing is filtered; every question is a paraphrase without digits, so exact-match signals are deliberately weak ([eval/results_v2_A_vector_only.md](eval/results_v2_A_vector_only.md), [eval/results_v2_B_hybrid.md](eval/results_v2_B_hybrid.md), [eval/results_v2_D_hybrid_top12.md](eval/results_v2_D_hybrid_top12.md), [eval/results_v2.md](eval/results_v2.md)):

| Category (questions) | vector only, top-8 | hybrid, top-8 | hybrid, top-12 | hybrid, top-20 (deploy config) |
| --- | --- | --- | --- | --- |
| direct (142) | 0.95 | 0.95 | 0.96 | 0.97 |
| table (16) | 0.62 | 0.62 | 0.81 | 1.00 |
| multi-doc, all sources found (80) | 0.82 | 0.82 | 0.89 | 0.99 |
| version, current value (52) | 0.94 | 0.94 | 1.00 | 1.00 |
| version history, old value (24) | 0.79 | 0.79 | 0.88 | 1.00_history |
| stale FAQ vs policy (6) | 0.67 | 0.67 | 1.00 | 1.00 |
| as-of-date meeting decisions (12) | 0.67 | 0.67 | 0.75 | 0.92 |
| country variants (84) | 1.00 | 1.00 | 1.00 | 1.00 |
| German (78) | 1.00 | 1.00 | 1.00 | 1.00 |
| access, unlocked (90) | — | 0.99 | 1.00 | 1.00 |
| **all answerable** | **0.92** | **0.93** | **0.96** | **0.99** |

Reading it: the 21-document corpus hid the retrieval window entirely (top-8 was 13% of the corpus); at 1,165 chunks the window is the lever. Tables lose most at top-8 because six country supplements and three policy versions crowd out the one rate sheet that holds the current figure; the same crowding hits version history and meeting decisions. Hybrid retrieval equals vector-only here to the last digit — the golden set forbids digits and shared keywords in questions, which is exactly the regime where FTS has nothing to anchor on (on v1's ID- and number-bearing questions it mattered). Country variants and German mirrors are solved by the embedding alone.

**Full pipeline** (hybrid, top-20, `deepseek-v4-flash`, judge `deepseek-chat`; 828 questions, [eval/results_v2.md](eval/results_v2.md)):

| Answer-layer metric | Result |
| --- | --- |
| Faithfulness — every claim supported by the retrieved excerpts (LLM-judged, 582 answered) | **580/582** |
| Correctness vs the golden answer (LLM-judged) | 570/582 (97.9%) |
| Citation precision (cited docs ∈ expected docs) | 596/602 |
| False refusals on answerable questions | 20/602 (3.3%) |
| Off-corpus questions (136): refused | 106/136 — the other 30 got a *grounded* answer (mileage rules when asked about a "car allowance", the learning budget when asked about tuition); the judge found **1** of the 36 answered off-corpus questions unfaithful |
| Access: restricted values appearing in any answer | **0/90** |
| Access: chunks outside the role's labels retrieved | **0/102** |
| Access: answered from open content instead of refusing (no restricted value involved) | 6/90 |
| Access: reveal hint names the unlocking group | 95/102 |

Two things v1 could not show. First, the retrieval gate threshold is a property of the corpus, not only of the embedding model: on the same `text-embedding-3-small` the sweep recommends `0.46` here versus `0.28` on the 21-document set, because a dense corpus always has *something* near an off-corpus question (mean gate score of unanswerable questions: 0.46 vs 0.38); at the deployed 0.28 the gate refuses almost nothing for free and the `NO_ANSWER` sentinel carries the load — still with zero invented rules. Second, "refused" is the wrong yardstick for off-corpus questions once the corpus is rich: the honest metric is *faithfulness of what was answered*, which is why the harness now judges those answers too.

The seven remaining top-20 misses are informal documents losing to formal ones on the same topic: all-hands notes stating the headcount or the NPS rank below FAQs and handbooks that discuss the same subject without the figure, and one meeting decision outranked by a later meeting on a neighbouring topic.

## Public corpora: GitLab Handbook, GovReport, CUAD, FinanceBench

The demo also carries four collections of **real** documents — 9,461 files, ~295k chunks —
so the interface can be exercised against text nobody engineered for it: the GitLab
handbook (3,639 pages), 4,979 US congressional research reports, 509 commercial contracts
(CUAD, CC-BY-4.0) and 334 SEC filings (FinanceBench, Apache-2.0). The last two ship with
expert annotations, which yielded two more golden sets without hand-writing questions:
[eval/golden_cuad.yaml](eval/golden_cuad.yaml) (130 clause questions) and
[eval/golden_financebench.yaml](eval/golden_financebench.yaml) (140 of the 150 published
questions).

| | CUAD (509 contracts) | FinanceBench (334 filings) |
| --- | --- | --- |
| Recall (expected document in the retrieved chunks) | **0.98** | 0.89 |
| Citation precision | **98%** | 88% |
| Faithfulness (LLM-judged) | 84/87 (97%) | 68/70 (97%) |
| Correctness vs the expert answer | 78/87 (90%) | 61/70 (87%) |
| Refused instead of answering | 33% | 50% |

These numbers are lower than the synthetic sets above, and that is the point of having
them. Two findings came out of the gap, both documented in
[eval/results_financebench.md](eval/results_financebench.md) and
[eval/results_cuad.md](eval/results_cuad.md):

- **The pipeline was retrieving the evidence and then cutting it off.** With eight chunks
  and a 3,600-token context budget, the expected document sat *just below the cut* for 40
  of 140 finance questions while only 3 were missing from retrieval entirely. Widening the
  window (`top_k` 30→100, `rerank_top_n` 8→20, context 3,600→9,000) moved FinanceBench
  recall 0.70→0.89 and CUAD 0.87→0.98, and cut refusals by 10 and 13 points. Widening the
  *search* costs nothing measurable (1,673 ms at `top_k=100` vs 1,693 ms at 30); the added
  latency is entirely the larger prompt, and the per-query cost roughly tripled — which is
  why the demo's daily quota moved 900→600.
- **A quarter of FinanceBench is not a retrieval task.** Where the expected number never
  surfaces, it usually does not exist in the filing: the answers are derived metrics
  (quick ratio, per-share figures) an analyst computes from balance-sheet lines. This
  system answers what documents *say*, with a page reference, and refuses otherwise — so
  those count as refusals and are deliberately not "fixed".

A cross-encoder reranker would address about 16% of the finance questions (measured: the
share whose answering chunk is retrieved but ranks below the cut), at the price of a second
paid API on the query path. The pluggable path is in the code (`RERANK_PROVIDER`); it is
not enabled here.

## Known limits

- pgvector/HNSW is the right tool up to roughly ~10M vectors; beyond that, revisit (partitioning or a dedicated vector DB).
- Files are stored on local disk behind a `StorageProtocol` — S3/MinIO is a drop-in later, not a rewrite.
- Heading detection in PDFs is heuristic (font-size clustering); exotic layouts degrade gracefully to flat chunking.
- **DeepSeek `v4-flash` hidden reasoning** — the model non-deterministically spends completion tokens on reasoning the OpenAI-compatible stream carries outside `content`; with a tight `LLM_MAX_TOKENS` this can exhaust the budget and yield an empty answer (measured: 2 of 447 eval queries at 1024). Mitigations: raise `LLM_MAX_TOKENS` to ~4096 so reasoning completes and the answer follows (verified — the demo config does this), or use the non-thinking alias `deepseek-chat` (same model, same price). As a backstop, the pipeline converts an empty completion into an honest refusal (`reason: empty_completion`) instead of returning a blank answer. A provider-level `thinking: disabled` toggle is planned.
- `'simple'` FTS does no stemming by design (bilingual corpus) — singular/plural mismatches occasionally cost a retrieval hit; the vector side usually covers them.

## Roadmap

- **Live demo** — VPS deploy behind Caddy (runbook ready)
- **Nice-to-haves** — provider-level thinking toggle for DeepSeek, Anthropic streaming provider, Prometheus metrics, Sentry
