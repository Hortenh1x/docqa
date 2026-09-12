#!/usr/bin/env python3
"""Quiesced Compose DB/files backups and restoration into NEW disposable resources.

No credentials or resolved Compose environment are written to a backup manifest.
The restore-check command never attaches to an existing database or storage volume.
"""

import argparse
import csv
import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ARTIFACTS = ("database.dump", "files.tar.gz")
WRITERS = ("beat", "api", "worker")
TABLES = (
    "tenants",
    "api_keys",
    "collections",
    "documents",
    "chunks",
    "queries",
    "query_citations",
    "users",
    "account_sessions",
    "account_tokens",
    "auth_attempts",
    "google_identities",
    "google_auth_states",
    "spend_reservations",
    "spend_allocations",
)


def counts_sql(tables=TABLES):
    if not tables or not set(tables).issubset(TABLES):
        raise ValueError("Backup contains unsupported table names")
    return (
        "SELECT json_build_object("
        + ",".join(f"'{table}', (SELECT count(*) FROM {table})" for table in tables)
        + ")"
    )


COUNTS_SQL = counts_sql()
EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/markdown": ".md",
    "text/plain": ".txt",
}


def run(command, *, stdin=None, stdout=subprocess.PIPE, check=True):
    result = subprocess.run(command, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE)
    if check and result.returncode:
        # Commands use service names and paths; do not dump Compose configuration/env.
        raise RuntimeError(
            f"{command[0]} exited {result.returncode}: {result.stderr.decode()[-2000:]}"
        )
    return result


