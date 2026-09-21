"""Bounded query planning and evidence-group merging."""

import json
from dataclasses import dataclass, field

import anyio

from app.generation.llm import LLMProvider, StreamUsage, TextDelta
from app.retrieval.base import RetrievedChunk

MAX_PLANNED_QUERIES = 3
MAX_PLANNED_QUERY_CHARS = 400
MAX_PLANNER_OUTPUT_CHARS = 4096

PLANNER_SYSTEM_PROMPT = "\n".join(
    [
        "You are a retrieval planner for a grounded document question-answering system.",
        "",
        "Given one standalone user question, decide whether retrieval needs multiple focused "
        "searches.",
        "Return exactly one JSON object and no other text, using this schema:",
        '{"queries":["..."]}',
        "",
        "Rules:",
        '1. Return {"queries":[]} when the question is a simple, self-contained direct lookup '
        "that one search can answer.",
        "2. Create focused searches only when the answer needs evidence from multiple distinct "
        "facets, including explicit comparisons across entities, periods, countries, versions, or "
        "scopes; multi-part requests; or implicit evidence dependencies.",
        "3. Preserve every entity, period, country, version, scope, and named metric from the user "
        "question. Each query must independently describe the evidence it should find.",
        '4. For a vague comparison criterion such as "financially better," retrieve multiple '
        "reported metrics for each comparison side. Do not choose one definitive criterion and do "
        "not invent facts or values.",
        "5. Do not answer the question. Do not assume conversation history. Do not use outside "
        "knowledge or hidden document metadata.",
        "6. Return at most 3 unique queries. Each query must be a non-empty string of at most 400 "
        "characters.",
        "7. Do not return a query that merely restates the original question. When side-specific "
        "queries fully\n   cover a comparison, do not add a combined comparison query.",
    ]
)


def _sum_complete(values: list[int | None]) -> int | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


@dataclass
class UsageAccumulator:
    """Aggregate streamed usage without presenting a partial component as complete."""

    _attempts: list[StreamUsage | None] = field(default_factory=list)

    def start_attempt(self) -> None:
        self._attempts.append(None)

    def observe(self, usage: StreamUsage) -> None:
        if not self._attempts:
            raise RuntimeError("start_attempt() must be called before observe()")
        self._attempts[-1] = usage

    @property
    def total(self) -> StreamUsage | None:
        if not self._attempts:
            return None
        prompt_tokens = _sum_complete(
            [usage.prompt_tokens if usage is not None else None for usage in self._attempts]
        )
        completion_tokens = _sum_complete(
            [usage.completion_tokens if usage is not None else None for usage in self._attempts]
        )
        return StreamUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


async def plan_queries(
    llm: LLMProvider,
    question: str,
    aggregate_usage: UsageAccumulator | None = None,
) -> tuple[list[str] | None, StreamUsage | None]:
    """Return strict retrieval facets, or ``None`` when the response is invalid."""

    call_usage = UsageAccumulator()
    call_usage.start_attempt()
    if aggregate_usage is not None:
        aggregate_usage.start_attempt()

    parts: list[str] = []
    buffered = 0
    overflow = False
    stream = llm.stream(PLANNER_SYSTEM_PROMPT, question)
    try:
        async for event in stream:
            if isinstance(event, TextDelta):
                remaining = MAX_PLANNER_OUTPUT_CHARS - buffered
                if len(event.text) > remaining:
                    overflow = True
                    if remaining > 0:
                        parts.append(event.text[:remaining])
                        buffered += remaining
                elif not overflow:
                    parts.append(event.text)
                    buffered += len(event.text)
            elif isinstance(event, StreamUsage):
                call_usage.observe(event)
                if aggregate_usage is not None:
                    aggregate_usage.observe(event)
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            with anyio.CancelScope(shield=True):
                await close()

    if overflow:
        return None, call_usage.total
    raw = "".join(parts)
    if not raw.strip():
        return None, call_usage.total
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, call_usage.total
    if not isinstance(payload, dict) or set(payload) != {"queries"}:
        return None, call_usage.total
    queries = payload["queries"]
    if not isinstance(queries, list) or len(queries) > MAX_PLANNED_QUERIES:
        return None, call_usage.total

    planned: list[str] = []
    seen: set[str] = set()
    for candidate in queries:
        if not isinstance(candidate, str):
            return None, call_usage.total
        cleaned = candidate.strip()
        normalized = " ".join(cleaned.split()).casefold()
        if not cleaned or len(cleaned) > MAX_PLANNED_QUERY_CHARS or normalized in seen:
            return None, call_usage.total
        seen.add(normalized)
        planned.append(cleaned)
    return planned, call_usage.total


def round_robin_chunks(groups: list[list[RetrievedChunk]], limit: int) -> list[RetrievedChunk]:
    """Merge ranked groups by rank, preserving group order and unique chunk ids."""

    merged: list[RetrievedChunk] = []
    seen: set[int] = set()
    rank = 0
    while len(merged) < limit and any(rank < len(group) for group in groups):
        for group in groups:
            if rank >= len(group):
                continue
            chunk = group[rank]
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                merged.append(chunk)
                if len(merged) == limit:
                    break
        rank += 1
    return merged
