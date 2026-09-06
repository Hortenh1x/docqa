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

from app.access import resolve_principal
from app.config import get_settings
from app.db.base import dispose_engine
from app.embeddings.base import EmbeddingError
from app.generation.llm import TextDelta
from app.generation.llm.openai_compat import OpenAICompatLLM
from app.generation.prompts import build_context_blocks
from app.retrieval.service import retrieve

GOLDEN = Path("eval/golden.yaml")
RESULTS = Path("eval/results.md")

CATEGORY_ORDER = [
    "direct",
    "table",
    "multi_doc",
    "version",
    "version_history",
    "buried",
    "distractor_country",
    "stale_faq",
    "as_of_date",
    "german",
    "no_answer",
    "access",
    "partial",
]


@dataclass
class QuestionResult:
    qid: str
    category: str
    question: str
    expected_docs: list[str]
    expected_refusal: bool
    expected_answer: str | None = None
    role: str | None = None  # access role the question is asked under (None → --role)
    # access category: documents holding the hidden passage (documentation for the
    # Misses block) and the labels the reveal-mode hint is expected to name
    hidden_docs: list[str] = field(default_factory=list)
    expected_hidden_labels: list[str] = field(default_factory=list)
    retrieved_docs: list[str] = field(default_factory=list)
    gate_score: float | None = None
    recall_hit: bool | None = None
    hidden_values: list[str] = field(default_factory=list)  # values that must never be answered
    hidden_labels: list[str] | None = None  # from retrieval (reveal mode only)
    value_leak: bool | None = None  # a hidden value appeared in the answer text
    retrieval_leak: bool | None = None  # a chunk outside the role's labels surfaced
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


def load_golden(path: Path) -> list[dict[str, Any]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


async def _retrieve_with_retry(target, question, settings, principal, attempts: int = 4):
    """The embedding provider is remote: a transient connection failure must not abort a
    long run — retry with backoff, then give up loudly."""
    for attempt in range(attempts):
        try:
            return await retrieve(target, question, settings, principal)
        except EmbeddingError:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(2 * 2**attempt)
    raise AssertionError("unreachable")


async def run_retrieval_layer(
    collection_id: uuid.UUID,
    collection_de_id: uuid.UUID | None,
    entries: list[dict[str, Any]],
    role: str,
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
            role=entry.get("role"),
            hidden_docs=[s["doc"] for s in entry.get("hidden_sources", [])],
            expected_hidden_labels=list(entry.get("expected_hidden_labels", [])),
            hidden_values=list(entry.get("hidden_values", [])),
        )
        target = _target_collection(collection_id, collection_de_id, expected_docs)
        principal = resolve_principal(settings, result.role or role)
        retrieval = await _retrieve_with_retry(target, entry["question"], settings, principal)
        result.retrieved_docs = [_doc_of(c.filename) for c in retrieval.chunks]
        result.gate_score = retrieval.top_score
        if retrieval.hidden is not None:
            result.hidden_labels = list(retrieval.hidden.labels)
        # the authoritative leak test: a chunk whose label the role may not read surfaced.
        # Section numbers are not needed for this — open sections of the same document
        # may surface freely (T11 partial answers)
        result.retrieval_leak = any(
            chunk.access_label not in principal.labels for chunk in retrieval.chunks
        )
        if expected_docs:
            # multi_doc questions require ALL expected documents in the returned window —
            # that is the whole point of the category
            result.recall_hit = all(doc in result.retrieved_docs for doc in expected_docs)
        results.append(result)
        marker = "·" if result.recall_hit in (True, None) else "MISS"
        if result.retrieval_leak:
            marker = "LEAK"
        # gate_score is None when retrieval returned nothing (e.g. an FTS-only query
        # that matched no chunk) — report it instead of crashing the whole run
        score = f"{result.gate_score:.3f}" if result.gate_score is not None else "none"
        print(f"  {result.qid} [{result.category}] score={score} {marker}")
    return results


async def run_answer_layer(
    api: str,
    api_key: str,
    collection_id: uuid.UUID,
    collection_de_id: uuid.UUID | None,
    results: list[QuestionResult],
    role: str,
    concurrency: int = 1,
) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(
        base_url=api, headers={"Authorization": f"Bearer {api_key}"}, timeout=300
    ) as client:

        async def one(result: QuestionResult) -> None:
            target = _target_collection(collection_id, collection_de_id, result.expected_docs)
            async with semaphore:
                try:
                    # a well-behaved client: respect 429 + Retry-After from our own limiter,
                    # back off on transient 5xx instead of killing a long run
                    for attempt in range(8):
                        response = await client.post(
                            "/v1/query",
                            json={
                                "collection_id": str(target),
                                "question": result.question,
                                "stream": False,
                                "role": result.role or role,
                            },
                        )
                        if response.status_code == 429:
                            await asyncio.sleep(int(response.headers.get("retry-after", "5")))
                            continue
                        if response.status_code >= 500 and attempt < 7:
                            await asyncio.sleep(2**attempt)
                            continue
                        break
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    print(f"  {result.qid} ERROR {exc!r} — skipped")
                    return
                body = response.json()
                result.answered_refused = body["refused"]
                result.answer_text = body.get("answer")
                if result.hidden_values:
                    answer = result.answer_text or ""
                    result.value_leak = any(value in answer for value in result.hidden_values)
                result.citation_docs = [_doc_of(s["filename"]) for s in body.get("sources", [])]
                print(f"  {result.qid} refused={body['refused']}")

        await asyncio.gather(*(one(result) for result in results))


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


NO_EXPECTED = "(none — the corpus holds nothing on this; judge faithfulness only)"


def _judge_prompt(result: QuestionResult, excerpts: list[str]) -> str:
    numbered = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(excerpts, 1))
    return (
        f"QUESTION:\n{result.question}\n\n"
        "EXPECTED answer (golden):\n"
        f"{result.expected_answer or NO_EXPECTED}\n\n"
        f"ANSWER (to judge):\n{result.answer_text}\n\n"
        f"EXCERPTS:\n{numbered}"
    )


