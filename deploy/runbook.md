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
EMBEDDING_PROVIDER=openai            # or ollama if the box runs one
OPENAI_API_KEY=…
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash          # current DeepSeek model; deepseek-chat is deprecated
LLM_API_KEY=…
RERANK_PROVIDER=none                 # cohere + COHERE_API_KEY for better precision
NEXT_PUBLIC_DEMO_API_KEY=            # filled in after step 4
```

Demo quotas: tighten per-key limits via `RATE_LIMIT_QUERY_PER_MINUTE=10`.

## 3. First start

```bash
docker compose -f docker-compose.prod.yml -f deploy/docker-compose.deploy.yml up -d --build
```

Migrations run on API start (fine for a single instance; use a dedicated migrate job
before scaling to replicas). Caddy fetches certificates automatically.

## 4. Seed the demo corpus

```bash
docker compose -f docker-compose.prod.yml exec api \
  python -m scripts.build_corpus
docker compose -f docker-compose.prod.yml exec api \
  python -m scripts.seed_demo --api http://localhost:8000 --readonly
```

Copy the printed API key into `NEXT_PUBLIC_DEMO_API_KEY` in `.env`, note the sandbox
collection id, then rebuild the UI (the key is baked at build time):

```bash
docker compose -f docker-compose.prod.yml -f deploy/docker-compose.deploy.yml up -d --build ui
```

## 5. Cron: backups and the sandbox wipe

```cron
0 3 * * * docker exec docqa-db pg_dump -U docqa docqa | gzip > /backup/docqa-$(date +\%F).sql.gz && find /backup -mtime +7 -delete
30 3 * * * docker compose -f /opt/docqa/docker-compose.prod.yml exec -T api python -m app.cli wipe-collection --collection-id <SANDBOX_ID>
```

Optionally sync `/backup` to object storage with rclone.

## 6. Checks

- `https://docqa.example.com/readyz` → `{"status": "ok"}`
- `https://app.docqa.example.com` → preset question streams an answer with citations
- upload to a policies collection → 403 `demo_readonly`; sandbox accepts ≤ 5 files ≤ 5 MB

## Known limits

- Single instance; migrations at startup. Multi-instance needs a migrate job + shared storage for `data/`.
- `NEXT_PUBLIC_*` are build-time: changing the demo key or API URL means rebuilding the UI image.
