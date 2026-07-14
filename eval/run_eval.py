"""Golden-set evaluation against a seeded collection.

Two layers, run what your budget allows:

- **Retrieval layer (default, no LLM):** recall@8 per category (are the expected
  documents in the top-8 after fusion/rerank), gate-score distributions, and a
  REFUSAL_THRESHOLD sweep that balances refusing no_answer questions against passing
  answerable ones.
- **Answer layer (``--with-answers``):** runs the full pipeline through the HTTP API
  (stream=false) — adds citation precision and end-to-end refusal behavior with the
  configured LLM. Costs tokens; run when an LLM is configured.

Writes ``eval/results.md``. Reproduce with:
    uv run python -m eval.run_eval --collection <policies-en id>
"""

import argparse
import asyncio
import statistics
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.config import get_settings
from app.db.base import dispose_engine
from app.retrieval.service import retrieve

GOLDEN = Path("eval/golden.yaml")
RESULTS = Path("eval/results.md")

CATEGORY_ORDER = ["direct", "table", "multi_doc", "version", "buried", "german", "no_answer"]


@dataclass
class QuestionResult:
    qid: str
    category: str
    question: str
    expected_docs: list[str]
    expected_refusal: bool
    retrieved_docs: list[str] = field(default_factory=list)
    gate_score: float | None = None
    recall_hit: bool | None = None
    # answer layer
    answered_refused: bool | None = None
    citation_docs: list[str] = field(default_factory=list)


def _doc_of(filename: str) -> str:
    return filename.rsplit(".", 1)[0]


def load_golden() -> list[dict[str, Any]]:
    return yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))


async def run_retrieval_layer(
    collection_id: uuid.UUID,
    collection_de_id: uuid.UUID | None,
    entries: list[dict[str, Any]],
):
    settings = get_settings()
    results: list[QuestionResult] = []
    for entry in entries:
        expected_docs = [s["doc"] for s in entry.get("expected_sources", [])]
        result = QuestionResult(
            qid=entry["id"],
            category=entry["category"],
            question=entry["question"],
            expected_docs=expected_docs,
            expected_refusal=bool(entry.get("expected_refusal", False)),
        )
        # questions whose golden sources are German mirrors run against the DE collection
        target = collection_id
        if collection_de_id and any(doc.endswith("-DE") for doc in expected_docs):
            target = collection_de_id
        retrieval = await retrieve(target, entry["question"], settings)
        result.retrieved_docs = [_doc_of(c.filename) for c in retrieval.chunks]
        result.gate_score = retrieval.top_score
        if expected_docs:
            # multi_doc questions require ALL expected documents in the top-8 —
            # that is the whole point of the category
            result.recall_hit = all(doc in result.retrieved_docs for doc in expected_docs)
        results.append(result)
        marker = "·" if result.recall_hit in (True, None) else "MISS"
        print(f"  {result.qid} [{result.category}] score={result.gate_score:.3f} {marker}")
    return results


async def run_answer_layer(
    api: str, api_key: str, collection_id: uuid.UUID, results: list[QuestionResult]
) -> None:
    async with httpx.AsyncClient(
        base_url=api, headers={"Authorization": f"Bearer {api_key}"}, timeout=300
    ) as client:
        for result in results:
            response = await client.post(
                "/v1/query",
                json={
                    "collection_id": str(collection_id),
                    "question": result.question,
                    "stream": False,
                },
            )
            response.raise_for_status()
            body = response.json()
            result.answered_refused = body["refused"]
            result.citation_docs = [_doc_of(s["filename"]) for s in body.get("sources", [])]
            print(f"  {result.qid} refused={body['refused']}")


def threshold_sweep(results: list[QuestionResult]) -> list[tuple[float, float, float, float]]:
    """Rows of (threshold, refusal_rate_on_no_answer, pass_rate_on_answerable, balanced)."""
    no_answer = [r for r in results if r.expected_refusal and r.gate_score is not None]
    answerable = [r for r in results if not r.expected_refusal and r.gate_score is not None]
    rows = []
    for step in range(30, 71, 2):
        threshold = step / 100
        refused = sum(1 for r in no_answer if r.gate_score < threshold)
        passed = sum(1 for r in answerable if r.gate_score >= threshold)
        refusal_rate = refused / len(no_answer) if no_answer else 0.0
        pass_rate = passed / len(answerable) if answerable else 0.0
        rows.append((threshold, refusal_rate, pass_rate, (refusal_rate + pass_rate) / 2))
    return rows


def recommend_threshold(sweep: list[tuple[float, float, float, float]]) -> tuple[float, ...]:
    """The retrieval gate is the CHEAP gate: it must pass ~all answerable questions,
    while anything it lets through is still caught by the NO_ANSWER generation gate.
    So: the highest threshold that keeps the answerable pass rate >= 0.95."""
    passing = [row for row in sweep if row[2] >= 0.95]
    return max(passing, key=lambda row: row[0]) if passing else max(sweep, key=lambda r: r[3])


