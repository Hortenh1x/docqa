import uuid

import pytest

from app.generation.llm import GenerationError, StreamUsage, TextDelta
from app.retrieval.base import RetrievedChunk
from app.retrieval.planning import UsageAccumulator, plan_queries, round_robin_chunks


class Stream:
    model_name = "stub"

    def __init__(self, *events):
        self.events = events
        self.closed = False

    async def stream(self, system, user):
        try:
            for event in self.events:
                if isinstance(event, BaseException):
                    raise event
                yield event
        finally:
            self.closed = True


def chunk(chunk_id: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        filename=f"doc-{chunk_id}.md",
        content=f"chunk {chunk_id}",
        page_start=None,
        page_end=None,
        section_path=None,
        score=1.0,
    )


async def test_plan_queries_accepts_strict_bounded_json_and_drains_usage():
    llm = Stream(
        TextDelta('{"queries":["Amazon 2017 net income",'),
        TextDelta('"Amazon 2022 net income"]}'),
        StreamUsage(prompt_tokens=11, completion_tokens=7),
    )

    plan, usage = await plan_queries(llm, "Which year was financially better?")

    assert plan == ["Amazon 2017 net income", "Amazon 2022 net income"]
    assert usage == StreamUsage(prompt_tokens=11, completion_tokens=7)
    assert llm.closed


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "",
        '{"queries":null}',
        '{"queries":[],"answer":"no"}',
        '{"queries":["one","two","three","four"]}',
        '{"queries":["one"," ONE "]}',
        '{"queries":[""]}',
        '{"queries":[7]}',
        '{"queries":["' + ("x" * 401) + '"]}',
    ],
)
async def test_plan_queries_rejects_entire_invalid_plan(payload):
    plan, _ = await plan_queries(Stream(TextDelta(payload)), "question")
    assert plan is None


async def test_plan_queries_preserves_explicit_empty_plan():
    plan, usage = await plan_queries(
        Stream(TextDelta('{"queries":[]}'), StreamUsage(prompt_tokens=4, completion_tokens=2)),
        "question",
    )
    assert plan == []
    assert usage == StreamUsage(prompt_tokens=4, completion_tokens=2)


async def test_plan_queries_bounds_buffer_but_drains_stream_for_usage():
    llm = Stream(
        TextDelta("x" * 5000),
        TextDelta("ignored but drained"),
        StreamUsage(prompt_tokens=21, completion_tokens=9),
    )

    plan, usage = await plan_queries(llm, "question")

    assert plan is None
    assert usage == StreamUsage(prompt_tokens=21, completion_tokens=9)
    assert llm.closed


async def test_known_usage_survives_later_generation_error_in_shared_accumulator():
    aggregate = UsageAccumulator()
    llm = Stream(StreamUsage(prompt_tokens=21, completion_tokens=9), GenerationError("late"))

    with pytest.raises(GenerationError, match="late"):
        await plan_queries(llm, "question", aggregate)

    assert aggregate.total == StreamUsage(prompt_tokens=21, completion_tokens=9)
    assert llm.closed


def test_round_robin_retains_group_coverage_and_deduplicates():
    c1, c2, c3, c4 = (chunk(i) for i in range(1, 5))

    merged = round_robin_chunks([[c1, c2], [c2, c3], [c4]], 4)

    assert [item.chunk_id for item in merged] == [1, 2, 4, 3]


def test_usage_accumulator_totals_each_component_only_when_complete():
    usage = UsageAccumulator()
    usage.start_attempt()
    usage.observe(StreamUsage(10, 2))
    usage.start_attempt()
    usage.observe(StreamUsage(20, None))

    assert usage.total == StreamUsage(prompt_tokens=30, completion_tokens=None)


def test_usage_accumulator_marks_unobserved_attempt_unknown():
    usage = UsageAccumulator()
    usage.start_attempt()
    usage.observe(StreamUsage(10, 2))
    usage.start_attempt()

    assert usage.total == StreamUsage(prompt_tokens=None, completion_tokens=None)
