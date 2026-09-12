#!/usr/bin/env python3
"""Local monitoring probe. Emits JSON and nonzero on failure; sends no notifications."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from backup import Compose, run, verify_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-directory", default=".")
    parser.add_argument("--compose-file", action="append", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--project-name")
    parser.add_argument("--backup-directory", required=True)
    parser.add_argument("--max-backup-age-seconds", type=int, required=True)
    parser.add_argument("--max-ingestion-age-seconds", type=int, required=True)
    args = parser.parse_args()
    if min(args.max_backup_age_seconds, args.max_ingestion_age_seconds) <= 0:
        parser.error("Monitoring age limits must be positive; select them with the operator")
    compose = Compose(args.project_directory, args.compose_file, args.env_file, args.project_name)
    issues = []
    for service in ("db", "redis", "api", "worker", "beat"):
        ids = compose.call("ps", "--all", "--quiet", service).stdout.decode().split()
        if not ids:
            issues.append(f"{service}: missing")
            continue
        state = json.loads(run(["docker", "inspect", "--format", "{{json .State}}", ids[0]]).stdout)
        if not state["Running"] or state.get("Health", {}).get("Status") != "healthy":
            issues.append(f"{service}: not healthy")
    stale = int(
        compose.sql(
            "SELECT count(*) FROM documents WHERE "
            "(status='pending' AND created_at < now() - "
            f"interval '{args.max_ingestion_age_seconds} seconds') "
            "OR (status='processing' AND (lease_expires_at IS NULL OR lease_expires_at < now()))"
        )
    )
    if stale:
        issues.append(f"ingestion: {stale} stale documents")
    manifests = [
        path
        for path in Path(args.backup_directory).glob("*/manifest.json")
        if ".incomplete-" not in path.parent.name
    ]
    if not manifests:
        issues.append("backup: no completed bundle")
    else:
        newest = max(manifests, key=lambda path: path.stat().st_mtime)
        bundle = verify_bundle(newest.parent)
        age = (datetime.now(UTC) - datetime.fromisoformat(bundle["completed_at"])).total_seconds()
        if age > args.max_backup_age_seconds:
            issues.append("backup: newest verified bundle exceeds configured age")
    print(json.dumps({"status": "failed" if issues else "ok", "issues": issues}))
    return int(bool(issues))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(json.dumps({"status": "failed", "issues": [str(error)]}), file=sys.stderr)
        raise SystemExit(1) from None
