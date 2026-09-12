# Deployment and recovery runbook

The production stack is Caddy (or an existing ingress), UI, API, a prefork Celery worker,
one Celery beat scheduler, PostgreSQL 18/pgvector, and Redis. PostgreSQL and Redis have no
published ports. The base API mapping is loopback-only. Use one Compose project consistently;
changing its project name creates different generated volume/container names.

## 1. Configuration and identities

Create a private `.env` beside `docker-compose.prod.yml` (`chmod 600 .env`). Generate **two
distinct URL-safe passwords**, for example with `openssl rand -hex 32`; do not put credentials
in shell history or paste resolved `docker compose config` output into logs. Both password
variables are required: there is no development-password fallback in production Compose.

```dotenv
# Fresh installation only: for existing deployments retain their current project name.
COMPOSE_PROJECT_NAME=docqa
POSTGRES_PASSWORD=<admin password, URL-safe>
POSTGRES_APP_PASSWORD=<different runtime password, URL-safe>
DOCQA_IMAGE=docqa:<reviewed release tag>
DOCQA_DOMAIN=api.docqa.example.com
DOCQA_APP_DOMAIN=docqa.example.com
DEMO_MODE=true
ACCOUNTS_ENABLED=true
NEXT_PUBLIC_ACCOUNTS_ENABLED=true
NEXT_PUBLIC_DEMO_API_KEY=
PUBLIC_TENANT_ID=<existing service tenant UUID for reviewed public collections>
BUDGET_ENABLED=true
BUDGET_DAILY_USD=0.50
BUDGET_IP_SECRET=<stable independent random secret, at least 32 characters>
SMTP_HOST=<mail server>
SMTP_PORT=587
SMTP_USERNAME=<mail account>
SMTP_PASSWORD=<private mail password>
SMTP_FROM=<verified sender address>
SERVICE_OPERATOR_CONTACT=<public operator contact>
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<private provider key>
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1024
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=<private provider key>
LLM_MAX_TOKENS=4096
LLM_TIMEOUT_S=180
REFUSAL_THRESHOLD=0.28
RERANK_TOP_N=40
CONTEXT_TOKEN_BUDGET=18000
RERANK_PROVIDER=none
RATE_LIMIT_ENABLED=true
RATE_LIMIT_QUERY_PER_MINUTE=10
RATE_LIMIT_QUERY_PER_DAY=0
RATE_LIMIT_TRUST_FORWARDED_FOR=true
ACCESS_ROLES='{"employee":["all"],"manager":["all","managers"],"hr":["all","managers","hr"],"finance":["all","managers","finance"],"leadership":["all","managers","hr","finance","leadership"]}'
ACCESS_DEFAULT_ROLE=employee
ACCESS_REVEAL_HIDDEN=true
```

Provider selection and the 0.28 threshold retain the measured OpenAI setup; use the recorded
eval for the corpus/model being served. The PostgreSQL ledger enforces $0.50/day for each
account and visitor IP, including guest spending before login. It fails closed when admission
cannot be verified. There is no global monetary cap, as requested by the operator. See
[billing](../docs/billing.md). Keep forwarded-IP trust off unless ingress replaces untrusted
headers. The deploy overlays set exact HTTPS session origins; verify these match the UI URL.

Before serving private uploads, provision and verify the independent storage/replication
topology in [durability.md](durability.md). Base Compose's single local volume alone does not
satisfy host-loss durability. Test SMTP with operator-controlled addresses before opening
registration. An absent SMTP configuration leaves registration unavailable, not simulated.

Compose explicitly passes access roles, demo mode/caps, upload/page limits, rate limits,
idempotency TTL, embedding/chunk/retrieval/reranking settings, LLM temperature/token/timeout/
context limits, suggestions, CORS and log level. Defaults are visible in `x-app-env`.
`STORAGE_DIR=/app/data/files` is fixed in the production topology so the backup covers it.
An arbitrary host `.env` variable is not automatically passed into a container.

Database identities:

| Identity | Purpose | Authority |
| --- | --- | --- |
| `docqa` | PostgreSQL bootstrap, one-shot migrations, operator backup/restore | Admin/schema owner; its password exists only in DB and migrate container configuration |
| `docqa_app` | API, worker, beat and normal application CLI | CRUD on application tables and sequence usage; no ownership, superuser, role management, schema creation, temporary tables, TRUNCATE, or migration-version modification |

Fresh PostgreSQL volumes run `deploy/db/init-runtime.sh`. The dedicated `migrate` service runs
Alembic then `deploy/db/runtime-grants.sql`; runtime services require successful migration.
Grants are reapplied after each schema update. Existing elevated memberships or ownership of
`docqa_app` cause the grant step to fail instead of silently retaining excessive authority.

## 2. Fresh start and release

Use Bash arrays so paths and arguments remain intact:

```bash
cd /opt/docqa
compose=(docker compose --env-file .env -f docker-compose.prod.yml -f deploy/docker-compose.deploy.yml)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build --wait
"${compose[@]}" ps
```

For a host with an existing ingress, replace the second file with
`deploy/docker-compose.shared-host.yml`. It exposes API/UI only on
`127.0.0.1:${API_HOST_PORT:-8100}` and `127.0.0.1:${UI_HOST_PORT:-3100}`. Point the existing ingress
at those ports. The bundled Caddy variant obtains TLS automatically; verify DNS and reachability
before release. Never expose the base API directly when trusting forwarded headers.

There must be **one beat scheduler** per deployment. The worker does not run beat implicitly.
Beat republishes due pending uploads and expired processing leases every minute. `/readyz`
checks PostgreSQL and Redis; Compose uses it for API health, and checks worker ping and beat
process liveness. Beat liveness alone does not prove recovery progress: monitor stale documents.

On a later release, serialize migration with application writers: create and verify the backup
below, stop `beat api worker`, build the reviewed image, run
`"${compose[@]}" run --rm migrate`, then `"${compose[@]}" up -d --wait api worker beat ui`.
Do not run migrations from an API entrypoint or overlap an operator/seed job with this sequence.
Retain the previous **image and configuration** separately for rollback; a Git tag alone does
not reproduce downloaded image/dependency contents. Run backward-compatibility checks before
restarting an older image against an additive migrated schema. Do not downgrade a live database
as an automatic rollback step; restore a verified backup into a new target if required.

## 3. Existing database volumes: operator migration only

The init script does not rerun for existing volumes. Updating Compose does not change the
stored admin password, create the runtime role, or remove historic grants. **Do not delete the
volume or run `down --volumes` on an existing deployment.**

1. Record the running image IDs, Compose project name, database version, migration revision,
   actual volume names and schema/role ownership. Do not publish environment or secret values.
2. Obtain a verified DB/files backup and rehearse it with `restore-check` on a safe machine.
   Preserve private configuration separately. Confirm the maintenance window and rollback owner.
3. Stop application writers and any seed/admin jobs. Keep the existing admin password in
   `POSTGRES_PASSWORD`; add a new distinct `POSTGRES_APP_PASSWORD` to the private environment.
4. Review `docqa_app` if it already exists. With the approved environment supplied to the DB
   container, an operator may run the mounted bootstrap script explicitly:

   ```bash
   "${compose[@]}" up -d db
   "${compose[@]}" exec -T db sh /docker-entrypoint-initdb.d/10-docqa-runtime.sh
   "${compose[@]}" run --rm migrate
   "${compose[@]}" up -d --wait api worker beat
   ```

   The bootstrap creates a missing role; it intentionally does not rotate an existing role's
   password. Existing-role rotation and ownership reassignment require a reviewed operator SQL
   procedure, followed by the same grants and a runtime-role test. The migration grants assume
   schema owner `docqa`, matching this repository's deployment; inspect divergent installations.
5. Confirm runtime login has no elevated role flags/memberships or owned schema objects, and
   exercise collection create (outside demo mode), upload/ingestion, query, original read and
   permitted delete. Verify a runtime connection cannot CREATE/ALTER/DROP/TRUNCATE application
   objects or write `alembic_version`. Keep the admin credential out of API/worker/beat.

