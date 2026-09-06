# Deploy runbook — public demo on a VPS

Target: a small VPS (e.g. Hetzner CX32, 4 vCPU / 8 GB, EU) running the full stack:
Caddy (TLS) → UI + API → worker → Postgres/Redis. Nothing but 22/80/443 exposed.

## 1. Server prep (once)

```bash
apt update && apt install -y ufw
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw enable
# docker + compose plugin per docs.docker.com; create a deploy user in the docker group
```

DNS: point `docqa.example.com` and `app.docqa.example.com` (A records) at the server.

## 2. Configuration

Clone the repo, then create `.env` next to `docker-compose.prod.yml` (never commit it):

```bash
POSTGRES_PASSWORD=<random>
DOCQA_DOMAIN=docqa.example.com
DOCQA_APP_DOMAIN=app.docqa.example.com
DEMO_MODE=true
EMBEDDING_PROVIDER=openai            # measured choice — see the threshold note below
OPENAI_API_KEY=…
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash          # thinking allowed by decision — LLM_MAX_TOKENS below gives hidden
                                     # reasoning room to finish (at 1024 it emptied 2/447 answers; the
                                     # pipeline now converts an empty completion into a refusal as a backstop).
                                     # Cheaper/simpler alternative: LLM_MODEL=deepseek-chat = the same model
                                     # in non-thinking mode, same price, then LLM_MAX_TOKENS can stay 1024.
LLM_MAX_TOKENS=4096
LLM_API_KEY=…
REFUSAL_THRESHOLD=0.28               # measured for text-embedding-3-small@1024 on the 447-question set
                                     # (eval/results_large_openai.md: recall@8 0.99, faithfulness 100%,
                                     # 98% answerable pass, e2e refusal 99%). The scale is embedding-model-
                                     # specific: bge-m3 via ollama needs 0.48 (eval/results_large.md) and an
                                     # ollama container; any other provider — re-run eval/run_eval.py against
                                     # a collection seeded with it and take the sweep's recommendation.
RERANK_PROVIDER=none                 # cohere + COHERE_API_KEY for better precision
RATE_LIMIT_QUERY_PER_MINUTE=10       # demo pacing
RATE_LIMIT_QUERY_PER_DAY=600         # cost cap: ~$1.4/day worst case per visitor (typical ~$0.8).
                                     # Lowered from 900 when the retrieval window widened: a query now
                                     # carries ~8.7k context tokens instead of ~3k, so it costs ~$0.0014
                                     # typical / ~$0.0024 worst case instead of ~$0.0004 / ~$0.0017.
RATE_LIMIT_TRUST_FORWARDED_FOR=true  # per-visitor quota scope from Caddy's X-Forwarded-For
NEXT_PUBLIC_DEMO_API_KEY=            # filled in after step 4
```

Cost math for the daily cap (thinking allowed, `LLM_MAX_TOKENS=4096`): reasoning
bills as ordinary output tokens at `deepseek-v4-flash` prices (`app/usage/costs.py`);
typical bursts are 150–500 tokens on a low single-digit % of calls, so a typical query
is ~$0.0014 at the current context budget (9k tokens, measured average 8.7k), so
600/day lands at ~$0.8/day per visitor. The worst case — full context plus a 4096-token
completion — is ~$0.0024, i.e. **~$1.4/day per visitor at 600/day (accepted)**. Re-derive
after changing `CONTEXT_TOKEN_BUDGET`, `RERANK_TOP_N` or the model: context size is now
the dominant term, not the completion.

## 3. First start

```bash
docker compose -f docker-compose.prod.yml -f deploy/docker-compose.deploy.yml up -d --build
```

Migrations run on API start (fine for a single instance; use a dedicated migrate job
before scaling to replicas). Caddy fetches certificates automatically.

## 4. Seed the demo corpus

Two caveats discovered on the first real deploy:

- the production image ships only `app/` — copy `scripts/` and a locally built
  `corpus/build/` into the container (`python -m scripts.build_corpus` also cannot run
  in the image: the `markdown` dependency is dev-only);
- seed with `DEMO_MODE=false`: the demo sandbox cap (5 files/collection) otherwise
  rejects the corpus upload itself. Flip it back to `true` right after.

```bash
# on the workstation: uv run python -m scripts.build_corpus && scp -r corpus/build <host>:/tmp/corpus-build
sed -i 's/^DEMO_MODE=true/DEMO_MODE=false/' .env && docker compose -f docker-compose.prod.yml up -d api
docker exec -u 0 <api container> mkdir -p /app/corpus
docker cp scripts <api container>:/app/scripts && docker cp /tmp/corpus-build <api container>:/app/corpus/build
docker compose -f docker-compose.prod.yml exec api \
  python -m scripts.seed_demo --api http://localhost:8000 --readonly
sed -i 's/^DEMO_MODE=false/DEMO_MODE=true/' .env && docker compose -f docker-compose.prod.yml up -d api
```

Copy the printed API key into `NEXT_PUBLIC_DEMO_API_KEY` in `.env`, note the sandbox
collection id, then rebuild the UI (the key is baked at build time):

