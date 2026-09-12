"""Opt-in, isolated real-provider audit. Never imported by the ordinary test suite.

Run from the repo root: .venv/bin/python -m audit.paid_eval --run
Copies only the three named synthetic collections from the local DB into an ephemeral
testcontainer. Source DB is read-only. A process-wide HTTP gate reserves a conservative
UTF-8-byte token bound BEFORE every paid call (including retries), never refunds it,
and stops at $3. Provider usage is separately recorded at verified peak/miss prices.
No keys, request headers, prompts or connection strings enter the evidence ledger.
"""

import argparse
import asyncio
import hashlib
import json
import os
import random
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import yaml
from alembic.config import Config
from sqlalchemy import create_engine, insert, text
from testcontainers.postgres import PostgresContainer

from alembic import command
from app.config import get_settings
from app.db.base import dispose_engine
from app.db.models import Chunk, Collection, Document, Tenant
from app.generation.llm import StreamUsage, TextDelta
from app.generation.llm.openai_compat import OpenAICompatLLM
from eval import run_eval as harness

OUT = Path("audit/evidence/implementation-v2/paid-eval")
COLLECTIONS = {
    "v2": uuid.UUID("3947277a-1d2e-43ce-a350-db9112a7bc0b"),
    "access": uuid.UUID("f624b5a5-5577-4ec8-b0fe-8e0853893711"),
    "de": uuid.UUID("a20afc50-2c68-415b-8092-45df4ed29e7d"),
}
PHASE = ContextVar("audit_phase", default="setup")
PRICES = {
    ("api.deepseek.com", "deepseek-v4-flash"): (Decimal("0.30"), Decimal("1.20")),
    ("api.openai.com", "gpt-4.1-mini"): (Decimal("0.40"), Decimal("1.60")),
    ("api.openai.com", "text-embedding-3-small"): (Decimal("0.02"), Decimal("0")),
}


class BudgetGate:
    def __init__(self, limit=Decimal("3")):
        self.limit = limit
        self.reserved = Decimal("0")
        self.calls = []

    def reserve(self, request):
        payload = json.loads(request.content)
        key = (request.url.host, payload["model"])
        if key not in PRICES or request.method != "POST":
            raise RuntimeError("Paid audit permits only its named providers/models")
        p_in, p_out = PRICES[key]
        embedding = request.url.path.endswith("/embeddings")
        if not embedding and not request.url.path.endswith("/chat/completions"):
            raise RuntimeError("Unexpected provider endpoint")
        content = payload["input"] if embedding else [m["content"] for m in payload["messages"]]
        input_bound = sum(len(s.encode("utf-8")) for s in content) + 1024
        output_bound = 0 if embedding else payload["max_tokens"]
        upper = (input_bound * p_in + output_bound * p_out) / 1_000_000
        # No await between admission and increment: atomic within this event loop.
        if self.reserved + upper > self.limit:
            raise RuntimeError("Paid evaluation budget exhausted before provider call")
        self.reserved += upper
        row = {
            "phase": PHASE.get(),
            "host": key[0],
            "model": key[1],
            "input_bound": input_bound,
            "output_bound": output_bound,
            "reserved_usd": str(upper),
            "usage_peak_miss_usd": None,
        }
        self.calls.append(row)
        return row

    def usage(self, row, prompt, completion):
        if prompt is None or completion is None:
            return
        p_in, p_out = PRICES[(row["host"], row["model"])]
        row.update(prompt_tokens=prompt, completion_tokens=completion)
        cost = (prompt * p_in + completion * p_out) / 1_000_000
        row["usage_peak_miss_usd"] = str(cost)
        if prompt > row["input_bound"] or completion > row["output_bound"]:
            raise RuntimeError("Provider usage exceeded conservative reservation")

    def save(self):
        OUT.mkdir(parents=True, exist_ok=True)
        observed = sum(Decimal(r["usage_peak_miss_usd"] or "0") for r in self.calls)
        unknown = sum(
            Decimal(r["reserved_usd"]) for r in self.calls if r["usage_peak_miss_usd"] is None
        )
        data = {
            "limit_usd": str(self.limit),
            "cumulative_reserved_usd": str(self.reserved),
            "observed_peak_miss_usd": str(observed),
            "unknown_usage_reserved_usd": str(unknown),
            "calls": self.calls,
        }
        (OUT / "spend.json").write_text(json.dumps(data, indent=2) + "\n")


