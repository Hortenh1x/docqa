# Private data durability and independent copies

The release target is preservation of **acknowledged** records if one application/database
host is lost. Downtime is acceptable. PostgreSQL must confirm synchronous replication,
and original files must be confirmed in independent versioned object storage, before an
upload can return success. Daily dumps alone do not satisfy this target.

The Oracle deployment uses a synchronous standby in another availability domain and
private versioned object storage. Dated production checks and restore results are recorded
in `audit/evidence/production-2026-09-12/`; repeat the relevant checks when changing the
deployment. Two containers on one test host demonstrate protocol behavior only.

## Original files

`STORAGE_PROVIDER=s3` uses a private S3-compatible bucket outside the application host.
Provide `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` and, for an
alternative S3 service, an HTTPS `S3_ENDPOINT_URL`. The service's S3 API must support
SHA-256 checksums and versioned objects. Enable bucket versioning and default encryption;
block public access and forbid public bucket policies/ACLs. Configure these in the storage
account, then verify them using the provider's controls. Do not expose bucket credentials
or object URLs to browsers.

Use a runtime identity restricted to this bucket: `GetBucketVersioning`, `GetObject`,
`PutObject`, `DeleteObject`; omit `DeleteObjectVersion`, bucket-policy changes, versioning
changes and bucket deletion. A separate recovery identity can read old versions. Protect
those credentials independently. Do not configure automatic expiration of current
originals or non-current versions until a retention policy is explicitly chosen.

For an S3-compatible service that omits the `DeleteMarker` response header (including
Oracle), also permit `ListBucketVersions`. The adapter confirms that the returned version
is the latest delete marker for the exact key before evicting its cache. This permission
does not authorize deletion of historical versions.

Each object key is `{tenant_uuid}/{sha256}.{verified_format}`. Upload checks the source
hash, confirms bucket versioning and a non-null returned version, then records the
document in PostgreSQL. Failed/uncertain uploads are not acknowledged; an unreferenced
remote version can remain for later operator reconciliation. In S3 mode `STORAGE_DIR`
is a verified parser/download cache: loss of that cache triggers a fresh download and
SHA verification. Runtime deletion creates a versioned delete marker and removes the
cache; it never permanently deletes an object version. The UI explains backup retention.

Local mode fsyncs the file and containing directories before upload acknowledgment.
It protects against interrupted writes but cannot survive loss of the host/disk.

Before switching an existing installation to S3, stop application writers and run the
explicit migration with the **existing files volume attached**:

```bash
docker compose -f docker-compose.prod.yml stop beat api worker
docker compose -f docker-compose.prod.yml run --rm --no-deps api python -m app.storage.migrate_originals
```

The command copies every referenced original, verifies its independent bytes, and leaves
local originals in place. Re-running can create additional identical remote versions;
it does not erase old data or guess ownership. Merely changing `STORAGE_PROVIDER` does
not migrate old local originals. All these commands require the same project and overlays
as the installation; include them consistently.

## PostgreSQL standby on an independent host

Use an independent machine/storage failure domain, the same CPU architecture, PostgreSQL
major/minor version and pgvector image as the primary. Restrict network access to the
private/VPN addresses. The provided overlay enables TLS; replication validates the
primary's TLS hostname against a trusted CA.

