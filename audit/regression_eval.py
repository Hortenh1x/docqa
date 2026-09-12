"""Bounded follow-up to paid_eval; carries forward its nonrefundable $3 gate.

Only named synthetic collections are copied read-only into a disposable database.
--diagnose records candidate IDs; --answers records original trimmed model context.
Both require --run and refuse to overwrite existing evidence or spend ledgers.
"""

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import yaml
from alembic.config import Config
from testcontainers.postgres import PostgresContainer

from alembic import command
from app.config import get_settings
from app.db.base import dispose_engine
from app.generation.llm import StreamUsage, TextDelta
from app.generation.llm.openai_compat import OpenAICompatLLM
from app.retrieval import service as retrieval_service
from audit import paid_eval as paid
from eval import run_eval as harness

ROOT = Path("audit/evidence/implementation-v2/paid-eval")
CASES = {"h0090", "m0516", "m0520", "x0533", "p0603", "p0609"}


def selected_cases():
    selected = [
        ("v2", entry)
        for entry in harness.load_golden(Path("eval/golden_v2.yaml"))
        if entry["id"] in CASES
    ]
    for _, entry in selected:
        if entry["id"] == "p0609":
            entry.update(expected_refusal=True, expected_sources=[], expected_answer=None)
            entry["notes"] += "; corrected: all of section 3 is Finance-only"
            entry["hidden_values"] += ["€600"]
    selected.extend(
        ("access", entry)
        for entry in harness.load_golden(Path("eval/golden_access.yaml"))
        if entry["id"] in {"a001", "a002", "a005", "a006"}
    )
    return selected


