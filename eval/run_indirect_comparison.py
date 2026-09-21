"""Reproduce the bounded Amazon cross-year comparison diagnostic.

The default run is retrieval-only. It downloads three fixed FinanceBench PDFs when
needed, verifies their hashes/page counts, parses them with the current DocQA parser,
and caches embeddings outside Git. Every invocation reparses and validates the PDFs;
cached vectors are reused only when the current chunk metadata/content, query inputs,
and embedding model have the same fingerprint. ``--with-answers`` additionally calls
the real ``run_query`` orchestration with retrieval and query recording replaced by the
isolated fixture; it never opens or writes the application database.

Examples:
    uv run python -m eval.run_indirect_comparison
    uv run python -m eval.run_indirect_comparison --with-answers --repeats 2
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import math
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import yaml

from app.access import Principal, resolve_principal
from app.config import Settings, get_settings
from app.embeddings import get_embedding_provider
from app.generation import service as generation_service
from app.generation.llm import LLMEvent, LLMProvider, StreamUsage, TextDelta, get_llm_provider
from app.ingestion.chunking import TokenCounter, chunk_document
from app.ingestion.parsers.pdf import PdfParser
from app.retrieval.base import RetrievedChunk
from app.retrieval.planning import round_robin_chunks
from app.retrieval.service import RetrievalResult
from app.usage.costs import cost_usd, embedding_cost_usd

MANIFEST = Path("eval/indirect_comparison.yaml")
DEFAULT_CACHE_DIR = Path("/tmp/docqa-indirect-comparison")
CACHE_SCHEMA = 2


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return numerator / denominator


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise RuntimeError(f"unsupported fixture version in {path}")
    return payload


async def _ensure_documents(
    manifest: dict[str, Any], cache_dir: Path, *, allow_download: bool
) -> dict[str, Path]:
    document_dir = cache_dir / "documents"
    document_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=180) as client:
        for spec in manifest["documents"]:
            path = document_dir / spec["filename"]
            if not path.exists():
                if not allow_download:
                    raise RuntimeError(f"missing {path}; rerun without --no-download")
                partial = path.with_suffix(path.suffix + ".part")
                async with client.stream("GET", spec["url"]) as response:
                    response.raise_for_status()
                    with partial.open("wb") as handle:
                        async for block in response.aiter_bytes():
                            handle.write(block)
                partial.replace(path)
            actual = _sha256(path)
            if actual != spec["sha256"]:
                raise RuntimeError(
                    f"SHA-256 mismatch for {path}: expected {spec['sha256']}, got {actual}"
                )
            paths[spec["filename"]] = path
    return paths


def _validate_expected_statement(spec: dict[str, Any], chunks: list[Any]) -> None:
    expected = spec.get("expected_statement")
    if expected is None:
        return
    index = expected["parser_chunk_index"]
    if index >= len(chunks):
        raise RuntimeError(f"{spec['filename']} has no parser chunk {index}")
    chunk = chunks[index]
    if (chunk.page_start, chunk.page_end) != (
        expected["parser_page_start"],
        expected["parser_page_end"],
    ):
        raise RuntimeError(
            f"{spec['filename']} statement moved from pages "
            f"{expected['parser_page_start']}-{expected['parser_page_end']} to "
            f"{chunk.page_start}-{chunk.page_end}"
        )
    normalized = chunk.content.replace(",", "")
    for value in expected["values_usd_millions"].values():
        digits = str(abs(value))
        if digits not in normalized:
            raise RuntimeError(f"{spec['filename']} statement does not contain {value}")


def _extract_current_rows(manifest: dict[str, Any], paths: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in manifest["documents"]:
        parsed = PdfParser().parse(paths[spec["filename"]])
        if len(parsed.pages) != spec["pdf_pages"]:
            raise RuntimeError(
                f"page-count mismatch for {spec['filename']}: "
                f"expected {spec['pdf_pages']}, got {len(parsed.pages)}"
            )
        chunks = list(chunk_document(parsed))
        _validate_expected_statement(spec, chunks)
        for chunk in chunks:
            rows.append(
                {
                    "filename": spec["filename"],
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section_path": chunk.section_path,
                }
            )
    return rows


def _questions(manifest: dict[str, Any]) -> list[str]:
    questions = list(manifest["retrieval_queries"].values())
    questions.append(manifest["missing_evidence_control"])
    return questions


def _input_fingerprint(rows: list[dict[str, Any]], questions: list[str]) -> str:
    serialized = json.dumps(
        {"rows": rows, "questions": questions},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


async def _build_cache(
    rows: list[dict[str, Any]],
    questions: list[str],
    input_fingerprint: str,
    settings: Settings,
    cache_path: Path,
) -> dict[str, Any]:
    inputs = [row["content"] for row in rows] + questions

    vectors = await get_embedding_provider(settings).embed(inputs)
    tokens = sum(TokenCounter().count(text) for text in inputs)
    row_count = len(rows)
    payload = {
        "schema": CACHE_SCHEMA,
        "embedding_model": settings.embedding_model_id,
        "input_fingerprint": input_fingerprint,
        "tokens": tokens,
        "estimated_cost_usd": str(embedding_cost_usd(settings.embedding_model_id, tokens)),
        "rows": [
            dict(row, vector=vector) for row, vector in zip(rows, vectors[:row_count], strict=True)
        ],
        "query_vectors": dict(zip(questions, vectors[row_count:], strict=True)),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return payload


async def _load_or_build_cache(
    manifest: dict[str, Any],
    paths: dict[str, Path],
    settings: Settings,
    cache_path: Path,
    *,
    refresh: bool,
) -> dict[str, Any]:
    rows = _extract_current_rows(manifest, paths)
    questions = _questions(manifest)
    input_fingerprint = _input_fingerprint(rows, questions)
    if cache_path.exists() and not refresh:
        with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        if (
            payload.get("schema") == CACHE_SCHEMA
            and payload.get("embedding_model") == settings.embedding_model_id
            and payload.get("input_fingerprint") == input_fingerprint
        ):
            return payload
    return await _build_cache(rows, questions, input_fingerprint, settings, cache_path)


def _chunk_id(filename: str, chunk_index: int) -> int:
    document = {
        "AMAZON_2017_10K.pdf": 1,
        "AMAZON_2022_10K.pdf": 2,
        "BESTBUY_2020_10K.pdf": 3,
    }[filename]
    return document * 1000 + chunk_index


def _to_chunk(row: dict[str, Any], score: float) -> RetrievedChunk:
    chunk_id = _chunk_id(row["filename"], row["chunk_index"])
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=uuid.UUID(int=chunk_id // 1000),
        filename=row["filename"],
        content=row["content"],
        page_start=row["page_start"],
        page_end=row["page_end"],
        section_path=row["section_path"],
        score=score,
        chunk_index=row["chunk_index"],
    )


def _rank(payload: dict[str, Any], vector: list[float], limit: int) -> list[RetrievedChunk]:
    ranked = sorted(
        ((_cosine(vector, row["vector"]), row) for row in payload["rows"]),
        key=lambda item: item[0],
        reverse=True,
    )
    return [_to_chunk(row, score) for score, row in ranked[:limit]]


def _target_ids(manifest: dict[str, Any]) -> dict[str, int]:
    return {
        spec["filename"]: _chunk_id(
            spec["filename"], spec["expected_statement"]["parser_chunk_index"]
        )
        for spec in manifest["documents"]
        if spec.get("expected_statement") is not None
    }


def _positions(chunks: list[RetrievedChunk], targets: dict[str, int]) -> dict[str, int | None]:
    return {
        filename: next(
            (index for index, chunk in enumerate(chunks, start=1) if chunk.chunk_id == target),
            None,
        )
        for filename, target in targets.items()
    }


def _coverage_sweep(manifest: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    queries = manifest["retrieval_queries"]
    rankings = {
        label: _rank(payload, payload["query_vectors"][question], max(manifest["coverage_caps"]))
        for label, question in queries.items()
    }
    targets = _target_ids(manifest)
    results = []
    for cap in manifest["coverage_caps"]:
        baseline = rankings["original"][:cap]
        planned = round_robin_chunks(
            [
                rankings["original"][:cap],
                rankings["amazon_2017"][:cap],
                rankings["amazon_2022"][:cap],
            ],
            cap,
        )
        baseline_positions = _positions(baseline, targets)
        planned_positions = _positions(planned, targets)
        results.append(
            {
                "cap": cap,
                "baseline_target_positions": baseline_positions,
                "planned_target_positions": planned_positions,
                "baseline_has_both": all(
                    value is not None for value in baseline_positions.values()
                ),
                "planned_has_both": all(value is not None for value in planned_positions.values()),
            }
        )
    return results


@dataclass
class CallMetric:
    kind: str
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    cost: Decimal | None
    visible: str


class MeteredLLM:
    def __init__(self, delegate: LLMProvider) -> None:
        self.delegate = delegate
        self.calls: list[CallMetric] = []

    @property
    def model_name(self) -> str:
        return self.delegate.model_name

    async def stream(self, system: str, user: str) -> AsyncIterator[LLMEvent]:
        kind = "planner" if "retrieval planner" in system.lower() else "answer"
        started = time.perf_counter()
        parts: list[str] = []
        usage: StreamUsage | None = None
        try:
            async for event in self.delegate.stream(system, user):
                if isinstance(event, TextDelta):
                    parts.append(event.text)
                elif isinstance(event, StreamUsage):
                    usage = event
                yield event
        finally:
            prompt_tokens = usage.prompt_tokens if usage else None
            completion_tokens = usage.completion_tokens if usage else None
            self.calls.append(
                CallMetric(
                    kind=kind,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost_usd(self.model_name, prompt_tokens, completion_tokens),
                    visible="".join(parts),
                )
            )


@dataclass
class FixtureRetriever:
    payload: dict[str, Any]
    settings: Settings
    calls: list[dict[str, Any]] = field(default_factory=list)
    new_embedding_tokens: int = 0

    async def vector(self, question: str) -> list[float]:
        known = self.payload["query_vectors"].get(question)
        if known is not None:
            return known
        [vector] = await get_embedding_provider(self.settings).embed([question])
        self.new_embedding_tokens += TokenCounter().count(question)
        self.payload["query_vectors"][question] = vector
        return vector

    async def retrieve(
        self,
        collection_id: uuid.UUID,
        question: str,
        settings: Settings,
        principal: Principal | None = None,
        *,
        reveal_hidden: bool = True,
    ) -> RetrievalResult:
        del collection_id
        vector = await self.vector(question)
        chunks = _rank(self.payload, vector, settings.rerank_top_n)
        self.calls.append(
            {
                "question": question,
                "reveal_hidden": reveal_hidden,
                "labels": list(principal.labels) if principal else None,
                "top_score": chunks[0].score if chunks else None,
            }
        )
        return RetrievalResult(
            chunks=chunks,
            top_score=chunks[0].score if chunks else None,
            hidden=None,
        )


def _citation_filenames(done: Any, sources: list[dict[str, Any]]) -> list[str]:
    by_n = {source["n"]: source["filename"] for source in sources}
    return sorted({by_n[item["n"]] for item in done.citations if item["n"] in by_n})


def _behavior_checks(
    manifest: dict[str, Any], question: str, answer: str | None, refused: bool, cited: list[str]
) -> dict[str, bool]:
    text = (answer or "").lower()
    if question == manifest["question"]:
        expectations = manifest["answer_expectations"]
        return {
            "answered": bool(answer) and not refused,
            "mentions_both_years": all(
                str(year) in text for year in expectations["required_years"]
            ),
            "cites_both_filings": set(expectations["required_citation_documents"]) <= set(cited),
            "states_criterion": any(term in text for term in expectations["acceptable_criteria"]),
            "qualified_winner": any(
                term in text
                for term in (
                    "depends",
                    "no single",
                    "while",
                    "but",
                    "by profitability",
                    "by scale",
                    "does not define",
                    "on the net income measure",
                    "on the measure",
                )
            ),
        }
    return {
        "honest_missing_side": refused
        or any(term in text for term in ("not available", "no 2025", "cannot", "missing")),
        "no_eur_amount_invented": not bool(
            re.search(r"(?:€\s*\d|\d[\d,.]*\s*(?:eur|euros?))", answer or "", re.IGNORECASE)
        ),
        "does_not_cite_best_buy": "BESTBUY_2020_10K.pdf" not in cited,
        "does_not_claim_2025_winner": "2025 was financially better" not in text,
    }


async def _answer_run(
    manifest: dict[str, Any],
    payload: dict[str, Any],
    settings: Settings,
    question: str,
    *,
    planning_enabled: bool,
    run_number: int,
) -> dict[str, Any]:
    run_settings = settings.model_copy(
        update={
            "query_planning_enabled": planning_enabled,
            "rerank_top_n": manifest["answer_cap"],
            "rrf_top_n": manifest["answer_cap"],
            "context_token_budget": manifest["context_token_budget"],
            "refusal_threshold": 0.28,
        }
    )
    retriever = FixtureRetriever(payload=payload, settings=run_settings)
    meter = MeteredLLM(get_llm_provider(run_settings))
    recorded: dict[str, Any] = {}
    observed_blocks: list[Any] = []

    async def no_record(**kwargs: Any) -> None:
        recorded.update(kwargs)

    started = time.perf_counter()
    with (
        patch.object(generation_service, "retrieve", retriever.retrieve),
        patch.object(generation_service, "get_llm_provider", lambda _settings: meter),
        patch.object(generation_service, "_record_query", no_record),
    ):
        events = [
            event
            async for event in generation_service.run_query(
                uuid.UUID(int=101),
                uuid.UUID(int=202),
                question,
                run_settings,
                resolve_principal(run_settings, None),
                data_version=0,
                context_observer=observed_blocks.extend,
            )
        ]
    done_events = [event for event in events if isinstance(event, generation_service.DoneEvent)]
    errors = [event for event in events if isinstance(event, generation_service.ErrorEvent)]
    if not ((len(done_events) == 1 and not errors) or (not done_events and len(errors) == 1)):
        raise RuntimeError(f"pipeline failed: done={done_events!r}, errors={errors!r}")
    done = done_events[0] if done_events else None
    terminal_error = errors[0] if errors else None
    sources_events = [
        event for event in events if isinstance(event, generation_service.SourcesEvent)
    ]
    sources = sources_events[0].sources if sources_events else []
    cited = _citation_filenames(done, sources) if done is not None else []
    observed_prompt = sum(call.prompt_tokens or 0 for call in meter.calls)
    observed_completion = sum(call.completion_tokens or 0 for call in meter.calls)
    if done is not None:
        checks = _behavior_checks(manifest, question, done.answer, done.refused, cited)
        terminal_prompt = done.prompt_tokens
        terminal_completion = done.completion_tokens
        terminal_cost = done.cost
        confidence = done.confidence
    else:
        checks = {
            "provider_error_not_document_refusal": terminal_error.code == "provider_unavailable"
        }
        terminal_prompt = recorded.get("prompt_tokens")
        terminal_completion = recorded.get("completion_tokens")
        terminal_cost = recorded.get("cost")
        confidence = recorded.get("confidence")
    original = retriever.calls[0]
    contract = {
        "original_first": original["question"] == question,
        "original_reveals_hidden": original["reveal_hidden"] is True,
        "expansions_hide_hidden": all(not call["reveal_hidden"] for call in retriever.calls[1:]),
        "same_labels": all(call["labels"] == original["labels"] for call in retriever.calls),
        "at_most_three_expansions": len(retriever.calls) - 1 <= 3,
        "context_deduplicated": len({block.chunk.chunk_id for block in observed_blocks})
        == len(observed_blocks),
        "gate_confidence_preserved": confidence == original["top_score"],
        "usage_aggregated": terminal_prompt == observed_prompt
        and terminal_completion == observed_completion,
        "recording_matches_terminal": recorded.get("prompt_tokens") == terminal_prompt
        and recorded.get("completion_tokens") == terminal_completion
        and recorded.get("cost") == terminal_cost,
    }
    return {
        "question": question,
        "planning_enabled": planning_enabled,
        "run_number": run_number,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "answer": done.answer if done is not None else None,
        "refused": done.refused if done is not None else False,
        "reason": done.reason if done is not None else None,
        "terminal_error": (
            {"code": terminal_error.code, "message": terminal_error.message}
            if terminal_error is not None
            else None
        ),
        "confidence": confidence,
        "usage": {
            "prompt_tokens": terminal_prompt,
            "completion_tokens": terminal_completion,
            "cost_usd": str(terminal_cost) if terminal_cost is not None else None,
        },
        "provider_calls": [
            {
                "kind": call.kind,
                "latency_ms": call.latency_ms,
                "prompt_tokens": call.prompt_tokens,
                "completion_tokens": call.completion_tokens,
                "cost_usd": str(call.cost) if call.cost is not None else None,
                "visible": call.visible,
            }
            for call in meter.calls
        ],
        "retrieval_calls": retriever.calls,
        "context": [
            {
                "n": block.n,
                "filename": block.chunk.filename,
                "chunk_index": block.chunk.chunk_index,
                "pages": [block.chunk.page_start, block.chunk.page_end],
            }
            for block in observed_blocks
        ],
        "citations": done.citations if done is not None else [],
        "cited_filenames": cited,
        "new_embedding_tokens": retriever.new_embedding_tokens,
        "contracts": contract,
        "all_contracts_pass": all(contract.values()),
        "behavior": checks,
        "all_behavior_checks_pass": all(checks.values()),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--refresh-embeddings", action="store_true")
    parser.add_argument("--with-answers", action="store_true")
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = _load_manifest(args.manifest)
    settings = get_settings()
    paths = await _ensure_documents(manifest, args.cache_dir, allow_download=not args.no_download)
    cache_path = args.cache_dir / "vectors.json.gz"
    payload = await _load_or_build_cache(
        manifest,
        paths,
        settings,
        cache_path,
        refresh=args.refresh_embeddings,
    )
    result: dict[str, Any] = {
        "fixture": manifest["fixture_name"],
        "embedding_model": payload["embedding_model"],
        "embedding_cache_tokens": payload["tokens"],
        "embedding_cache_estimated_cost_usd": payload["estimated_cost_usd"],
        "coverage": _coverage_sweep(manifest, payload),
        "limitations": manifest["limitations"],
    }
    if args.with_answers:
        answer_runs = []
        for run_number in range(1, args.repeats + 1):
            answer_runs.append(
                await _answer_run(
                    manifest,
                    payload,
                    settings,
                    manifest["question"],
                    planning_enabled=False,
                    run_number=run_number,
                )
            )
            answer_runs.append(
                await _answer_run(
                    manifest,
                    payload,
                    settings,
                    manifest["question"],
                    planning_enabled=True,
                    run_number=run_number,
                )
            )
        answer_runs.append(
            await _answer_run(
                manifest,
                payload,
                settings,
                manifest["missing_evidence_control"],
                planning_enabled=True,
                run_number=1,
            )
        )
        result["answer_runs"] = answer_runs

    output_path = args.output or args.cache_dir / "results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output_path}")
    for row in result["coverage"]:
        print(
            f"cap={row['cap']:>2} baseline={row['baseline_target_positions']} "
            f"planned={row['planned_target_positions']}"
        )
    for run in result.get("answer_runs", []):
        print(
            f"planning={run['planning_enabled']} run={run['run_number']} "
            f"refused={run['refused']} contracts={run['all_contracts_pass']} "
            f"behavior={run['all_behavior_checks_pass']} cost={run['usage']['cost_usd']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
