import asyncio
import uuid
from decimal import Decimal

import pytest

from app.config import Settings
from app.generation.citations import finalize_answer
from app.generation.llm import get_llm_provider
from app.generation.prompts import ContextBlock, block_header, build_context_blocks
from app.generation.sentinel import SentinelBuffer
from app.ingestion.chunking import TokenCounter
from app.retrieval.base import RetrievedChunk
from app.retrieval.planning import PLANNER_SYSTEM_PROMPT
from app.usage.costs import cost_usd


def make_chunk(chunk_id: int, content: str, **kwargs) -> RetrievedChunk:
    defaults = {
        "document_id": uuid.uuid4(),
        "filename": "POL-001_v2.3.pdf",
        "page_start": 3,
        "page_end": 4,
        "section_path": "5. Carryover",
        "score": 0.9,
    }
    defaults.update(kwargs)
    return RetrievedChunk(chunk_id=chunk_id, content=content, **defaults)


# --- context assembly ---


def test_blocks_numbered_with_headers():
    chunks = [make_chunk(1, "First."), make_chunk(2, "Second.", page_start=None, page_end=None)]
    blocks = build_context_blocks(chunks, token_budget=3600, chunk_max_tokens=700)

    assert [b.n for b in blocks] == [1, 2]
    header = block_header(blocks[0])
    assert header.startswith("[1] POL-001_v2.3.pdf")
    assert "5. Carryover" in header
    assert "p. 3–4" in header
    assert "p." not in block_header(blocks[1])  # pageless chunk


def test_budget_cuts_trailing_blocks_but_keeps_first():
    long_text = " ".join(f"Sentence number {i} about travel policies." for i in range(80))
    chunks = [make_chunk(i, long_text) for i in range(1, 9)]

    blocks = build_context_blocks(chunks, token_budget=1500, chunk_max_tokens=700)

    assert 1 <= len(blocks) < 8  # trimmed by the budget
    # even with an absurdly small budget the first block survives
    assert len(build_context_blocks(chunks, token_budget=10, chunk_max_tokens=700)) == 1


def test_oversized_chunk_is_truncated():
    long_text = " ".join(f"word{i}" for i in range(3000))
    blocks = build_context_blocks([make_chunk(1, long_text)], 3600, chunk_max_tokens=100)
    assert TokenCounter().count(blocks[0].text) <= 100


# --- citation post-processing ---


def blocks_for(*contents: str) -> list[ContextBlock]:
    return [
        ContextBlock(n=i, chunk=make_chunk(i, content), text=content)
        for i, content in enumerate(contents, start=1)
    ]


def test_valid_citations_are_mapped_in_order():
    blocks = blocks_for("Vacation content.", "Carryover content.")
    answer, citations = finalize_answer("Days: 27 [2][1]. Also [2].", blocks)

    assert answer == "Days: 27 [2][1]. Also [2]."
    assert [c.n for c in citations] == [2, 1]  # first-appearance order, deduplicated
    assert citations[0].snippet == "Carryover content."
    assert citations[0].filename == "POL-001_v2.3.pdf"


def test_out_of_range_citation_is_stripped():
    blocks = blocks_for("Only block.")
    answer, citations = finalize_answer("Fact [1], invented [9].", blocks)

    assert "[9]" not in answer
    assert answer == "Fact [1], invented."
    assert [c.n for c in citations] == [1]


def test_answer_with_no_citations_yields_empty_list():
    answer, citations = finalize_answer("Plain text.", blocks_for("A block."))
    assert answer == "Plain text."
    assert citations == []


# --- NO_ANSWER sentinel ---


def test_sentinel_detected_across_deltas():
    buffer = SentinelBuffer()
    assert buffer.feed("NO_ANS") == ""
    assert buffer.feed("WER") == ""
    assert buffer.refused
    assert buffer.feed(" anything after") == ""
    assert buffer.flush() == ""


def test_normal_text_flows_after_probe():
    buffer = SentinelBuffer()
    out = buffer.feed("Employees receive 27 days [1].")
    assert out == "Employees receive 27 days [1]."
    assert not buffer.refused
    assert buffer.feed(" More.") == " More."


def test_ambiguous_prefix_released_on_flush():
    buffer = SentinelBuffer()
    assert buffer.feed("NO_ANS") == ""
    assert buffer.flush() == "NO_ANS"  # never became the sentinel
    assert not buffer.refused


def test_leading_whitespace_ignored_for_detection():
    buffer = SentinelBuffer()
    buffer.feed("  \nNO_ANSWER")
    assert buffer.refused