def render_results(
    results: list[QuestionResult],
    sweep: list[tuple[float, float, float, float]],
    with_answers: bool,
    settings_note: str,
) -> str:
    best = recommend_threshold(sweep)
    lines = [
        "# Evaluation results",
        "",
        f"_{settings_note}_",
        "",
        "Reproduce: `uv run python -m eval.run_eval --collection <policies-en id>`",
        "",
        "## Retrieval quality by category",
        "",
        "| Category | Questions | Recall@8 | Mean gate score |",
        "| --- | --- | --- | --- |",
    ]
    for category in CATEGORY_ORDER:
        rows = [r for r in results if r.category == category]
        if not rows:
            continue
        scored = [r.gate_score for r in rows if r.gate_score is not None]
        mean_score = f"{statistics.mean(scored):.3f}" if scored else "—"
        hits = [r.recall_hit for r in rows if r.recall_hit is not None]
        recall = f"{sum(hits) / len(hits):.2f}" if hits else "—"
        lines.append(f"| {category} | {len(rows)} | {recall} | {mean_score} |")

    answerable = [r for r in results if r.recall_hit is not None]
    overall = sum(r.recall_hit for r in answerable) / len(answerable)
    lines += [
        f"| **all answerable** | {len(answerable)} | **{overall:.2f}** | |",
        "",
        "## Refusal threshold sweep (gate score = best vector cosine, rerank=none)",
        "",
        "| Threshold | Refuses no_answer | Passes answerable | Balanced |",
        "| --- | --- | --- | --- |",
    ]
    for threshold, refusal, passing, balanced in sweep:
        marker = " ←" if (threshold, refusal, passing, balanced) == best else ""
        lines.append(
            f"| {threshold:.2f} | {refusal:.2f} | {passing:.2f} | {balanced:.2f}{marker} |"
        )
    lines += [
        "",
        f"**Recommended `REFUSAL_THRESHOLD`: {best[0]:.2f}** — "
        f"refuses {best[1]:.0%} of off-corpus questions for $0 while passing "
        f"{best[2]:.0%} of answerable ones. The retrieval gate is deliberately "
        "conservative: off-corpus questions that slip through are still converted to "
        "refusals by the NO_ANSWER generation gate (at the cost of one LLM call).",
        "",
    ]

    if with_answers:
        no_answer = [r for r in results if r.expected_refusal]
        refused_ok = sum(1 for r in no_answer if r.answered_refused)
        cited = [r for r in results if not r.expected_refusal and r.citation_docs]
        precise = sum(1 for r in cited if any(doc in r.expected_docs for doc in r.citation_docs))
        lines += [
            "## Answer layer (full pipeline)",
            "",
            f"- End-to-end refusal rate on no_answer: {refused_ok}/{len(no_answer)}",
            f"- Citation precision (top source ∈ expected docs): {precise}/{len(cited)}",
            "",
        ]
    else:
        lines += [
            "## Answer layer",
            "",
            "_Not run yet (needs a configured LLM): `uv run python -m eval.run_eval "
            "--collection <id> --with-answers --api-key <key>`._",
            "",
        ]

    misses = [r for r in results if r.recall_hit is False]
    if misses:
        lines += ["## Misses", ""]
        for r in misses:
            lines.append(
                f"- `{r.qid}` [{r.category}] expected {r.expected_docs}, "
                f"top-8: {r.retrieved_docs[:8]}"
            )
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True, type=uuid.UUID, help="policies-en id")
    parser.add_argument("--collection-de", type=uuid.UUID, default=None, help="policies-de id")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--with-answers", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    settings_note = (
        f"Embeddings: {settings.embedding_model_id} · rerank: {settings.rerank_provider} · "
        f"top-8 after fusion of vector top-{settings.top_k_vector} + FTS top-{settings.top_k_fts}"
    )
    entries = load_golden()
    print(f"retrieval layer over {len(entries)} questions…")
    results = await run_retrieval_layer(args.collection, args.collection_de, entries)

    if args.with_answers:
        if not args.api_key:
            raise SystemExit("--with-answers requires --api-key")
        print("answer layer…")
        await run_answer_layer(args.api, args.api_key, args.collection, results)

    sweep = threshold_sweep(results)
    RESULTS.write_text(
        render_results(results, sweep, args.with_answers, settings_note), encoding="utf-8"
    )
    print(f"\nwrote {RESULTS}")


async def _run() -> None:
    try:
        await main()
    finally:
        await dispose_engine()  # same loop as the engine — asyncpg insists


if __name__ == "__main__":
    asyncio.run(_run())
