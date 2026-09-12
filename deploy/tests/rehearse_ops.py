#!/usr/bin/env python3
"""Build and rehearse the production topology using fresh, uniquely named Docker resources.

No existing project/volumes or external AI are used. Outputs only synthetic result summaries.
Run from any directory with Python 3.12 and Docker available.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/scripts"))
from backup import Compose, backup, restore_check, run  # noqa: E402

SEED = r"""
import hashlib, json, time, urllib.request
from app.core.security import generate_api_key
from app.db.models import Tenant, ApiKey
from app.db.sync import sync_session
key, prefix, key_hash = generate_api_key()
with sync_session() as db:
    tenant = Tenant(name="Disposable backup rehearsal")
    db.add(tenant)
    db.flush()
    db.add(ApiKey(tenant_id=tenant.id, prefix=prefix, key_hash=key_hash))
def request(path, data=None, headers=None):
    headers = {"Authorization": "Bearer " + key, **(headers or {})}
    req = urllib.request.Request("http://localhost:8000" + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()
cid = json.loads(request("/v1/collections", b'{"name":"Synthetic"}',
                         {"Content-Type":"application/json"}))["id"]
content = b"# Handbook\n\nEmployees get 27 vacation days."
payload = (b'--docqa-fixture\r\nContent-Disposition: form-data; '
           b'name="file"; filename="handbook.md"\r\n'
           b'Content-Type: text/markdown\r\n\r\n' + content + b'\r\n--docqa-fixture--\r\n')
did = json.loads(request("/v1/collections/" + cid + "/documents", payload,
                         {"Content-Type":"multipart/form-data; boundary=docqa-fixture"}))["id"]
for _ in range(120):
    status = json.loads(request("/v1/documents/" + did))["status"]
    if status == "ready": break
    if status == "failed": raise AssertionError("Synthetic ingestion failed")
    time.sleep(0.5)
else: raise AssertionError("Worker did not process synthetic upload")
assert request("/v1/documents/" + did + "/file") == content
answer = json.loads(request("/v1/query", json.dumps({"collection_id":cid,
    "question":"How many vacation days do employees get?", "stream":False}).encode(),
    {"Content-Type":"application/json"}))
# Add a real personal ownership graph and a settled daily allowance to the bundle.
# This privileged fixture setup is confined to this new disposable database.
import asyncio, uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app.accounts.passwords import hash_password
from app.db.models import User, AccountSession, AccountToken, Collection, Document, Query
from app.db.models.spend import SpendReservation, SpendAllocation
from app.storage import get_storage
from pathlib import Path
encoded = asyncio.run(hash_password("synthetic safe backup password 9364"))
with sync_session() as db:
    owner_tenant = Tenant(name="Synthetic private owner", kind="personal")
    db.add(owner_tenant)
    db.flush()
    owner = User(tenant_id=owner_tenant.id, email="backup@example.com", password_hash=encoded,
                 email_verified=True)
    db.add(owner)
    db.flush()
    collection = db.get(Collection, uuid.UUID(cid))
    old_tenant = collection.tenant_id
    collection.tenant_id = owner_tenant.id
    document = db.get(Document, uuid.UUID(did))
    document.billing_user_id, document.billing_ip_digest = owner.id, "synthetic-ip-digest"
    query = db.get(Query, uuid.UUID(answer["query_id"]))
    query.user_id, query.tenant_id = owner.id, owner_tenant.id
    query.ip_digest = "synthetic-ip-digest"
    db.add(AccountSession(token_hash=uuid.uuid4().hex, user_id=owner.id,
                          csrf_token=uuid.uuid4().hex,
                          expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
    db.add(AccountToken(token_hash=uuid.uuid4().hex, user_id=owner.id, kind="reset",
                        expires_at=datetime.now(timezone.utc)+timedelta(minutes=30)))
    ticket = SpendReservation(id=uuid.uuid4(), day=datetime.now(timezone.utc).date(),
        ip_digest="synthetic-ip-digest", payer_user_id=owner.id,
        operation="fixture", model="fixture", reserved_usd=Decimal("0.20"),
        actual_usd=Decimal("0.20"), settled_at=datetime.now(timezone.utc))
    db.add(ticket)
    db.flush()
    for scope in ("ip:synthetic-ip-digest", "user:"+str(owner.id)):
        db.add(SpendAllocation(reservation_id=ticket.id, scope=scope, day=ticket.day))
    source = Path("/tmp") / ("docqa-private-fixture-"+uuid.uuid4().hex)
    source.write_bytes(content)
    get_storage().store(str(owner_tenant.id), document.sha256, ".md", source)
print(json.dumps({"document_id":did, "query_recorded":True,
                  "private_owner_fixture":True, "settled_budget_usd":"0.20",
                  "original_sha256":hashlib.sha256(content).hexdigest()}))
"""


def main():
    project = "docqa-ops-" + uuid.uuid4().hex[:10]
    image = project + ":local"
    with tempfile.TemporaryDirectory(prefix=project + "-") as temp:
        temp = Path(temp)
        env = temp / "synthetic.env"
        env.write_text(
            f"POSTGRES_PASSWORD={uuid.uuid4().hex}\n"
            f"POSTGRES_APP_PASSWORD={uuid.uuid4().hex}\n"
            f"BUDGET_IP_SECRET={uuid.uuid4().hex}\n"
            f"PUBLIC_TENANT_ID={uuid.uuid4()}\n"
            f"DOCQA_IMAGE={image}\n"
            "EMBEDDING_PROVIDER=stub\nLLM_PROVIDER=stub\nRERANK_PROVIDER=stub\n"
            "DEMO_MODE=false\nSUGGESTED_QUESTIONS_ENABLED=false\nRATE_LIMIT_ENABLED=false\n"
        )
        override = temp / "isolated.yml"
        override.write_text("services:\n  api:\n    ports: !reset []\n")
        compose = Compose(ROOT, [ROOT / "docker-compose.prod.yml", override], env, project)
        try:
            context = temp / "build-context"
            context.mkdir()
            for name in ("Dockerfile", "pyproject.toml", "uv.lock", "alembic.ini"):
                shutil.copy2(ROOT / name, context / name)
            for name in ("app", "alembic"):
                shutil.copytree(
                    ROOT / name, context / name, ignore=shutil.ignore_patterns("__pycache__")
                )
            build_log = temp / "build.log"
            with build_log.open("wb") as output:
                result = subprocess.run(
                    ["docker", "build", "-t", image, str(context)],
                    stdout=output,
                    stderr=subprocess.STDOUT,
                )
            if result.returncode:
                raise RuntimeError(
                    "Disposable backend build failed: " + build_log.read_text()[-3000:]
                )
            try:
                compose.call("up", "--detach", "--no-build", "--wait", "--wait-timeout", "150")
            except RuntimeError as error:
                diagnostics = compose.call(
                    "logs", "--no-color", "--tail", "60", "db", "migrate", "api", "worker", "beat"
                ).stdout.decode()
                raise RuntimeError(f"Synthetic stack startup failed: {diagnostics}") from error
            seed_file = temp / "seed.py"
            seed_file.write_text(SEED)
            with seed_file.open("rb") as source:
                seeded = json.loads(
                    compose.call("exec", "-T", "api", "python", "-", stdin=source).stdout
                )
            bundle = temp / "backups" / "synthetic"
            backup(compose, bundle)
            restore_check(bundle, "pgvector/pgvector:pg18")
            assert int(compose.sql("SELECT count(*) FROM documents")) == 1
            assert int(compose.sql("SELECT count(*) FROM queries")) == 1
            # Prove failure exit/status without contacting a notification recipient.
            compose.call("stop", "beat")
            probe = run(
                [
                    sys.executable,
                    str(ROOT / "deploy/scripts/check_health.py"),
                    "--project-directory",
                    str(ROOT),
                    "--env-file",
                    str(env),
                    "--project-name",
                    project,
                    "--compose-file",
                    str(ROOT / "docker-compose.prod.yml"),
                    "--compose-file",
                    str(override),
                    "--backup-directory",
                    str(bundle.parent),
                    "--max-backup-age-seconds",
                    "3600",
                    "--max-ingestion-age-seconds",
                    "900",
                ],
                check=False,
            )
            assert probe.returncode == 1
            assert "beat: not healthy" in json.loads(probe.stdout)["issues"]
            compose.call("start", "beat")
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "fresh_compose": True,
                        "restricted_runtime": True,
                        "seed": seeded,
                        "monitor_fault_detected": True,
                    }
                )
            )
        finally:
            compose.call("down", "--volumes", "--remove-orphans")
            run(["docker", "image", "rm", image], check=False)


if __name__ == "__main__":
    os.umask(0o077)
    started = time.monotonic()
    main()
    print(json.dumps({"rehearsal_seconds": round(time.monotonic() - started, 3)}))