def test_similar_but_different_text_is_released():
    buffer = SentinelBuffer()
    assert buffer.feed("NO answer here [1].") == "NO answer here [1]."
    assert not buffer.refused


# --- empty completion guard ---


async def test_empty_answer_retries_once_with_same_evidence_and_succeeds(monkeypatch):
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(
        collection_id, question, settings, principal=None, *, reveal_hidden=True
    ):
        return RetrievalResult(chunks=[make_chunk(1, "Some relevant content.")], top_score=0.9)

    class EmptyThenAnswerLLM:
        model_name = "gpt-4o-mini"

        def __init__(self):
            self.answer_prompts = []

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(10, 2)
                return
            self.answer_prompts.append(user)
            if len(self.answer_prompts) == 1:
                yield StreamUsage(3000, 1024)
                return
            yield TextDelta("The evidence supports the answer [1].")
            yield StreamUsage(100, 18)

    recorded = {}
    llm = EmptyThenAnswerLLM()

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: llm)
    monkeypatch.setattr(service, "_record_query", fake_record)

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "How many days?", _settings(), data_version=0
        )
    ]

    done = events[-1]
    assert isinstance(done, service.DoneEvent)
    assert sum(isinstance(event, service.MetaEvent) for event in events) == 1
    assert sum(isinstance(event, service.SourcesEvent) for event in events) == 1
    assert done.refused is False
    assert done.answer == "The evidence supports the answer [1]."
    assert llm.answer_prompts[0] == llm.answer_prompts[1]
    assert (done.prompt_tokens, done.completion_tokens) == (3110, 1044)
    assert done.cost == Decimal("0.001093")
    assert recorded["refused"] is False and recorded["answer"] == done.answer


async def test_two_empty_answers_emit_provider_error_and_record_all_usage(monkeypatch):
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(chunks=[make_chunk(1, "Relevant context")], top_score=0.9)

    class AlwaysEmptyLLM:
        model_name = "gpt-4o-mini"

        def __init__(self):
            self.answer_calls = 0

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(10, 2)
                return
            self.answer_calls += 1
            yield StreamUsage(20, 5)

    llm = AlwaysEmptyLLM()
    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: llm)
    monkeypatch.setattr(service, "_record_query", fake_record)

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    assert llm.answer_calls == 2
    assert isinstance(events[-1], service.ErrorEvent)
    assert events[-1].code == "provider_unavailable"
    assert "try again" in events[-1].message.lower()
    assert recorded["answer"] is None and recorded["refused"] is False
    assert (recorded["prompt_tokens"], recorded["completion_tokens"]) == (50, 12)


async def test_no_answer_sentinel_does_not_retry(monkeypatch):
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(chunks=[make_chunk(1, "Relevant context")], top_score=0.9)

    class RefusingLLM:
        model_name = "gpt-4o-mini"

        def __init__(self):
            self.answer_calls = 0

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(10, 2)
                return
            self.answer_calls += 1
            yield TextDelta("NO_ANSWER")
            yield StreamUsage(20, 3)

    llm = RefusingLLM()
    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: llm)
    monkeypatch.setattr(service, "_record_query", lambda **kwargs: _async_noop())

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    assert llm.answer_calls == 1
    assert isinstance(events[-1], service.DoneEvent)
    assert events[-1].refused is True


async def test_retry_missing_usage_component_keeps_only_complete_total(monkeypatch):
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(chunks=[make_chunk(1, "Relevant context")], top_score=0.9)

    class PartialRetryUsageLLM:
        model_name = "gpt-4o-mini"

        def __init__(self):
            self.answer_calls = 0

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(10, 2)
                return
            self.answer_calls += 1
            if self.answer_calls == 1:
                yield StreamUsage(20, 5)
                return
            yield TextDelta("Supported [1].")
            yield StreamUsage(None, 10)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: PartialRetryUsageLLM())
    monkeypatch.setattr(service, "_record_query", lambda **kwargs: _async_noop())

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    done = events[-1]
    assert isinstance(done, service.DoneEvent)
    assert done.prompt_tokens is None
    assert done.completion_tokens == 17
    assert done.cost is None


