"""Common currency of every retrieval stage (vector, FTS, fusion, rerank, generation)."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: uuid.UUID
    filename: str
    content: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    # meaning depends on the stage: cosine similarity -> ts_rank -> RRF -> rerank score
    score: float
    # content label the chunk was filtered on (app/access); "all" for open content
    access_label: str = "all"


@dataclass(frozen=True)
class HiddenStats:
    """What the caller's role could not see (demo reveal mode only).

    ``passages``: filtered-out chunks scoring above the floor the caller set (the refusal
    gate, or the best visible score minus a margin); ``documents``: how many distinct
    documents they come from; ``outranking``: how many of them scored at least as well as
    the best passage the role *could* see — after a successful answer these are the ones
    that might have changed it; ``truncated``: the probe window was full, so ``passages``
    is a lower bound; ``labels``: which labels unlock them, best-scoring first.
    """

    passages: int
    labels: tuple[str, ...]
    documents: int = 0
    outranking: int = 0
    truncated: bool = False
