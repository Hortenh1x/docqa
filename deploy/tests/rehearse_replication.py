#!/usr/bin/env python3
"""Disposable two-PostgreSQL test: acknowledged commits survive primary loss.

Both containers are on this test host; this proves PostgreSQL behavior, not independent
production failure domains. No existing container or volume is addressed by this script.
"""

import json
import subprocess
import time
import uuid

IMAGE = "pgvector/pgvector:pg18"


def run(*command, data=None, check=True):
    result = subprocess.run(command, input=data, capture_output=True, timeout=60)
    if check and result.returncode:
        raise RuntimeError(
            f"Rehearsal command failed: {command[0]}: {result.stderr.decode()[-1000:]}"
        )
    return result


def sql(container, statement):
    return (
        run(
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "docqa",
            "-d",
            "docqa",
            "-At",
            data=statement.encode(),
        )
        .stdout.decode()
        .strip()
    )


def wait_for(check, message, seconds=40):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if check():
                return
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
        time.sleep(0.25)
    raise RuntimeError(message)


def main():
    prefix = "docqa-sync-test-" + uuid.uuid4().hex[:10]
    primary, standby = prefix + "-primary", prefix + "-standby"
    volumes = [prefix + "-primary-data", prefix + "-standby-data"]
    secret = uuid.uuid4().hex
    pending = None
    started = time.monotonic()
    try:
        run("docker", "network", "create", prefix)
        for volume in volumes:
            run("docker", "volume", "create", volume)
        run(
            "docker",
            "run",
            "-d",
            "--pull=never",
            "--name",
            primary,
            "--network",
            prefix,
            "--network-alias",
            "primary",
            "-e",
            "POSTGRES_USER=docqa",
            "-e",
            "POSTGRES_DB=docqa",
            "-e",
            "POSTGRES_PASSWORD=" + secret,
            "-v",
            volumes[0] + ":/var/lib/postgresql",
            IMAGE,
        )
        wait_for(lambda: sql(primary, "SELECT 1") == "1", "Primary did not start")
        sql(
            primary, "CREATE ROLE docqa_replicator WITH REPLICATION LOGIN PASSWORD '" + secret + "'"
        )
        run(
            "docker",
            "exec",
            primary,
            "sh",
            "-c",
            "printf '\nhost replication docqa_replicator all scram-sha-256\n' "
            '>> "$PGDATA/pg_hba.conf"',
        )
        sql(primary, "SELECT pg_reload_conf()")
        conninfo = (
            "host=primary user=docqa_replicator application_name=docqa_standby password=" + secret
        )
        run(
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network",
            prefix,
            "-v",
            volumes[1] + ":/var/lib/postgresql",
            "--entrypoint",
            "sh",
            IMAGE,
            "-ec",
            "mkdir -p /var/lib/postgresql/18/docker; "
            "chown -R postgres:postgres /var/lib/postgresql; "
            'exec gosu postgres pg_basebackup -d "$1" -D /var/lib/postgresql/18/docker '
            "-R -X stream -C -S docqa_standby",
            "seed",
            conninfo,
        )
        run(
            "docker",
            "run",
            "-d",
            "--pull=never",
            "--name",
            standby,
            "--network",
            prefix,
            "-v",
            volumes[1] + ":/var/lib/postgresql",
            IMAGE,
        )
        wait_for(lambda: sql(standby, "SELECT pg_is_in_recovery()") == "t", "Standby did not start")
        sql(primary, "ALTER SYSTEM SET synchronous_standby_names = 'FIRST 1 (docqa_standby)'")
        sql(primary, "SELECT pg_reload_conf()")
        wait_for(
            lambda: (
                sql(
                    primary,
                    "SELECT count(*) FROM pg_stat_replication "
                    "WHERE application_name='docqa_standby' AND sync_state='sync'",
                )
                == "1"
            ),
            "Standby did not become synchronous",
        )
        sql(primary, "CREATE TABLE acknowledged_rows (id int PRIMARY KEY, payload text NOT NULL)")
        sql(
            primary,
            "INSERT INTO acknowledged_rows VALUES (1, 'acknowledged account and quota fixture')",
        )
        wait_for(
            lambda: sql(standby, "SELECT count(*) FROM acknowledged_rows") == "1",
            "Acknowledged row was not replicated",
        )
        run("docker", "stop", "--time", "5", standby)
        pending = subprocess.Popen(
            [
                "docker",
                "exec",
                primary,
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "docqa",
                "-d",
                "docqa",
                "-c",
                "INSERT INTO acknowledged_rows VALUES (2, 'unacknowledged')",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        wait_for(
            lambda: (
                sql(primary, "SELECT count(*) FROM pg_stat_activity WHERE wait_event='SyncRep'")
                == "1"
            ),
            "Commit did not wait for absent synchronous standby",
        )
        assert pending.poll() is None, "Commit was acknowledged without its independent copy"
        run("docker", "kill", "--signal", "KILL", primary)
        pending.communicate(timeout=10)
        assert pending.returncode != 0
        run("docker", "start", standby)
        wait_for(
            lambda: sql(standby, "SELECT pg_is_in_recovery()") == "t", "Standby restart failed"
        )
        sql(standby, "SELECT pg_promote(false)")
        wait_for(lambda: sql(standby, "SELECT pg_is_in_recovery()") == "f", "Promotion failed")
        assert sql(standby, "SELECT id FROM acknowledged_rows ORDER BY id") == "1"
        print(
            json.dumps(
                {
                    "acknowledged_row_survived": True,
                    "offline_replica_blocked_commit": True,
                    "unacknowledged_row_not_reported_successful": True,
                    "primary_killed": True,
                    "scope": "isolated containers on one test host; not production independence",
                    "seconds": round(time.monotonic() - started, 2),
                }
            )
        )
    finally:
        if pending is not None and pending.poll() is None:
            pending.terminate()
            pending.communicate(timeout=10)
        failures = []
        for container in (primary, standby):
            result = run("docker", "rm", "--force", "--volumes", container, check=False)
            if result.returncode and b"No such container" not in result.stderr:
                failures.append("container")
        for volume in volumes:
            if run("docker", "volume", "rm", volume, check=False).returncode:
                failures.append("volume")
        if run("docker", "network", "rm", prefix, check=False).returncode:
            failures.append("network")
        if failures:
            raise RuntimeError("Rehearsal cleanup incomplete: " + ", ".join(failures))


if __name__ == "__main__":
    main()