These steps are instructions for an authorized maintenance window, not permission to modify
an existing environment. Local disposable rehearsals do not establish existing production grants.

## 4. Corpus provisioning

Migration 0009 leaves all existing collections private. Review corpus provenance and
content, configure its service tenant as `PUBLIC_TENANT_ID`, then explicitly publish:

```bash
"${compose[@]}" exec -T api python -m app.cli publish-collection --collection-id <reviewed UUID>
```

This makes it read-only. Personal-tenant collections cannot be published by this command.
Use `--private` to withdraw publication; it remains read-only until an explicit separate
operator change. Do not reuse old browser demo keys: the account UI uses session cookies.
Revoke every former public demo key with `python -m app.cli revoke-key --prefix <prefix>`
before reopening the service. Removing a key from the UI does not invalidate copies
visitors already obtained. Existing service-tenant data has no inferred personal owner;
review it separately and keep it unpublished until its provenance and access are resolved.
Disable any old nightly sandbox job that addresses user data; `wipe-collection` now refuses
personal or published collections. User originals have no automatic expiry.

The backend image ships `app/` and migrations, not corpus builders. Build PDF/DOCX files on the
workstation. Temporarily turn `DEMO_MODE=false` in the private environment while the operator
seeds; restore demo mode immediately afterwards. `RATE_LIMIT_ENABLED=false` is an operator-only
seeding override, never a steady-state demo setting.

```bash
"${compose[@]}" up -d api
"${compose[@]}" cp scripts api:/app/scripts
"${compose[@]}" exec -T --user root api mkdir -p /app/corpus
"${compose[@]}" cp /tmp/corpus-build api:/app/corpus/build
"${compose[@]}" exec -T api python -m scripts.seed_demo --api http://localhost:8000 --readonly
```

The seeder prints a public demo key once. Put it in `NEXT_PUBLIC_DEMO_API_KEY` privately and
rebuild the UI after restoring demo mode. `NEXT_PUBLIC_*` values are baked into the UI bundle.
For corpus v2, build with `scripts.build_corpus --src corpus/large/docs --out corpus/large/build
--manifest corpus/large/manifest.yaml`, copy with `compose cp`, and use `scripts.corpus_v2.seed`.
`mark-readonly` / `reprocess` remain operator CLI commands; use collection IDs verified in the
intended tenant, and do not overlap provisioning or reprocessing with a backup.

## 5. Consistent database and original-file backups

The old `docker exec docqa-db pg_dump | gzip` cron is insufficient: it guesses a container name,
misses originals, and can report success after a failed dump. Replace it only after the operator
chooses schedule, secure destination, retention, off-host copy/encryption and failure recipient.
No backup deletion policy or notification recipient is installed by this repository.
The scripts require Python 3.12 and Docker Compose on the Linux operator host.

```bash
python3 deploy/scripts/backup.py backup /secure/docqa-backups/2026-09-10T120000Z \
  --project-directory /opt/docqa --env-file /opt/docqa/.env \
  --compose-file /opt/docqa/docker-compose.prod.yml \
  --compose-file /opt/docqa/deploy/docker-compose.shared-host.yml
python3 deploy/scripts/backup.py verify /secure/docqa-backups/2026-09-10T120000Z
```

This command causes application downtime. It stops beat, drains/stops API and worker, refuses
remaining database clients, captures a custom-format `pg_dump` and `/app/data` tar archive,
checks every committed document's original against its SHA-256, and restarts only services that
were originally running. A host lock rejects overlapping backups for the same user and Compose
project, even when their destinations differ. Do not run backups from multiple hosts/users, or
overlap migrations, manual SQL, seed or cleanup jobs; all writers must observe the maintenance
window. Backend hard limits and a 660-second
stop allowance bound normal draining; a forced worker stop leaves a persisted lease for recovery.