async def test_retry_budget_denial_is_not_retried_and_records_unknown_attempt(monkeypatch):
    from app.billing.errors import BudgetExceededError
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(chunks=[make_chunk(1, "Relevant context")], top_score=0.9)

    class RetryBudgetLLM:
        model_name = "gpt-4o-mini"

        def __init__(self):
            self.answer_calls = 0

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(10, 2)
                return
            self.answer_calls += 1
            if self.answer_calls == 1:
                yield StreamUsage(20, 5)
                return
            raise BudgetExceededError("Retry denied")
            yield  # pragma: no cover

    llm = RetryBudgetLLM()
    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: llm)
    monkeypatch.setattr(service, "_record_query", fake_record)

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    assert llm.answer_calls == 2
    assert isinstance(events[-1], service.ErrorEvent)
    assert events[-1].code == "quota_exceeded"
    assert recorded["prompt_tokens"] is None
    assert recorded["completion_tokens"] is None
    assert recorded["cost"] is None


async def test_query_planning_expands_context_with_original_scope_and_question(monkeypatch):
    from app.access import Principal
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    question = "Was 2017 or 2022 financially better?"
    collection_id = uuid.uuid4()
    principal = Principal(role="finance", labels=("all", "finance"))
    original = make_chunk(1, "Original context")
    first = make_chunk(2, "2017 evidence")
    second = make_chunk(3, "2022 evidence")
    calls = []

    async def fake_retrieve(
        actual_collection_id, query, settings, actual_principal=None, *, reveal_hidden=True
    ):
        calls.append(("retrieve", actual_collection_id, query, actual_principal, reveal_hidden))
        if query == question:
            return RetrievalResult(chunks=[original], top_score=0.91)
        if query == "Amazon 2017 reported metrics":
            return RetrievalResult(chunks=[first], top_score=0.8)
        return RetrievalResult(chunks=[second], top_score=0.7)

    class PlannedLLM:
        model_name = "gpt-4o-mini"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                calls.append(("planner", user))
                yield TextDelta(
                    '{"queries":["Amazon 2017 reported metrics","Amazon 2022 reported metrics"]}'
                )
                yield StreamUsage(10, 2)
                return
            calls.append(("answer", user))
            yield TextDelta("2017 and 2022 are both supported [1][2][3].")
            yield StreamUsage(100, 18)

    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: PlannedLLM())
    monkeypatch.setattr(service, "_record_query", fake_record)

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(),
            collection_id,
            question,
            _settings(query_planning_enabled=True),
            principal,
            data_version=0,
        )
    ]

    assert isinstance(events[0], service.MetaEvent)
    assert isinstance(events[1], service.SourcesEvent)
    assert all(isinstance(event, service.DeltaEvent) for event in events[2:-1])
    assert isinstance(events[-1], service.DoneEvent)
    assert sum(isinstance(event, service.SourcesEvent) for event in events) == 1
    assert calls[:4] == [
        ("retrieve", collection_id, question, principal, True),
        ("planner", question),
        ("retrieve", collection_id, "Amazon 2017 reported metrics", principal, False),
        ("retrieve", collection_id, "Amazon 2022 reported metrics", principal, False),
    ]
    answer_prompt = calls[4]
    assert answer_prompt[0] == "answer"
    assert answer_prompt[1].endswith(f"Question: {question}")
    assert [block.chunk.chunk_id for block in recorded["blocks"]] == [1, 2, 3]
    done = events[-1]
    assert done.confidence == 0.91
    assert (done.prompt_tokens, done.completion_tokens) == (110, 20)


async def test_planner_generation_error_falls_back_and_keeps_observed_usage(monkeypatch):
    from app.generation import service
    from app.generation.llm import GenerationError, StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    original = make_chunk(1, "Original context")
    calls = 0

    async def fake_retrieve(
        collection_id, question, settings, principal=None, *, reveal_hidden=True
    ):
        return RetrievalResult(chunks=[original], top_score=0.9)

    class FailingPlanner:
        model_name = "gpt-4o-mini"

        async def stream(self, system, user):
            nonlocal calls
            calls += 1
            if system == PLANNER_SYSTEM_PROMPT:
                yield StreamUsage(11, 3)
                raise GenerationError("late planner failure")
            yield TextDelta("Supported [1].")
            yield StreamUsage(100, 18)

    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: FailingPlanner())
    monkeypatch.setattr(service, "_record_query", fake_record)

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    assert calls == 2
    assert [block.chunk.chunk_id for block in recorded["blocks"]] == [1]
    assert (events[-1].prompt_tokens, events[-1].completion_tokens) == (111, 21)
    assert (recorded["prompt_tokens"], recorded["completion_tokens"]) == (111, 21)


async def test_answer_missing_usage_component_does_not_report_partial_total(monkeypatch):
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(
        collection_id, question, settings, principal=None, *, reveal_hidden=True
    ):
        return RetrievalResult(chunks=[make_chunk(1, "Original context")], top_score=0.9)

    class PartialUsageLLM:
        model_name = "gpt-4o-mini"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(11, 3)
                return
            yield TextDelta("Supported [1].")
            yield StreamUsage(None, 18)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: PartialUsageLLM())
    monkeypatch.setattr(service, "_record_query", lambda **kwargs: _async_noop())

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    assert events[-1].prompt_tokens is None
    assert events[-1].completion_tokens == 21
    assert events[-1].cost is None


