#!/usr/bin/env bash
# One-command dev stack: Postgres+Redis (docker), user-level ollama, Celery worker,
# API with reload, and the Next.js UI. Ctrl+C tears down everything it started.
#
#   ./scripts/dev.sh
#
# Embeddings default to OpenAI (cloud, parity with prod); the user-level ollama on
# 11435 is still started for legacy bge-m3 collections and the optional local LLM
# (the systemd instance does not see ~/.ollama models).
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d

if ! curl -sf --max-time 2 http://localhost:11435/api/version >/dev/null 2>&1; then
  OLLAMA_HOST=127.0.0.1:11435 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 \
    OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_KEEP_ALIVE=1h ollama serve \
    >"${TMPDIR:-/tmp}/docqa-ollama.log" 2>&1 &
fi

uv run alembic upgrade head

uv run celery -A app.workers.celery_app worker -Q ingestion -c 2 --loglevel=WARNING &
uv run uvicorn app.main:app --reload --no-access-log &

# next start needs a production build; build once, then reuse
[ -f ui/.next/BUILD_ID ] || npm --prefix ui run build
npm --prefix ui run start &

trap 'echo; echo "stopping the stack…"; docker compose stop >/dev/null 2>&1; kill 0' INT TERM

echo
echo "DocQA dev stack is up:"
echo "  UI   http://localhost:3002"
echo "  API  http://localhost:8000   (interactive docs: /docs)"
echo "  Ctrl+C stops everything (db/redis containers included)"
wait