async def run_judge_layer(
    collection_id: uuid.UUID,
    collection_de_id: uuid.UUID | None,
    results: list[QuestionResult],
    judge_model: str | None,
    role: str,
    concurrency: int = 1,
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
    semaphore = asyncio.Semaphore(concurrency)

    async def one(result: QuestionResult) -> None:
        # answerable questions are judged for faithfulness + correctness; an off-corpus
        # question that got an answer anyway is judged for faithfulness only — a grounded
        # "no such benefit, but…" is honest, an invented rule is not
        judgeable = (
            result.answered_refused is False
            and result.answer_text
            and (result.expected_answer or result.expected_refusal)
        )
        if not judgeable:
            return
        async with semaphore:
            try:
                # rebuild exactly the context the answering LLM saw (same retrieval, same budget)
                target = _target_collection(collection_id, collection_de_id, result.expected_docs)
                principal = resolve_principal(settings, result.role or role)
                retrieval = await retrieve(target, result.question, settings, principal)
                blocks = build_context_blocks(
                    retrieval.chunks,
                    settings.context_token_budget,
                    settings.context_chunk_max_tokens,
                )
                excerpts = [b.chunk.content for b in blocks]
                parts: list[str] = []
                async for event in llm.stream(JUDGE_SYSTEM, _judge_prompt(result, excerpts)):
                    if isinstance(event, TextDelta):
                        parts.append(event.text)
            except Exception as exc:  # noqa: BLE001 — one lost verdict must not kill the run
                print(f"  {result.qid} JUDGE ERROR {exc!r} — skipped")
                return
            raw = "".join(parts)
            result.judge_faithful = _parse_verdict(raw, "faithful")
            result.judge_correct = _parse_verdict(raw, "correct")
            print(f"  {result.qid} faithful={result.judge_faithful} correct={result.judge_correct}")

    await asyncio.gather(*(one(result) for result in results))
    return llm.model


def threshold_sweep(results: list[QuestionResult]) -> list[tuple[float, float, float, float]]:
    """Rows of (threshold, refusal_rate_on_no_answer, pass_rate_on_answerable, balanced)."""
    no_answer = [r for r in results if r.expected_refusal and r.gate_score is not None]
    answerable = [r for r in results if not r.expected_refusal and r.gate_score is not None]
    rows = []
    # 0.10 floor: openai embeddings score much lower on the cosine scale than bge-m3
    for step in range(10, 71, 2):
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
        f"| Category | Questions | Recall@{get_settings().rerank_top_n} | Mean gate score |",
        "| --- | --- | --- | --- |",
    ]
    extra = sorted({r.category for r in results} - set(CATEGORY_ORDER))
    for category in CATEGORY_ORDER + extra:
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
        judged = [r for r in results if r.judge_faithful is not None and not r.expected_refusal]
        if judged and judge_model:
            faithful = sum(1 for r in judged if r.judge_faithful)
            correct = sum(1 for r in judged if r.judge_correct)
            lines += [
                f"## LLM-judged answer quality (judge: {judge_model})",
                "",
                f"- Faithfulness (every claim supported by the excerpts): {faithful}/{len(judged)}",
                f"- Correctness vs the golden expected answer: {correct}/{len(judged)}",
            ]
            off = [r for r in results if r.expected_refusal and r.judge_faithful is not None]
            if off:
                unfaithful = sum(1 for r in off if not r.judge_faithful)
                lines.append(
                    f"- Off-corpus questions answered instead of refused: {len(off)} — "
                    f"of which unfaithful (claims not supported by the excerpts): {unfaithful}"
                )
            lines.append("")
    else:
        lines += [
            "## Answer layer",
            "",
            "_Not run yet (needs a configured LLM): `uv run python -m eval.run_eval "
            "--collection <id> --with-answers --api-key <key>`._",
            "",
        ]

    access = [r for r in results if r.category in ("access", "partial")]
    if access:
        restricted = [r for r in access if r.expected_refusal or r.expected_hidden_labels]
        unlock = [r for r in access if not r.expected_hidden_labels and r.recall_hit is not None]
        leak_checked = [r for r in restricted if r.retrieval_leak is not None]
        leaks = sum(1 for r in leak_checked if r.retrieval_leak)
        leaked_ids = [r.qid for r in leak_checked if r.retrieval_leak]
        hint_checked = [
            r for r in restricted if r.expected_hidden_labels and r.hidden_labels is not None
        ]
        hint_ok = sum(
            1 for r in hint_checked if set(r.expected_hidden_labels) <= set(r.hidden_labels or [])
        )
        unlock_hits = sum(1 for r in unlock if r.recall_hit)
        lines += [
            "## Access control",
            "",
            f"- Restricted questions (asked under a role that may not see all of the answer): "
            f"{len(restricted)}",
            f"- Retrieval leaks (a chunk outside the role's labels surfaced): "
            f"{leaks}/{len(leak_checked)}" + (f" — {', '.join(leaked_ids)}" if leaked_ids else ""),
        ]
        if hint_checked:
            lines.append(f"- Reveal hint names the unlocking label: {hint_ok}/{len(hint_checked)}")
        if with_answers:
            answered = [
                r for r in restricted if r.expected_refusal and r.answered_refused is not None
            ]
            e2e_leaks = sum(1 for r in answered if r.answered_refused is False)
            value_leaks = sum(1 for r in answered if r.value_leak)
            lines.append(
                f"- Restricted values appearing in an answer (the real leak test): "
                f"{value_leaks}/{len(answered)}"
            )
            lines.append(
                f"- Answered from open content instead of refusing: {e2e_leaks}/{len(answered)}"
            )
        if unlock:
            lines.append(
                f"- Unlock questions (asked under the right role), "
                f"recall@{get_settings().rerank_top_n}: {unlock_hits}/{len(unlock)}"
            )
        lines.append("")

    misses = [r for r in results if r.recall_hit is False]
    if misses:
        lines += ["## Misses", ""]
        for r in misses:
            window = get_settings().rerank_top_n
            lines.append(
                f"- `{r.qid}` [{r.category}] expected {r.expected_docs}, "
                f"top-{window}: {r.retrieved_docs[:window]}"
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
    parser.add_argument("--golden", type=Path, default=GOLDEN, help="golden set YAML path")
    parser.add_argument("--results", type=Path, default=RESULTS, help="results markdown path")
    parser.add_argument(
        "--concurrency", type=int, default=1, help="parallel requests in answer/judge layers"
    )
    parser.add_argument(
        "--role",
        default="leadership",
        help="access role for questions that name none (default: leadership = full corpus)",
    )
    args = parser.parse_args()
    if args.judge:
        args.with_answers = True

    settings = get_settings()
    settings_note = (
        f"Embeddings: {settings.embedding_model_id} · rerank: {settings.rerank_provider} · "
        f"top-{settings.rerank_top_n} after fusion of vector top-{settings.top_k_vector} "
        f"+ FTS top-{settings.top_k_fts}"
    )
    if args.with_answers:
        settings_note += f" · LLM: {settings.llm_model}"
    entries = load_golden(args.golden)
    print(f"retrieval layer over {len(entries)} questions…")
    results = await run_retrieval_layer(args.collection, args.collection_de, entries, args.role)

    judge_model: str | None = None
    if args.with_answers:
        if not args.api_key:
            raise SystemExit("--with-answers requires --api-key")
        print("answer layer…")
        await run_answer_layer(
            args.api,
            args.api_key,
            args.collection,
            args.collection_de,
            results,
            args.role,
            concurrency=args.concurrency,
        )
    if args.judge:
        print("judge layer…")
        judge_model = await run_judge_layer(
            args.collection,
            args.collection_de,
            results,
            args.judge_model,
            args.role,
            concurrency=args.concurrency,
        )

    sweep = threshold_sweep(results)
    args.results.write_text(
        render_results(results, sweep, args.with_answers, settings_note, judge_model),
        encoding="utf-8",
    )
    print(f"\nwrote {args.results}")


async def _run() -> None:
    try:
        await main()
    finally:
        await dispose_engine()  # same loop as the engine — asyncpg insists


if __name__ == "__main__":
    asyncio.run(_run())