async def _async_noop():
    return None


async def test_planner_cancellation_propagates_and_records_known_usage(monkeypatch):
    from app.generation import service
    from app.generation.llm import StreamUsage
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(
        collection_id, question, settings, principal=None, *, reveal_hidden=True
    ):
        return RetrievalResult(chunks=[make_chunk(1, "Original context")], top_score=0.9)

    class CancelledPlanner:
        model_name = "gpt-4o-mini"

        def __init__(self):
            self.closed = False

        async def stream(self, system, user):
            try:
                yield StreamUsage(9, 1)
                raise asyncio.CancelledError
            finally:
                self.closed = True

    llm = CancelledPlanner()
    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: llm)
    monkeypatch.setattr(service, "_record_query", fake_record)

    with pytest.raises(asyncio.CancelledError):
        _ = [
            event
            async for event in service.run_query(
                uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
            )
        ]

    assert llm.closed
    assert (recorded["prompt_tokens"], recorded["completion_tokens"]) == (9, 1)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        pytest.param("exceeded", "quota_exceeded", id="exceeded"),
        pytest.param("unavailable", "budget_unavailable", id="unavailable"),
    ],
)
async def test_planner_budget_errors_do_not_fall_back(monkeypatch, error, code):
    from app.billing.errors import BudgetExceededError, BudgetUnavailableError
    from app.generation import service
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(chunks=[make_chunk(1, "Original context")], top_score=0.9)

    class BudgetPlanner:
        model_name = "gpt-4o-mini"

        async def stream(self, system, user):
            if error == "exceeded":
                raise BudgetExceededError("No budget")
            raise BudgetUnavailableError("No accounting")
            yield  # pragma: no cover

    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: BudgetPlanner())
    monkeypatch.setattr(service, "_record_query", fake_record)

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    assert isinstance(events[-1], service.ErrorEvent)
    assert events[-1].code == code
    assert recorded["answer"] is None and recorded["refused"] is False
    assert recorded["prompt_tokens"] is None


@pytest.mark.parametrize("planner_text", ["not json", "", '{"queries":[]}'])
async def test_planner_fallback_shapes_continue_with_aggregate_usage(monkeypatch, planner_text):
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    retrieval_calls = 0

    async def fake_retrieve(*args, **kwargs):
        nonlocal retrieval_calls
        retrieval_calls += 1
        return RetrievalResult(chunks=[make_chunk(1, "Original context")], top_score=0.9)

    class FallbackPlanner:
        model_name = "gpt-4o-mini"

        def __init__(self):
            self.calls = 0

        async def stream(self, system, user):
            self.calls += 1
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta(planner_text)
                yield StreamUsage(7, 2)
                return
            yield TextDelta("Supported [1].")
            yield StreamUsage(100, 18)

    llm = FallbackPlanner()
    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: llm)
    monkeypatch.setattr(service, "_record_query", lambda **kwargs: _async_noop())

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    done = events[-1]
    assert isinstance(done, service.DoneEvent)
    assert retrieval_calls == 1 and llm.calls == 2
    assert (done.prompt_tokens, done.completion_tokens) == (107, 20)


async def test_answer_cancellation_closes_stream_and_records_partial_usage(monkeypatch):
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(*args, **kwargs):
        return RetrievalResult(chunks=[make_chunk(1, "Original context")], top_score=0.9)

    class CancelledAnswer:
        model_name = "gpt-4o-mini"

        def __init__(self):
            self.answer_closed = False

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(10, 2)
                return
            try:
                yield TextDelta("A substantive partial answer with enough text to stream [1].")
                yield StreamUsage(20, 4)
                raise asyncio.CancelledError
            finally:
                self.answer_closed = True

    llm = CancelledAnswer()
    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: llm)
    monkeypatch.setattr(service, "_record_query", fake_record)

    with pytest.raises(asyncio.CancelledError):
        _ = [
            event
            async for event in service.run_query(
                uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
            )
        ]

    assert llm.answer_closed
    assert recorded["answer"].startswith("A substantive partial")
    assert (recorded["prompt_tokens"], recorded["completion_tokens"]) == (30, 6)


def test_query_planning_defaults_on_and_can_be_disabled():
    assert _settings().query_planning_enabled is True
    assert _settings(query_planning_enabled=False).query_planning_enabled is False