def copy_synthetic(source_url, target_url):
    source = create_engine(source_url.replace("+asyncpg", "+psycopg"))
    target = create_engine(target_url.replace("+asyncpg", "+psycopg"))
    ids = list(COLLECTIONS.values())
    predicates = [
        "id IN (SELECT tenant_id FROM collections WHERE id = ANY(:ids))",
        "id = ANY(:ids)",
        "collection_id = ANY(:ids)",
        "document_id IN (SELECT id FROM documents WHERE collection_id = ANY(:ids))",
    ]
    counts = {}
    digest = hashlib.sha256()
    try:
        with source.connect() as src, target.begin() as dst:
            src.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            for model, predicate in zip(
                (Tenant, Collection, Document, Chunk), predicates, strict=True
            ):
                table = model.__table__
                rows = (
                    src.execute(
                        text(f"SELECT * FROM {table.name} WHERE {predicate} ORDER BY id"),
                        {"ids": ids},
                    )
                    .mappings()
                    .all()
                )
                data = []
                for row in rows:
                    item = {k: v for k, v in row.items() if k in table.c and k != "tsv"}
                    if model is Chunk:
                        item["embedding"] = json.loads(item["embedding"])
                        digest.update(json.dumps(item, sort_keys=True, default=str).encode())
                    data.append(item)
                if data:
                    dst.execute(insert(table), data)
                counts[table.name] = len(data)
            if counts["collections"] != 3 or counts["documents"] != 320:
                raise RuntimeError("Synthetic corpus changed: inspect before spending")
    finally:
        source.dispose()
        target.dispose()
    return {"rows": counts, "chunks_sha256": digest.hexdigest()}