1. Provision a second host and record both failure domains in the deployment inventory.
   Prepare a trusted primary certificate/key as `server.crt`/`server.key` in `PG_TLS_DIR`;
   the private key must be readable only by PostgreSQL (0600 and the image's postgres UID).
   Set `PG_PRIVATE_BIND` to the primary's private address.
2. Stop application writers. For initial TLS/replication bootstrap only, start the
   primary with an empty standby-name setting; never expose application writes in this phase:

   ```bash
   PG_SYNCHRONOUS_STANDBY_NAMES= docker compose -f docker-compose.prod.yml -f deploy/docker-compose.synchronous.yml up -d db
   ```

3. Through an authenticated administrator session create a dedicated replication role:
   `CREATE ROLE docqa_replicator WITH REPLICATION LOGIN;` then set its password using
   the interactive `\password docqa_replicator` command. Add a narrow primary `pg_hba.conf`
   entry: `hostssl replication docqa_replicator <standby-private-ip>/32 scram-sha-256`,
   and reload PostgreSQL. Do not give the runtime application replication privileges.
4. On the standby host prepare `PG_REPLICATION_SECRET_DIR/ca.crt` and a postgres-readable
   `pgpass` file (0600) containing the primary host/port, database `replication`, username
   and replication password. Escape colon/backslash characters using libpq's pgpass
   format. Secrets must not be passed through shell command-line literals or logs.
5. Create a **new** Docker volume named by `PG_STANDBY_VOLUME`. In a disposable container
   of the exact database image, mount that volume at `/var/lib/postgresql`, mount the
   secret directory read-only at `/run/replication`, create the image's PGDATA directory
   owned by postgres, and run as postgres:

   ```text
   pg_basebackup --dbname="host=<primary-tls-hostname> port=5432 user=docqa_replicator application_name=docqa_standby sslmode=verify-full sslrootcert=/run/replication/ca.crt passfile=/run/replication/pgpass" -D /var/lib/postgresql/18/docker -R -X stream -C -S docqa_standby
   ```

   The supplied PostgreSQL 18 image uses `/var/lib/postgresql/18/docker`; verify PGDATA
   if changing images. `-C` creates the physical slot; if a failed bootstrap left the
   slot, inspect it rather than blindly dropping it. Never run basebackup into an
   existing populated volume.
6. Set `PG_PRIMARY_HOST`, `PG_REPLICATION_SECRET_DIR`, `PG_STANDBY_VOLUME` and start
   `deploy/docker-compose.standby.yml` on the second host. Check recovery is active and
   the primary sees `application_name=docqa_standby`, `state=streaming`.
7. Remove the temporary empty bootstrap variable and recreate the primary with the
   synchronous overlay. Its default is `FIRST 1 (docqa_standby)` and
   `synchronous_commit=on`. Confirm `sync_state=sync`. A missing standby must block
   commits, not cause a fallback to local-only acknowledgment.
8. As the administrator-configured migrate service, run the read-only release check:

   ```bash
   docker compose -f docker-compose.prod.yml -f deploy/docker-compose.synchronous.yml run --rm --no-deps migrate python -m deploy.scripts.check_durability
   ```

   This checks fsync/full-page writes, synchronous settings, a streaming synchronous
   standby, bucket versioning and every committed original's independent bytes.
   It cannot prove physical independence or bucket access policy: verify those in the
   deployment inventory/provider controls. Restart writers only after those checks pass.

Monitor standby connectivity, replication lag, disk free space and physical-slot WAL
retention. An offline replica can retain WAL until the primary fills its disk; alert
early and restore replication. Do not disable fsync, synchronous commits or the standby
requirement as an availability workaround. Client timeouts can leave an uncertain
locally committed transaction: use idempotency/deduplication and inspect state before
repeating an operation. No provider call begins before its quota reservation commits.

## Backups, restoration and failover

Keep scheduled DB+original bundles in addition to the live standby. `backup.py` quiesces
writers, hydrates missing originals from S3, verifies their hashes, dumps the complete
schema and data, and records counts including accounts, sessions, tokens, ownership and
spending tables. Its offline restore creates new isolated resources and verifies restored
rows and bytes. Keep encrypted copies of backup bundles off the primary host with a
separate recovery identity; retain the stable `BUDGET_IP_SECRET` in protected configuration
backups so releases/recovery do not reset IP allowances. Mail/storage credentials belong
in protected configuration, never manifests or the repository.

Replica failover is manual: fence the old primary so it cannot accept writes, verify the
standby and original store, promote the standby, and point the application at it. Before
accepting new writes, establish a new independent synchronous standby and TLS/access
configuration for the promoted server. Do not bring the old primary back as a competing
writer; rejoin it through a reviewed rewind/re-seed procedure. A current standby alone
cannot undo an operator's accidental deletion: restore a historical bundle into isolated
resources, verify it, then perform a deliberate recovery.

Do not schedule `wipe-collection` for personal accounts. The command rejects personal and
published collections even if passed their IDs. An AI failure, quota exhaustion, logout,
inactive account or elapsed time never deletes an original. Owners can explicitly retry
a failed document after the daily quota replenishes.

Local evidence: `deploy/tests/rehearse_replication.py` creates its own primary and standby,
acknowledges a write, takes the standby offline, proves the next commit waits, kills only
its test primary, promotes the standby and verifies the acknowledged row. The test removes
all resources it created. `deploy/tests/rehearse_ops.py` covers the actual application
backup/restore topology. Neither script establishes production host-loss resilience.

Reference semantics: [PostgreSQL synchronous replication](https://www.postgresql.org/docs/18/warm-standby.html#SYNCHRONOUS-REPLICATION),
[continuous archiving/PITR](https://www.postgresql.org/docs/18/continuous-archiving.html),
[S3 versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html),
[S3 PutObject checksum/version response](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html).