async def test_query_planning_flag_off_keeps_single_retrieval_and_answer_call(monkeypatch):
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    retrieval_calls = 0
    llm_calls = 0

    async def fake_retrieve(
        collection_id, question, settings, principal=None, *, reveal_hidden=True
    ):
        nonlocal retrieval_calls
        retrieval_calls += 1
        return RetrievalResult(chunks=[make_chunk(1, "Original context")], top_score=0.9)

    class AnswerOnlyLLM:
        model_name = "gpt-4o-mini"

        async def stream(self, system, user):
            nonlocal llm_calls
            llm_calls += 1
            assert system != PLANNER_SYSTEM_PROMPT
            yield TextDelta("Supported [1].")
            yield StreamUsage(100, 18)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: AnswerOnlyLLM())
    monkeypatch.setattr(service, "_record_query", lambda **kwargs: _async_noop())

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(),
            uuid.uuid4(),
            "Question",
            _settings(query_planning_enabled=False),
            data_version=0,
        )
    ]

    assert retrieval_calls == llm_calls == 1
    assert (events[-1].prompt_tokens, events[-1].completion_tokens) == (100, 18)


async def test_expansion_embedding_error_keeps_original_and_successful_groups(monkeypatch):
    from app.embeddings.base import EmbeddingError
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    original = make_chunk(1, "Original context")
    recovered = make_chunk(3, "Recovered context")

    async def fake_retrieve(
        collection_id, question, settings, principal=None, *, reveal_hidden=True
    ):
        if question == "Question":
            return RetrievalResult(chunks=[original], top_score=0.9)
        if question == "failed facet":
            raise EmbeddingError("transient")
        return RetrievalResult(chunks=[recovered], top_score=0.8)

    class FacetLLM:
        model_name = "gpt-4o-mini"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":["failed facet","successful facet"]}')
                yield StreamUsage(10, 2)
                return
            yield TextDelta("Supported [1][2].")
            yield StreamUsage(100, 18)

    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: FacetLLM())
    monkeypatch.setattr(service, "_record_query", fake_record)

    _ = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    assert [block.chunk.chunk_id for block in recorded["blocks"]] == [1, 3]


async def test_answer_budget_error_is_not_planner_fallback_and_records_unknown_attempt(monkeypatch):
    from app.billing.errors import BudgetUnavailableError
    from app.generation import service
    from app.generation.llm import StreamUsage, TextDelta
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(
        collection_id, question, settings, principal=None, *, reveal_hidden=True
    ):
        return RetrievalResult(chunks=[make_chunk(1, "Original context")], top_score=0.9)

    class BudgetDeniedAnswer:
        model_name = "gpt-4o-mini"

        async def stream(self, system, user):
            if system == PLANNER_SYSTEM_PROMPT:
                yield TextDelta('{"queries":[]}')
                yield StreamUsage(10, 2)
                return
            raise BudgetUnavailableError("No budget")
            yield  # pragma: no cover - keeps this an async generator

    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: BudgetDeniedAnswer())
    monkeypatch.setattr(service, "_record_query", fake_record)

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", _settings(), data_version=0
        )
    ]

    assert isinstance(events[-1], service.ErrorEvent)
    assert events[-1].code == "budget_unavailable"
    assert recorded["prompt_tokens"] is None
    assert recorded["completion_tokens"] is None
    assert recorded["cost"] is None


# --- llm provider factory ---


def _settings(**overrides) -> Settings:
    return Settings(database_url="postgresql+asyncpg://x/x", redis_url="redis://x", **overrides)


def test_hosted_llm_endpoint_requires_api_key():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        _settings(
            llm_provider="openai_compat", llm_base_url="https://api.deepseek.com", llm_api_key=None
        )


def test_local_llm_endpoint_may_go_keyless():
    settings = _settings(
        llm_provider="openai_compat",
        llm_base_url="http://localhost:11435/v1",
        llm_model="deepseek-v4-flash",
        llm_api_key=None,
    )
    assert get_llm_provider(settings).model_name == "deepseek-v4-flash"


# --- costs ---


def test_known_model_cost():
    assert cost_usd("gpt-4o-mini", 1_000_000, 1_000_000) == Decimal("0.750000")
    assert cost_usd("stub", 100, 18) == Decimal("0.000000")


def test_unknown_model_or_missing_tokens_yield_none():
    assert cost_usd("mystery-model-9000", 100, 100) is None
    assert cost_usd("gpt-4o-mini", None, 100) is None
    assert cost_usd(None, 100, 100) is None