A complete bundle contains `database.dump`, `files.tar.gz`, and `manifest.json` with artifact
checksums, migration revision, image IDs, application-table counts and timestamps. Credentials/resolved
Compose configuration are excluded. The directory is private (0700; files subject to umask 077).
Errors are fatal, including failure to resume services; `.incomplete-*` bundles are not successful
backups. Inspect failure output and service health immediately. Backups contain document/query
content and key hashes; protect access and use operator-approved encryption/off-host storage.
Redis is not restored: old cached answers/idempotency responses must not return, and the DB
recovery scheduler recreates pending ingestion work. Account for any old Redis URL during cutover.

Nightly sandbox cleanup remains an explicit operator-scheduled
`compose exec -T api python -m app.cli wipe-collection --collection-id <verified sandbox UUID>`.
It must not overlap backup/provisioning. Check its exit status; a failed cache/file cleanup is
not a successful reset. The operator must resolve backup-retention exceptions to deletion promises.

## 6. Restore rehearsal and recovery

```bash
# Uses only already-present PostgreSQL image; no production connections or published ports.
python3 deploy/scripts/backup.py restore-check /secure/docqa-backups/2026-09-10T120000Z \
  --postgres-image pgvector/pgvector:pg18
```

The rehearsal first verifies checksums, then creates uniquely named containers/volumes with
`--network=none`. It restores using `pg_restore --exit-on-error --no-owner --no-privileges`,
restores originals into a new volume, checks bytes read back from that volume against every DB
reference, and checks migration revision and every application-table count. It reports measured restore duration and removes
only those new resources. It never mounts a current application's volume. Verify artifact trust
before restoring: checksums detect corruption, not a maliciously replaced bundle or executable SQL.

For an actual incident: select the operator-approved recovery point, isolate the old deployment,
restore the verified pair into a **new target**, bootstrap/reapply runtime grants, use clean Redis,
apply only reviewed forward migrations, and start the corresponding application image against it.
Test readiness, restricted/original access, citations and permitted mutations before ingress cutover.
Keep the old target intact until the incident owner approves disposal. This manual cutover and
production restoration require separate authorization; the disposable tool performs neither.
A successful synthetic restore measures a drill, not the production RPO/RTO or a user's backup.

## 7. Monitoring and release evidence

Docker's `local` logging driver is bounded to five 10 MB files per service. This is a capacity
limit, **not** a time-based retention guarantee. Choose central log retention/access separately.
Health checks do not deliver alerts or automatically repair all unhealthy containers.

```bash
python3 deploy/scripts/check_health.py \
  --project-directory /opt/docqa --env-file /opt/docqa/.env \
  --compose-file /opt/docqa/docker-compose.prod.yml \
  --compose-file /opt/docqa/deploy/docker-compose.shared-host.yml \
  --backup-directory /secure/docqa-backups \
  --max-backup-age-seconds <operator threshold> \
  --max-ingestion-age-seconds <operator threshold>
```

The probe reports JSON and exits nonzero for unhealthy/missing core services, stale ingestion,
missing/corrupt backups or an overdue backup. It sends no messages. The operator must connect
nonzero status and backup/cleanup failures to an approved monitoring route, name the recipient,
and demonstrate receipt with a controlled fault. Record observed detection and response times.
Until the owner supplies RPO/RTO, retention, recipient and a real backup sample, those production
acceptance items remain **unverified**, even when isolated tests pass.

CI runs backend lint/types/integration tests, UI clean installation/typecheck/build and mocked
Chromium regressions for both keyless and demo builds. Main-branch image jobs build backend/UI;
these jobs do not publish or deploy images. For a release, retain build identifiers and the exact
verification artifacts, inspect `/readyz`, run a real authorized provider/corpus sample, and verify
TLS, ingress headers/CORS/forwarded IP and end-to-end UI behavior in the actual deployment.

References: [Compose startup dependencies](https://docs.docker.com/compose/how-tos/startup-order/),
[PostgreSQL grants](https://www.postgresql.org/docs/18/sql-grant.html),
[pg_restore options](https://www.postgresql.org/docs/18/app-pgrestore.html).
