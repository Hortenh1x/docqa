import uuid

from app.retrieval.base import RetrievedChunk
from app.retrieval.fusion import reciprocal_rank_fusion


def make(chunk_id: int, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        filename="doc.pdf",
        content=f"chunk {chunk_id}",
        page_start=None,
        page_end=None,
        section_path=None,
        score=score,
    )


def test_chunk_found_by_both_searches_wins():
    vector = [make(1), make(2)]
    fulltext = [make(3), make(1)]

    fused = reciprocal_rank_fusion([vector, fulltext], k=60, top_n=10)

    # 1: 1/61 + 1/62; 3: 1/61; 2: 1/62 — double-source hit on top, dedup applied
    assert [c.chunk_id for c in fused] == [1, 3, 2]
    assert fused[0].score > fused[1].score > fused[2].score


def test_larger_k_dampens_rank_differences():
    lists = [[make(1), make(2)]]

    sharp = reciprocal_rank_fusion(lists, k=1, top_n=2)
    flat = reciprocal_rank_fusion(lists, k=1000, top_n=2)

    sharp_ratio = sharp[0].score / sharp[1].score
    flat_ratio = flat[0].score / flat[1].score
    assert sharp_ratio > flat_ratio
    assert flat_ratio < 1.01  # with huge k ranks barely matter


def test_top_n_is_enforced():
    lists = [[make(i) for i in range(30)]]
    fused = reciprocal_rank_fusion(lists, k=60, top_n=5)
    assert len(fused) == 5


def test_empty_lists_fuse_to_empty():
    assert reciprocal_rank_fusion([[], []], k=60, top_n=5) == []
