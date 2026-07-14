"""Cohere reranker (MockTransport) and the none/stub providers."""

import json
import uuid

import httpx

from app.retrieval.base import RetrievedChunk
from app.retrieval.rerank.cohere import CohereRerank
from app.retrieval.rerank.none import NoRerank
from app.retrieval.rerank.stub import StubRerank


def make(chunk_id: int, content: str, score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        filename="doc.pdf",
        content=content,
        page_start=None,
        page_end=None,
        section_path=None,
        score=score,
    )


def cohere_with(handler) -> CohereRerank:
    return CohereRerank(
        api_key="k", model="rerank-v3.5", timeout_s=4.0, transport=httpx.MockTransport(handler)
    )


async def test_cohere_reorders_by_relevance():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert payload["model"] == "rerank-v3.5"
        assert payload["top_n"] == 2
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.12},
                ]
            },
        )

    chunks = [make(1, "irrelevant"), make(2, "relevant")]
    result = await cohere_with(handler).rerank("question", chunks, top_n=2)

    assert [c.chunk_id for c in result] == [2, 1]
    assert result[0].score == 0.91


async def test_cohere_degrades_to_fused_order_on_failure():
    chunks = [make(1, "a", score=0.9), make(2, "b", score=0.8), make(3, "c", score=0.7)]
    result = await cohere_with(lambda r: httpx.Response(429)).rerank("q", chunks, top_n=2)

    # the search must not fail because of the reranker: RRF order, top_n applied
    assert [c.chunk_id for c in result] == [1, 2]


async def test_none_normalizes_scores():
    chunks = [make(1, "a", score=0.032), make(2, "b", score=0.016)]
    result = await NoRerank().rerank("q", chunks, top_n=2)

    assert result[0].score == 1.0
    assert 0 < result[1].score < 1


async def test_stub_scores_by_word_overlap():
    chunks = [make(1, "vacation days for employees"), make(2, "totally unrelated text")]
    result = await StubRerank().rerank("how many vacation days", chunks, top_n=2)

    assert result[0].chunk_id == 1
    assert result[0].score > result[1].score