async def evaluate(gate, correct_german=False):
    settings = get_settings()
    original_send = httpx.AsyncClient.send
    original_stream = OpenAICompatLLM.stream

    async def metered_send(client, request, **kwargs):
        row = gate.reserve(request)
        try:
            response = await original_send(client, request, **kwargs)
            row["http_status"] = response.status_code
            if request.url.path.endswith("/embeddings") and response.status_code == 200:
                usage = response.json().get("usage", {})
                gate.usage(row, usage.get("total_tokens"), 0)
            return response
        finally:
            gate.save()

    async def metered_stream(llm, system, user):
        async for event in original_stream(llm, system, user):
            if isinstance(event, StreamUsage):
                row = next(
                    r
                    for r in reversed(gate.calls)
                    if r["phase"] == PHASE.get() and r["model"] == llm.model
                )
                gate.usage(row, event.prompt_tokens, event.completion_tokens)
                gate.save()
            yield event

    groups = defaultdict(list)
    for entry in harness.load_golden(Path("eval/golden_v2.yaml")):
        groups[entry["category"]].append(entry)
    rng = random.Random(20260910)
    selected = []
    for category in sorted(groups):
        rng.shuffle(groups[category])
        selected.extend(groups[category][:5])
    suites = [
        ("v2", selected, None),
        ("access", harness.load_golden(Path("eval/golden_access.yaml")), COLLECTIONS["de"]),
    ]
    if correct_german:
        entries = [
            e
            for e in harness.load_golden(Path("eval/golden_access.yaml"))
            if e["id"] in {"a021", "a022"}
        ]
        # Refusal rows have no expected_sources; explicitly target DE for BOTH roles.
        suites = [("de", entries, None)]
    results_all = []
    timings = []
    judge = OpenAICompatLLM(
        "https://api.openai.com/v1", settings.openai_api_key, "gpt-4.1-mini", 0, 300
    )
    semaphore = asyncio.Semaphore(3)
    with (
        patch.object(httpx.AsyncClient, "send", metered_send),
        patch.object(OpenAICompatLLM, "stream", metered_stream),
    ):
        for suite, entries, de in suites:
            (OUT / f"{suite}-golden.yaml").write_text(yaml.safe_dump(entries, allow_unicode=True))
            PHASE.set(f"{suite}:retrieval")
            results = await harness.run_retrieval_layer(COLLECTIONS[suite], de, entries, "employee")

            async def one(result, suite=suite, de=de):
                async with semaphore:
                    phase = f"{suite}:{result.qid}"
                    PHASE.set(phase + ":answer")
                    started = time.monotonic()
                    target = harness._target_collection(
                        COLLECTIONS[suite], de, result.expected_docs
                    )
                    try:
                        body = await harness._answer_direct(
                            target, result.question, result.role or "employee", settings
                        )
                        harness._record_answer(result, body)
                    except Exception as exc:
                        print(f"{phase} answer_error={type(exc).__name__}", flush=True)
                        return
                    timings.append({"phase": phase, "seconds": time.monotonic() - started})
                    if result.answered_refused or not result.answer_text:
                        return
                    PHASE.set(phase + ":judge")
                    parts = []
                    try:
                        async for event in judge.stream(
                            harness.JUDGE_SYSTEM,
                            harness._judge_prompt(
                                result,
                                [
                                    f"{b['header']}\n{b['text']}"
                                    for b in result.context_blocks or []
                                ],
                            ),
                        ):
                            if isinstance(event, TextDelta):
                                parts.append(event.text)
                        verdict = json.loads("".join(parts))
                        result.judge_faithful = verdict.get("faithful") is True
                        result.judge_correct = verdict.get("correct") is True
                    except Exception as exc:
                        print(f"{phase} judge_error={type(exc).__name__}", flush=True)

            await asyncio.gather(*(one(result) for result in results))
            note = (
                f"Isolated synthetic snapshot; {settings.llm_model} (provider aliases to V4.1); "
                f"OpenAI embeddings@1024; gate={settings.refusal_threshold}; "
                f"top_n={settings.rerank_top_n}; actual trimmed context; judge=gpt-4.1-mini"
            )
            (OUT / f"{suite}-results.md").write_text(
                harness.render_results(
                    results, harness.threshold_sweep(results), True, note, "gpt-4.1-mini"
                )
            )
            results_all.extend({"suite": suite, **asdict(r)} for r in results)
            (OUT / "results.json").write_text(json.dumps(results_all, ensure_ascii=False, indent=2))
            (OUT / "timings.json").write_text(json.dumps(timings, indent=2))
    await dispose_engine()


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="explicitly spend up to $3")
    parser.add_argument(
        "--correct-german",
        action="store_true",
        help="recheck a021/a022 against the patched DE corpus within SAME $3 budget",
    )
    args = parser.parse_args()
    if not args.run:
        parser.error("--run required; this command makes paid provider calls")
    previous = None
    if args.correct_german:
        previous = json.loads((OUT / "spend.json").read_text())
        OUT = OUT / "german-correction"
        COLLECTIONS["de"] = uuid.UUID("42e24a2b-4ad9-438f-8548-ac1686524f2d")
    if (OUT / "spend.json").exists():
        raise SystemExit("Existing spend ledger: inspect it before authorizing another run")
    OUT.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    assert settings.llm_base_url.rstrip("/") == "https://api.deepseek.com"
    assert settings.llm_model == "deepseek-v4-flash"
    assert settings.rerank_provider == "none"
    source_url = settings.database_url
    metadata = {
        "started_at": datetime.now(UTC).isoformat(),
        "budget_usd": "3.00",
        "scope": "in-process query pipeline, not deployed HTTP/auth or ingestion",
        "price_sources": [
            "https://api-docs.deepseek.com/quick_start/pricing/",
            "https://developers.openai.com/api/docs/models/text-embedding-3-small",
            "https://developers.openai.com/api/docs/models/gpt-4.1-mini",
        ],
        "source_hashes": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for root in ("app", "eval")
            for p in Path(root).rglob("*.py")
        },
    }
    gate = BudgetGate()
    if previous:
        gate.calls = previous["calls"]
        gate.reserved = Decimal(previous["cumulative_reserved_usd"])
        metadata["prior_spend_ledger"] = "../spend.json"
    try:
        with PostgresContainer(
            "pgvector/pgvector:pg18",
            username="docqa",
            password="docqa",
            dbname="docqa",
            driver="asyncpg",
        ) as pg:
            os.environ["DATABASE_URL"] = pg.get_connection_url()
            os.environ["ACCESS_REVEAL_HIDDEN"] = "true"
            get_settings.cache_clear()
            command.upgrade(Config("alembic.ini"), "head")
            metadata["snapshot"] = copy_synthetic(source_url, pg.get_connection_url())
            asyncio.run(evaluate(gate, args.correct_german))
    finally:
        gate.save()
        metadata["ended_at"] = datetime.now(UTC).isoformat()
        (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
