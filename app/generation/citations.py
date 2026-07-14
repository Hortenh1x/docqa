"""Citation post-processing.

The model cites context blocks as ``[n]``. Out-of-range citations (a ``[9]`` with 8
blocks) are stripped from the answer and logged — an invalid citation must never reach
the client. Valid ones are mapped back to their chunks: document, pages, section,
snippet, score.
"""

import re
import uuid
from dataclasses import dataclass

import structlog

from app.generation.prompts import ContextBlock

log = structlog.get_logger("docqa.citations")

CITATION_RE = re.compile(r"\[(\d+)\]")


@dataclass
class Citation:
    n: int
    chunk_id: int
    document_id: uuid.UUID
    filename: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    snippet: str
    score: float


def finalize_answer(raw_answer: str, blocks: list[ContextBlock]) -> tuple[str, list[Citation]]:
    """Strip invalid citations from the text; return (cleaned answer, used citations)."""
    by_n = {b.n: b for b in blocks}
    used: list[int] = []
    invalid: set[int] = set()

    def _replace(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if n in by_n:
            if n not in used:
                used.append(n)
            return match.group(0)
        invalid.add(n)
        return ""

    cleaned = CITATION_RE.sub(_replace, raw_answer)
    if invalid:
        log.warning("invalid_citations_removed", citations=sorted(invalid))
        cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

    citations = []
    for n in used:
        block = by_n[n]
        chunk = block.chunk
        citations.append(
            Citation(
                n=n,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_path=chunk.section_path,
                snippet=chunk.content[:300],
                score=chunk.score,
            )
        )
    return cleaned.strip(), citations