async def evaluate(gate, out, diagnose):
    settings = get_settings()
    if not diagnose:
        settings = settings.model_copy(update={"rerank_top_n": 40, "context_token_budget": 18000})
    original_send, original_stream = httpx.AsyncClient.send, OpenAICompatLLM.stream
    vector, fts, fusion = (
        retrieval_service.vector_search,
        retrieval_service.fulltext_search,
        retrieval_service.reciprocal_rank_fusion,
    )
    candidates = {}

    def remember(kind, chunks):
        candidates.setdefault(paid.PHASE.get(), {})[kind] = [
            {
                "chunk_id": c.chunk_id,
                "filename": c.filename,
                "score": c.score,
                "section": c.section_path,
                "label": c.access_label,
            }
            for c in chunks
        ]
        return chunks

    async def capture_vector(*args, **kwargs):
        return remember("vector", await vector(*args, **kwargs))

    async def capture_fts(*args, **kwargs):
        return remember("fts", await fts(*args, **kwargs))

    def capture_fusion(*args, **kwargs):
        return remember("fused", fusion(*args, **kwargs))

    async def metered_send(client, request, **kwargs):
        row = gate.reserve(request)
        gate.save()  # keep the reservation even if this process is interrupted
        try:
            response = await original_send(client, request, **kwargs)
            row["http_status"] = response.status_code
            if request.url.path.endswith("/embeddings") and response.status_code == 200:
                gate.usage(row, response.json().get("usage", {}).get("total_tokens"), 0)
            return response
        finally:
            gate.save()

    async def metered_stream(llm, system, user):
        async for event in original_stream(llm, system, user):
            if isinstance(event, StreamUsage):
                row = next(
                    r
                    for r in reversed(gate.calls)
                    if r["phase"] == paid.PHASE.get() and r["model"] == llm.model
                )
                gate.usage(row, event.prompt_tokens, event.completion_tokens)
                gate.save()
            yield event

    judge = OpenAICompatLLM(
        "https://api.openai.com/v1", settings.openai_api_key, "gpt-4.1-mini", 0, 300
    )
    results = []
    chosen = selected_cases()
    (out / "golden.yaml").write_text(yaml.safe_dump(chosen, allow_unicode=True))
    try:
        with (
            patch.object(httpx.AsyncClient, "send", metered_send),
            patch.object(OpenAICompatLLM, "stream", metered_stream),
            patch.object(retrieval_service, "vector_search", capture_vector),
            patch.object(retrieval_service, "fulltext_search", capture_fts),
            patch.object(retrieval_service, "reciprocal_rank_fusion", capture_fusion),
        ):
            for suite, entry in chosen:
                target = paid.COLLECTIONS[suite]
                phase = f"regression:{suite}:{entry['id']}"
                paid.PHASE.set(phase + (":diagnose" if diagnose else ":answer"))
                if diagnose:
                    if entry["id"] not in {"h0090", "m0516", "m0520", "x0533"}:
                        continue
                    principal = harness.resolve_principal(settings, entry.get("role", "employee"))
                    retrieval = await harness.retrieve(
                        target, entry["question"], settings, principal
                    )
                    remember("final", retrieval.chunks)
                    continue
                result = harness.QuestionResult(
                    qid=entry["id"],
                    category=entry["category"],
                    question=entry["question"],
                    expected_docs=[s["doc"] for s in entry.get("expected_sources", [])],
                    expected_refusal=bool(entry.get("expected_refusal", False)),
                    expected_answer=entry.get("expected_answer"),
                    role=entry.get("role"),
                    hidden_values=entry.get("hidden_values", []),
                )
                started = time.monotonic()
                body = await harness._answer_direct(
                    target, result.question, result.role or "employee", settings
                )
                harness._record_answer(result, body)
                result.retrieved_docs = [
                    harness._doc_of(b["filename"]) for b in result.context_blocks or []
                ]
                if result.expected_docs:
                    result.recall_hit = all(
                        d in result.retrieved_docs for d in result.expected_docs
                    )
                allowed = harness.resolve_principal(settings, result.role or "employee").labels
                result.retrieval_leak = any(
                    b["access_label"] not in allowed for b in result.context_blocks or []
                )
                if not result.answered_refused and result.answer_text:
                    paid.PHASE.set(phase + ":judge")
                    parts = []
                    async for event in judge.stream(
                        harness.JUDGE_SYSTEM,
                        harness._judge_prompt(
                            result,
                            [f"{b['header']}\n{b['text']}" for b in result.context_blocks or []],
                        ),
                    ):
                        if isinstance(event, TextDelta):
                            parts.append(event.text)
                    raw = "".join(parts)
                    result.judge_faithful = harness._parse_verdict(raw, "faithful")
                    result.judge_correct = harness._parse_verdict(raw, "correct")
                results.append(
                    {"suite": suite, "seconds": time.monotonic() - started, **asdict(result)}
                )
                (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
                print(
                    f"{phase} refused={result.answered_refused} correct={result.judge_correct}",
                    flush=True,
                )
    finally:
        (out / "candidates.json").write_text(json.dumps(candidates, indent=2))
        await dispose_engine()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--diagnose", action="store_true")
    modes.add_argument("--answers", action="store_true")
    args = parser.parse_args()
    if not args.run:
        parser.error("--run required for paid calls")
    out = ROOT / ("regression-diagnosis" if args.diagnose else "regression-answers")
    prior = ROOT / ("german-correction" if args.diagnose else "regression-diagnosis") / "spend.json"
    if out.exists():
        raise SystemExit("Evidence already exists; inspect ledger before another run")
    previous = json.loads(prior.read_text())
    out.mkdir(parents=True)
    paid.OUT = out
    gate = paid.BudgetGate()
    gate.calls, gate.reserved = previous["calls"], Decimal(previous["cumulative_reserved_usd"])
    source_url = get_settings().database_url
    metadata = {
        "prior_ledger": str(prior),
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "isolated synthetic in-process regression; exact original context",
        "mode": "diagnose" if args.diagnose else "answers",
        "retrieval_overrides": {}
        if args.diagnose
        else {"rerank_top_n": 40, "context_token_budget": 18000},
    }
    try:
        with PostgresContainer(
            "pgvector/pgvector:pg18",
            username="docqa",
            password="docqa",
            dbname="docqa",
            driver="asyncpg",
        ) as pg:
            os.environ.update(
                DATABASE_URL=pg.get_connection_url(),
                ACCOUNTS_ENABLED="false",
                BUDGET_ENABLED="false",
                ACCESS_REVEAL_HIDDEN="true",
            )
            get_settings.cache_clear()
            command.upgrade(Config("alembic.ini"), "head")
            metadata["snapshot"] = paid.copy_synthetic(source_url, pg.get_connection_url())
            asyncio.run(evaluate(gate, out, args.diagnose))
    finally:
        gate.save()
        metadata["ended_at"] = datetime.now(UTC).isoformat()
        (out / "metadata.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
