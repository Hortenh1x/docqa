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
    """What the caller's role could not see (demo reveal mode only): how many passages
    above the refusal threshold were filtered out, and which labels would unlock them
    (best-scoring label first)."""

    passages: int
    labels: tuple[str, ...]