```bash
docker compose -f docker-compose.prod.yml -f deploy/docker-compose.deploy.yml up -d --build ui
```

### 4b. Corpus v2 (`kranich`, 298 documents) and the access-levels patch of the v1 set

Build both on the workstation, copy them over, then seed through the API from inside the
container (same caveats as above: `DEMO_MODE=false` while seeding, and `RATE_LIMIT_ENABLED=false`
unless you are happy to wait 30 minutes for the upload limiter). `ACCESS_REVEAL_HIDDEN=true`
stays on afterwards — it powers the "not available at your access level / view as …" panel
(the compose file passes it through explicitly; a variable that is only in `.env` never reaches the container).

```bash
# workstation
uv run python -m scripts.build_corpus                                   # v1 (now with restricted sections)
uv run python -m scripts.build_corpus --src corpus/large/docs --out corpus/large/build \
    --manifest corpus/large/manifest.yaml                               # v2
mkdir -p /tmp/corpus-build-en && cp corpus/build/* /tmp/corpus-build-en/ && rm /tmp/corpus-build-en/*-DE.*
scp -r /tmp/corpus-build-en <host>:/tmp/corpus-build-en && scp -r corpus/large/build <host>:/tmp/corpus-large-build

# server
grep -q ^ACCESS_REVEAL_HIDDEN .env || echo ACCESS_REVEAL_HIDDEN=true >> .env
sed -i 's/^DEMO_MODE=true/DEMO_MODE=false/' .env; echo RATE_LIMIT_ENABLED=false >> .env
C="docker compose -f docker-compose.prod.yml -f deploy/docker-compose.shared-host.yml"; $C up -d api
docker exec -u 0 docqa-api-1 mkdir -p /app/corpus/large
docker cp scripts docqa-api-1:/app/ && docker cp /tmp/corpus-build-en docqa-api-1:/app/corpus/build \
    && docker cp /tmp/corpus-large-build docqa-api-1:/app/corpus/large/build
KEY=$(grep ^NEXT_PUBLIC_DEMO_API_KEY= .env | cut -d= -f2)
$C exec -T api python -m scripts.corpus_v2.seed --api http://localhost:8000 --api-key "$KEY" \
    --slug kranich --name "Kranich (300 docs, EN+DE)" --build /app/corpus/large/build
$C exec -T api python -m app.cli mark-readonly --collection-id <policies-en id> --writable
$C exec -T api python -m scripts.corpus_v2.seed --api http://localhost:8000 --api-key "$KEY" \
    --slug policies-en --build /app/corpus/build                          # re-uploads only the changed files
$C exec -T api python -m app.cli mark-readonly --collection-id <policies-en id>
$C exec -T api python -m app.cli mark-readonly --collection-id <kranich id>
sed -i 's/^DEMO_MODE=false/DEMO_MODE=true/; /^RATE_LIMIT_ENABLED=false/d' .env; $C up -d api
```

Suggested questions regenerate on their own once each collection settles (one `deepseek-chat`
call per collection); the seeder prints per-label chunk counts so you can see the restricted
sections landed.

## 5. Cron: backups and the sandbox wipe

Resolve the sandbox collection id once (seed_demo also prints it in step 4):

```bash
SANDBOX_ID=$(docker compose -f /opt/docqa/docker-compose.prod.yml exec -T db \
  psql -U docqa -d docqa -tA -c "select id from collections where slug='sandbox'")
echo "$SANDBOX_ID"   # paste into the wipe line below
```

```cron
0 3 * * * docker exec docqa-db pg_dump -U docqa docqa | gzip > /backup/docqa-$(date +\%F).sql.gz && find /backup -mtime +7 -delete
30 3 * * * docker compose -f /opt/docqa/docker-compose.prod.yml exec -T api python -m app.cli wipe-collection --collection-id <SANDBOX_ID>
```

Optionally sync `/backup` to object storage with rclone.

## 6. Checks

- `https://docqa.example.com/readyz` → `{"status": "ok"}`
- `https://app.docqa.example.com` → preset question streams an answer with citations
- upload to a policies collection → 403 `demo_readonly`; sandbox accepts ≤ 5 files ≤ 5 MB

## Variant: a host that already has an ingress on 80/443

When the box runs other projects behind an existing reverse proxy, skip the bundled
Caddy: use `deploy/docker-compose.shared-host.yml` instead of the deploy overlay. It
publishes the API on `127.0.0.1:${API_HOST_PORT:-8100}` and the UI on
`127.0.0.1:${UI_HOST_PORT:-3100}`; point the host ingress at those two ports
(`DOCQA_DOMAIN` → API port, `DOCQA_APP_DOMAIN` → UI port) and let it terminate TLS.
Everything else in this runbook (seed, key, crons, checks) is unchanged.

## Known limits

- Single instance; migrations at startup. Multi-instance needs a migrate job + shared storage for `data/`.
- `NEXT_PUBLIC_*` are build-time: changing the demo key or API URL means rebuilding the UI image.
