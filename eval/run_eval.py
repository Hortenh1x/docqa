"""Golden-set evaluation against a seeded collection.

Two layers, run what your budget allows:

- **Retrieval layer (default, no LLM):** recall@8 per category (are the expected
  documents in the top-8 after fusion/rerank), gate-score distributions, and a
  REFUSAL_THRESHOLD sweep that balances refusing no_answer questions against passing
  answerable ones.
- **Answer layer (``--with-answers``):** runs the full pipeline through the HTTP API
  (stream=false) — adds citation precision and end-to-end refusal behavior with the
  configured LLM. Costs tokens; run when an LLM is configured.
- **Judge layer (``--judge``):** LLM-as-judge over the answered questions — faithfulness
  (every claim supported by the retrieved excerpts) and correctness (conveys the golden
  expected answer). Uses the configured openai_compat endpoint; ``--judge-model``
  overrides the model.

Writes ``eval/results.md``. Reproduce with:
    uv run python -m eval.run_eval --collection <policies-en id>
"""

import argparse
import asyncio
import re
import statistics
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.config import get_settings
from app.db.base import dispose_engine
from app.generation.llm import TextDelta
from app.generation.llm.openai_compat import OpenAICompatLLM
from app.generation.prompts import build_context_blocks
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
    expected_answer: str | None = None
    retrieved_docs: list[str] = field(default_factory=list)
    gate_score: float | None = None
    recall_hit: bool | None = None
    # answer layer
    answered_refused: bool | None = None
    answer_text: str | None = None
    citation_docs: list[str] = field(default_factory=list)
    # judge layer
    judge_faithful: bool | None = None
    judge_correct: bool | None = None


def _doc_of(filename: str) -> str:
    return filename.rsplit(".", 1)[0]


def _target_collection(
    collection_id: uuid.UUID, collection_de_id: uuid.UUID | None, expected_docs: list[str]
) -> uuid.UUID:
    """Questions whose golden sources are German mirrors run against the DE collection."""
    if collection_de_id and any(doc.endswith("-DE") for doc in expected_docs):
        return collection_de_id
    return collection_id


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
            expected_answer=entry.get("expected_answer"),
        )
        target = _target_collection(collection_id, collection_de_id, expected_docs)
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
    api: str,
    api_key: str,
    collection_id: uuid.UUID,
    collection_de_id: uuid.UUID | None,
    results: list[QuestionResult],
) -> None:
    async with httpx.AsyncClient(
        base_url=api, headers={"Authorization": f"Bearer {api_key}"}, timeout=300
    ) as client:
        for result in results:
            target = _target_collection(collection_id, collection_de_id, result.expected_docs)
            response = await client.post(
                "/v1/query",
                json={
                    "collection_id": str(target),
                    "question": result.question,
                    "stream": False,
                },
            )
            response.raise_for_status()
            body = response.json()
            result.answered_refused = body["refused"]
            result.answer_text = body.get("answer")
            result.citation_docs = [_doc_of(s["filename"]) for s in body.get("sources", [])]
            print(f"  {result.qid} refused={body['refused']}")


JUDGE_SYSTEM = (
    "You are an evaluation judge for a document Q&A system. "
    "Judge the ANSWER using only the EXCERPTS and the EXPECTED answer. "
    'Reply with ONLY a JSON object, no other text: {"faithful": true, "correct": true}\n'
    'Rules: "faithful" — do the facts stated in the ANSWER appear in the EXCERPTS? '
    "Paraphrase is fine; citation markers like [1] are fine and are not facts. "
    "Set faithful=false ONLY if the ANSWER states a fact that contradicts the EXCERPTS "
    "or is absent from them.\n"
    '"correct" — does the ANSWER convey the key fact(s) of the EXPECTED answer? '
    "Extra correct detail is fine. Set correct=false ONLY if a key fact is missing or wrong."
)


def _parse_verdict(raw: str, key: str) -> bool:
    """Tolerant parse: a missing or malformed verdict counts as a fail, never a pass."""
    match = re.search(rf'"{key}"\s*:\s*(true|false)', raw, re.IGNORECASE)
    return match is not None and match.group(1).lower() == "true"


def _judge_prompt(result: QuestionResult, excerpts: list[str]) -> str:
    numbered = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(excerpts, 1))
    return (
        f"QUESTION:\n{result.question}\n\n"
        f"EXPECTED answer (golden):\n{result.expected_answer}\n\n"
        f"ANSWER (to judge):\n{result.answer_text}\n\n"
        f"EXCERPTS:\n{numbered}"
    )