def checksum(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_directory(path):
    """Reconfirm ancestors, including entries left by failed/concurrent creators."""
    path = path.absolute()
    if path.parent == path:
        return
    durable_directory(path.parent)
    path.mkdir(mode=0o700, exist_ok=True)
    sync_directory(path.parent)


def verify_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("format") != 1 or set(manifest.get("files", {})) != set(ARTIFACTS):
        raise ValueError("Unsupported or incomplete backup manifest")
    for name in ARTIFACTS:
        if checksum(directory / name) != manifest["files"][name]:
            raise ValueError(f"Backup checksum mismatch: {name}")
    return manifest


class Compose:
    def __init__(self, project_directory, files, env_file=None, project_name=None):
        self.command = [
            "docker",
            "compose",
            "--project-directory",
            str(Path(project_directory).resolve()),
        ]
        if env_file:
            self.command += ["--env-file", str(Path(env_file).resolve())]
        if project_name:
            self.command += ["--project-name", project_name]
        for file in files:
            self.command += ["--file", str(Path(file).resolve())]

    def call(self, *args, **kwargs):
        return run([*self.command, *args], **kwargs)

    def sql(self, sql):
        return (
            self.call(
                "exec",
                "-T",
                "db",
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "docqa",
                "-d",
                "docqa",
                "-At",
                "-c",
                sql,
            )
            .stdout.decode()
            .strip()
        )


def verify_originals(archive, references):
    """Validate paths and committed originals in one forward pass over gzip data."""
    expected = {
        f"files/{tenant_id}/{digest}{EXTENSIONS[mime_type]}": digest
        for tenant_id, digest, mime_type in references
    }
    source = {"fileobj": archive} if hasattr(archive, "read") else {"name": archive}
    verified = set()
    seen = set()
    with tarfile.open(mode="r|gz", **source) as files:
        for member in files:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError("Unsafe file archive member")
            name = str(path)
            if name in seen:
                raise ValueError("Unsafe duplicate file archive member")
            seen.add(name)
            if name not in expected or not member.isfile():
                continue
            with files.extractfile(member) as original:
                if hashlib.file_digest(original, "sha256").hexdigest() != expected[name]:
                    raise ValueError(f"Original content hash mismatch: {path}")
            verified.add(name)
    if missing := expected.keys() - verified:
        raise ValueError(f"Missing original for a committed document: {min(missing)}")


REFERENCE_SQL = (
    "COPY (SELECT c.tenant_id, d.sha256, d.mime_type FROM documents d "
    "JOIN collections c ON c.id=d.collection_id) TO STDOUT WITH CSV"
)


@contextmanager
def project_lock(project):
    """Serialize backups of one Compose project even with different destinations."""
    project_hash = hashlib.sha256(project.encode()).hexdigest()[:24]
    path = Path(tempfile.gettempdir()) / f"docqa-backup-{os.getuid()}-{project_hash}.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("A backup is already running for this Compose project") from error
        yield


def backup(compose, destination):
    config = json.loads(compose.call("config", "--format", "json").stdout)
    with project_lock(config["name"]):
        _backup(compose, destination, config)


def _backup(compose, destination, config):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Backup destination already exists; choose a new bundle directory")
    durable_directory(destination.parent)
    staging = destination.with_name(destination.name + ".incomplete-" + uuid.uuid4().hex[:8])
    staging.mkdir(mode=0o700)
    sync_directory(staging.parent)
    running = compose.call("ps", "--status", "running", "--services").stdout.decode().split()
    if "migrate" in running:
        raise ValueError("Migration is running; retry after the release has completed")
    writers = [service for service in WRITERS if service in running]
    manifest = {
        "format": 1,
        "started_at": datetime.now(UTC).isoformat(),
        "project": config["name"],
        "postgres_image": config["services"]["db"]["image"],
        "quiesced_services": writers,
        "images": {},
    }
    try:
        # Stop beat first, then drain API/worker within the configured hard-limit envelope.
        if "beat" in writers:
            compose.call("stop", "--timeout", "30", "beat")
        active_writers = [service for service in writers if service != "beat"]
        if active_writers:
            compose.call("stop", "--timeout", "660", *active_writers)
        remaining = compose.call("ps", "--status", "running", "--services").stdout.decode().split()
        if any(service in remaining for service in WRITERS):
            raise RuntimeError("Application writers did not stop")
        if int(
            compose.sql(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid() AND backend_type='client backend' "
                "AND application_name<>'pg_isready'"
            )
        ):
            raise RuntimeError("Other DB clients remain; suspend admin/seed jobs before backup")
        for service in ("api", "worker", "beat", "db"):
            ids = compose.call("ps", "--all", "--quiet", service).stdout.decode().split()
            if ids:
                manifest["images"][service] = (
                    run(["docker", "inspect", "--format", "{{.Image}}", ids[0]])
                    .stdout.decode()
                    .strip()
                )
        manifest["migration"] = compose.sql("SELECT version_num FROM alembic_version")
        manifest["table_counts"] = json.loads(compose.sql(COUNTS_SQL))
        references = list(csv.reader(io.StringIO(compose.sql(REFERENCE_SQL))))
        # S3 mode may have an empty cache after host replacement. Fetch every
        # committed original before tarring; fail rather than produce a partial bundle.
        compose.call(
            "run", "--rm", "--no-deps", "-T", "api", "python", "-m", "app.storage.snapshot"
        )
        with (staging / "database.dump").open("wb") as output:
            compose.call(
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "docqa",
                "-d",
                "docqa",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                stdout=output,
            )
            output.flush()
            os.fsync(output.fileno())
        with (staging / "files.tar.gz").open("wb") as output:
            compose.call(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--entrypoint",
                "tar",
                "api",
                "-czf",
                "-",
                "-C",
                "/app/data",
                ".",
                stdout=output,
            )
            output.flush()
            os.fsync(output.fileno())
        verify_originals(staging / "files.tar.gz", references)
        manifest["document_references"] = len(references)
        manifest["files"] = {name: checksum(staging / name) for name in ARTIFACTS}
        manifest["completed_at"] = datetime.now(UTC).isoformat()
        with (staging / "manifest.json").open("w") as output:
            output.write(json.dumps(manifest, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        verify_bundle(staging)
        sync_directory(staging)
    finally:
        # Restart only services this command stopped; a resume failure is also a failed backup job.
        if writers:
            compose.call("start", *writers)
    staging.rename(destination)
    sync_directory(destination.parent)
    print(json.dumps({"status": "ok", "bundle": str(destination), "documents": len(references)}))


def cleanup_restore(container, volumes):
    failures = []
    commands = [["docker", "rm", "--force", "--volumes", container]]
    commands += [["docker", "volume", "rm", volume] for volume in volumes]
    for command in commands:
        result = run(command, check=False)
        message = result.stderr.decode()
        # Resources may not have been created when startup failed early.
        if result.returncode and not any(
            absent in message.lower() for absent in ("no such container", "no such volume")
        ):
            failures.append(command[-1])
    if failures:
        raise RuntimeError("Disposable restore cleanup failed: " + ", ".join(failures))


def restore_check(directory, postgres_image):
    directory = Path(directory).resolve()
    manifest = verify_bundle(directory)
    # Validate paths before allowing tar to restore anything, even in a disposable volume.
    verify_originals(directory / "files.tar.gz", [])
    prefix = "docqa-restore-" + uuid.uuid4().hex[:12]
    volumes = [prefix + "-db", prefix + "-files"]
    started = time.monotonic()
    try:
        for volume in volumes:
            run(["docker", "volume", "create", volume])
        run(
            [
                "docker",
                "run",
                "--detach",
                "--pull=never",
                "--name",
                prefix,
                "--network=none",
                "--env",
                "POSTGRES_USER=docqa",
                "--env",
                "POSTGRES_DB=docqa",
                "--env",
                "POSTGRES_PASSWORD=" + uuid.uuid4().hex,
                "--mount",
                f"type=volume,source={volumes[0]},target=/var/lib/postgresql",
                postgres_image,
            ]
        )
        ready = False
        for _ in range(120):
            result = run(
                [
                    "docker",
                    "exec",
                    prefix,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "docqa",
                    "-d",
                    "docqa",
                ],
                check=False,
            )
            if result.returncode == 0:
                ready = True
                break
            time.sleep(0.5)
        if not ready:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        with (directory / "database.dump").open("rb") as source:
            run(
                [
                    "docker",
                    "exec",
                    "-i",
                    prefix,
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "-U",
                    "docqa",
                    "-d",
                    "docqa",
                ],
                stdin=source,
            )
        with (directory / "files.tar.gz").open("rb") as source:
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network=none",
                    "-i",
                    "--mount",
                    f"type=volume,source={volumes[1]},target=/restore",
                    "--entrypoint",
                    "tar",
                    postgres_image,
                    "-xzf",
                    "-",
                    "-C",
                    "/restore",
                ],
                stdin=source,
            )
        rows = run(
            [
                "docker",
                "exec",
                prefix,
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "docqa",
                "-d",
                "docqa",
                "-At",
                "-c",
                REFERENCE_SQL,
            ]
        ).stdout.decode()
        references = list(csv.reader(io.StringIO(rows)))
        # Check bytes read BACK from the restored volume, not just the source archive.
        with tempfile.TemporaryFile() as restored:
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network=none",
                    "--mount",
                    f"type=volume,source={volumes[1]},target=/restore,readonly",
                    "--entrypoint",
                    "tar",
                    postgres_image,
                    "-czf",
                    "-",
                    "-C",
                    "/restore",
                    ".",
                ],
                stdout=restored,
            )
            restored.seek(0)
            verify_originals(restored, references)
        migration = (
            run(
                [
                    "docker",
                    "exec",
                    prefix,
                    "psql",
                    "-X",
                    "-U",
                    "docqa",
                    "-d",
                    "docqa",
                    "-At",
                    "-c",
                    "SELECT version_num FROM alembic_version",
                ]
            )
            .stdout.decode()
            .strip()
        )
        if migration != manifest["migration"] or len(references) != manifest["document_references"]:
            raise ValueError("Restored database does not match backup manifest")
        counts = json.loads(
            run(
                [
                    "docker",
                    "exec",
                    prefix,
                    "psql",
                    "-X",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "docqa",
                    "-d",
                    "docqa",
                    "-At",
                    "-c",
                    counts_sql(manifest["table_counts"]),
                ]
            ).stdout
        )
        if counts != manifest["table_counts"]:
            raise ValueError("Restored table counts do not match backup manifest")
        report = {
            "status": "ok",
            "documents": len(references),
            "migration": migration,
            "restore_seconds": round(time.monotonic() - started, 3),
            "isolated": True,
        }
    finally:
        cleanup_restore(prefix, volumes)
    print(json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    take = sub.add_parser("backup", help="Stop application writers; back up DB and files; resume")
    take.add_argument("directory")
    take.add_argument("--project-directory", default=".")
    take.add_argument("--compose-file", action="append", required=True)
    take.add_argument("--env-file")
    take.add_argument("--project-name")
    verify = sub.add_parser("verify", help="Check bundle completeness and artifact SHA-256")
    verify.add_argument("directory")
    restore = sub.add_parser(
        "restore-check", help="Restore only into fresh disposable Docker resources"
    )
    restore.add_argument("directory")
    restore.add_argument("--postgres-image", default="pgvector/pgvector:pg18")
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "backup":
        backup(
            Compose(args.project_directory, args.compose_file, args.env_file, args.project_name),
            args.directory,
        )
    elif args.command == "verify":
        verify_bundle(args.directory)
        print(json.dumps({"status": "ok"}))
    else:
        restore_check(args.directory, args.postgres_image)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Backup operation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
