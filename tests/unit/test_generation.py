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


async def test_empty_llm_stream_becomes_refusal(monkeypatch):
    """A zero-content stream (hidden-reasoning burn / provider glitch) must surface as
    an honest refusal, never as an empty non-refused answer."""
    from app.generation import service
    from app.generation.llm.base import StreamUsage as Usage
    from app.retrieval.service import RetrievalResult

    async def fake_retrieve(collection_id, question, settings):
        return RetrievalResult(chunks=[make_chunk(1, "Some relevant content.")], top_score=0.9)

    class EmptyLLM:
        model_name = "deepseek-v4-flash"

        async def stream(self, system, user):
            yield Usage(prompt_tokens=3000, completion_tokens=1024)  # budget eaten, no text

    recorded = {}

    async def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    monkeypatch.setattr(service, "get_llm_provider", lambda settings: EmptyLLM())
    monkeypatch.setattr(service, "_record_query", fake_record)

    events = [
        event
        async for event in service.run_query(
            uuid.uuid4(), uuid.uuid4(), "How many days?", _settings()
        )
    ]

    assert not any(isinstance(e, service.DeltaEvent) for e in events)
    done = events[-1]
    assert isinstance(done, service.DoneEvent)
    assert done.refused is True
    assert done.reason == service.EMPTY_COMPLETION_REASON
    assert done.answer is None
    assert recorded["refused"] is True and recorded["answer"] is None


# --- llm provider factory ---


def _settings(**overrides) -> Settings:
    return Settings(database_url="postgresql+asyncpg://x/x", redis_url="redis://x", **overrides)


def test_hosted_llm_endpoint_requires_api_key():
    settings = _settings(
        llm_provider="openai_compat", llm_base_url="https://api.deepseek.com", llm_api_key=None
    )
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        get_llm_provider(settings)


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
