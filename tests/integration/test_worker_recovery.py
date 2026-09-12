"""Real Redis/Celery process recovery; no eager shortcuts and no external AI."""

import asyncio
import os
import signal
import subprocess
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.base import get_sessionmaker
from app.db.models import Chunk, Document
from tests.integration.test_readiness_regressions import collection, upload


async def wait_until(predicate):
    async with asyncio.timeout(30):
        while not await predicate():  # noqa: ASYNC110 — external process/DB, no in-process event
            await asyncio.sleep(0.1)


@pytest.mark.parametrize("failure", ["process-kill", "hard-time-limit"])
async def test_worker_kill_recovers_committed_document_without_duplicate_chunks(
    client, tenant, monkeypatch, tmp_path, failure
):
    from app.ingestion.tasks import ingest_document, recover_ingestion
    from app.workers.celery_app import celery_app

    cid = await collection(client, tenant)
    with monkeypatch.context() as patch:
        patch.setattr(ingest_document, "delay", lambda *_: None)
        doc_id = (await upload(client, tenant, cid)).json()["id"]
    monkeypatch.setattr(celery_app.conf, "task_always_eager", False)
    marker = tmp_path / "worker-started"
    worker_env = {**os.environ, "SUGGESTED_QUESTIONS_ENABLED": "false"}
    worker_env["DOCQA_TEST_WORKER_MARKER"] = str(marker)
    if failure == "hard-time-limit":
        worker_env["DOCQA_TEST_IGNORE_SOFT_TIMEOUT"] = "1"
    workers = []
    logs = []

    def start_worker(block):
        if not block:
            worker_env.pop("DOCQA_TEST_WORKER_MARKER", None)
        output = (tmp_path / f"worker-{len(workers)}.log").open("w")
        logs.append(output)
        process = subprocess.Popen(
            [
                ".venv/bin/celery",
                "-A",
                "app.workers.celery_app",
                "worker",
                "--pool=prefork",
                "--concurrency=1",
                "-Q",
                "ingestion",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                "--include",
                "tests.worker_fixture",
                "--loglevel=INFO",
                *(
                    ["--soft-time-limit=1", "--time-limit=2"]
                    if block and failure == "hard-time-limit"
                    else []
                ),
            ],
            env=worker_env,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        workers.append(process)
        return process

    async def started():
        return marker.exists()

    async def ready():
        async with get_sessionmaker()() as db:
            return (
                await db.scalar(select(Document.status).where(Document.id == uuid.UUID(doc_id)))
                == "ready"
            )

    try:
        first = start_worker(True)
        recover_ingestion()
        await wait_until(started)
        if failure == "hard-time-limit":

            async def timed_out():
                return "TimeLimitExceeded" in (tmp_path / "worker-0.log").read_text()

            await wait_until(timed_out)
        os.killpg(first.pid, signal.SIGKILL)
        first.wait(timeout=5)
        # Advance the persisted lease instead of spending eleven minutes sleeping.
        async with get_sessionmaker()() as db:
            row = await db.get(Document, uuid.UUID(doc_id))
            assert row.status == "processing"
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            row.last_enqueued_at = None
            await db.commit()
        start_worker(False)
        recover_ingestion()
        await wait_until(ready)
        # Redelivery after successful completion must be a no-op.
        duplicate = ingest_document.delay(doc_id)

        async def duplicate_finished():
            return f"[{duplicate.id}] succeeded" in (tmp_path / "worker-1.log").read_text()

        await wait_until(duplicate_finished)
        async with get_sessionmaker()() as db:
            row = await db.get(Document, uuid.UUID(doc_id))
            assert row.ingestion_attempts == 2
            assert (
                await db.scalar(select(func.count(Chunk.id)).where(Chunk.document_id == row.id))
                == 1
            )
    finally:
        for process in workers:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        for output in logs:
            output.close()