async def run_judge_layer(
    collection_id: uuid.UUID,
    collection_de_id: uuid.UUID | None,
    results: list[QuestionResult],
    judge_model: str | None,
) -> str:
    """LLM-as-judge over answered questions; returns the judge model name used."""
    settings = get_settings()
    llm = OpenAICompatLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=judge_model or settings.llm_model,
        temperature=0.0,
        max_tokens=200,
    )
    for result in results:
        judgeable = (
            not result.expected_refusal
            and result.expected_answer
            and result.answered_refused is False
            and result.answer_text
        )
        if not judgeable:
            continue
        # rebuild exactly the context the answering LLM saw (same retrieval, same budget)
        target = _target_collection(collection_id, collection_de_id, result.expected_docs)
        retrieval = await retrieve(target, result.question, settings)
        blocks = build_context_blocks(
            retrieval.chunks, settings.context_token_budget, settings.context_chunk_max_tokens
        )
        excerpts = [b.chunk.content for b in blocks]
        parts: list[str] = []
        async for event in llm.stream(JUDGE_SYSTEM, _judge_prompt(result, excerpts)):
            if isinstance(event, TextDelta):
                parts.append(event.text)
        raw = "".join(parts)
        result.judge_faithful = _parse_verdict(raw, "faithful")
        result.judge_correct = _parse_verdict(raw, "correct")
        print(f"  {result.qid} faithful={result.judge_faithful} correct={result.judge_correct}")
    return llm.model


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
    judge_model: str | None = None,
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
        answerable_run = [
            r for r in results if not r.expected_refusal and r.answered_refused is not None
        ]
        false_refusals = sum(1 for r in answerable_run if r.answered_refused)
        cited = [r for r in results if not r.expected_refusal and r.citation_docs]
        precise = sum(1 for r in cited if any(doc in r.expected_docs for doc in r.citation_docs))
        lines += [
            "## Answer layer (full pipeline)",
            "",
            f"- End-to-end refusal rate on no_answer: {refused_ok}/{len(no_answer)}",
            f"- False refusals on answerable questions: {false_refusals}/{len(answerable_run)}",
            f"- Citation precision (cited docs ∩ expected docs): {precise}/{len(cited)}",
            "",
        ]
        judged = [r for r in results if r.judge_faithful is not None]
        if judged and judge_model:
            faithful = sum(1 for r in judged if r.judge_faithful)
            correct = sum(1 for r in judged if r.judge_correct)
            lines += [
                f"## LLM-judged answer quality (judge: {judge_model})",
                "",
                f"- Faithfulness (every claim supported by the excerpts): {faithful}/{len(judged)}",
                f"- Correctness vs the golden expected answer: {correct}/{len(judged)}",
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
    parser.add_argument(
        "--judge", action="store_true", help="LLM-as-judge pass (implies --with-answers)"
    )
    parser.add_argument("--judge-model", default=None, help="judge model (default: LLM_MODEL)")
    args = parser.parse_args()
    if args.judge:
        args.with_answers = True

    settings = get_settings()
    settings_note = (
        f"Embeddings: {settings.embedding_model_id} · rerank: {settings.rerank_provider} · "
        f"top-8 after fusion of vector top-{settings.top_k_vector} + FTS top-{settings.top_k_fts}"
    )
    if args.with_answers:
        settings_note += f" · LLM: {settings.llm_model}"
    entries = load_golden()
    print(f"retrieval layer over {len(entries)} questions…")
    results = await run_retrieval_layer(args.collection, args.collection_de, entries)

    judge_model: str | None = None
    if args.with_answers:
        if not args.api_key:
            raise SystemExit("--with-answers requires --api-key")
        print("answer layer…")
        await run_answer_layer(args.api, args.api_key, args.collection, args.collection_de, results)
    if args.judge:
        print("judge layer…")
        judge_model = await run_judge_layer(
            args.collection, args.collection_de, results, args.judge_model
        )

    sweep = threshold_sweep(results)
    RESULTS.write_text(
        render_results(results, sweep, args.with_answers, settings_note, judge_model),
        encoding="utf-8",
    )
    print(f"\nwrote {RESULTS}")


async def _run() -> None:
    try:
        await main()
    finally:
        await dispose_engine()  # same loop as the engine — asyncpg insists


if __name__ == "__main__":
    asyncio.run(_run())
