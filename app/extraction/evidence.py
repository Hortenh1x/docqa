"""Where a value comes from: a character span in a chunk (via the pinpoint-quote locator)
and, on OCR'd pages, the paragraph box on the scan."""

import re
from typing import Any

from app.extraction.context import ChunkText
from app.generation.quotes import locate

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).casefold().strip()


def _box_for(
    quote: str, pages: tuple[int | None, int | None], layout: list[dict[str, Any]] | None
) -> tuple[int, list[int], list[int]] | None:
    """(page, bbox, page size) of the OCR block that carries the quote, if any."""
    if not layout:
        return None
    needle = _norm(quote)
    if not needle:
        return None
    lo, hi = pages
    best: tuple[float, int, list[int], list[int]] | None = None
    for page in layout:
        number = int(page.get("page") or 0)
        if lo is not None and hi is not None and not (lo <= number <= hi):
            continue
        for block in page.get("blocks") or []:
            text = _norm(str(block.get("text") or ""))
            if not text:
                continue
            if needle in text:
                score = 1.0
            else:
                words = set(needle.split())
                score = len(words & set(text.split())) / max(len(words), 1)
                if score < 0.6:
                    continue
            candidate = (score, number, list(block["bbox"]), list(page.get("size") or []))
            if best is None or candidate[0] > best[0]:
                best = candidate
    if best is None:
        return None
    return best[1], best[2], best[3]


def find_evidence(
    value: Any,
    quote: str | None,
    chunks: list[ChunkText],
    layout: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any] | None, float]:
    """(evidence or None, confidence). Confidence: 0.9 quote located and the value appears
    in it, 0.75 quote located, 0.6 only the value itself was found, 0.4 nothing found."""
    candidates: list[str] = []
    if quote:
        candidates.append(quote)
    if value is not None and not isinstance(value, bool | list):
        candidates.append(str(value))
    for candidate in candidates:
        for chunk in chunks:
            span = locate(candidate, chunk.content)
            if span is None:
                continue
            start, end = span
            evidence: dict[str, Any] = {
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "page": chunk.page_start,
                "start": start,
                "end": end,
                "quote": chunk.content[start:end],
                "bbox": None,
                "page_size": None,
            }
            box = _box_for(candidate, (chunk.page_start, chunk.page_end), layout)
            if box is not None:
                evidence["page"], evidence["bbox"], evidence["page_size"] = box
            if candidate is quote:
                value_text = _norm(str(value)) if value is not None else ""
                in_quote = bool(value_text) and value_text in _norm(evidence["quote"])
                return evidence, 0.9 if in_quote or value is None else 0.75
            return evidence, 0.6
    return None, 0.4
