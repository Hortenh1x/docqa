"""OCR blocks → ParsedPage: heading detection without font sizes.

A block is a heading when its line height exceeds the page median by 25%, it is short
(< 80 chars, ≤ 2 lines) and does not end like a sentence. Levels come from clustering
heading line heights across the document (at most 3), mirroring the PDF parser.
"""

import statistics

from app.ingestion.ocr.base import OcrBlock, OcrPage
from app.ingestion.parsers.base import ParsedDocument, ParsedPage

_HEIGHT_FACTOR = 1.25
_MAX_HEADING_CHARS = 80
_CLUSTER_RATIO = 0.9
_MAX_LEVELS = 3


def is_heading(block: OcrBlock, median_height: float) -> bool:
    if block.line_height is None or median_height <= 0:
        return False
    text = block.text.strip()
    return (
        block.line_height > median_height * _HEIGHT_FACTOR
        and len(text) < _MAX_HEADING_CHARS
        and len(block.lines) <= 2
        and not text.endswith((".", ",", ";", ":"))
    )


def heading_levels(pages: list[OcrPage]) -> dict[float, int]:
    """Line height → level for every heading-sized block across the document."""
    heights: list[float] = []
    for page in pages:
        median = _median_height(page)
        heights.extend(
            round(b.line_height, 1)
            for b in page.blocks
            if b.line_height is not None and is_heading(b, median)
        )
    level_by_height: dict[float, int] = {}
    cluster_head: float | None = None
    level = 1
    for height in sorted(set(heights), reverse=True):
        if cluster_head is None:
            cluster_head = height
        elif height < cluster_head * _CLUSTER_RATIO:
            cluster_head = height
            level = min(level + 1, _MAX_LEVELS)
        level_by_height[height] = level
    return level_by_height


def _median_height(page: OcrPage) -> float:
    """Character-weighted median line height: body text dominates by volume, so a page
    with a few big headings and short body still measures the body."""
    heights: list[float] = []
    for block in page.blocks:
        if block.line_height:
            heights.extend([block.line_height] * max(len(block.text), 1))
    return float(statistics.median(heights)) if heights else 0.0


def ocr_layout(parsed: ParsedDocument) -> list[dict[str, object]]:
    """Compact per-page block geometry for OCR'd pages (documents.ocr_layout)."""
    layout: list[dict[str, object]] = []
    for page in parsed.pages:
        if not page.ocr or page.number is None or not page.size:
            continue
        layout.append(
            {
                "page": page.number,
                "size": list(page.size),
                "blocks": [
                    {"bbox": list(b.bbox), "text": b.text}
                    for b in (page.ocr_blocks or [])
                    if b.bbox is not None and b.text
                ],
            }
        )
    return layout


def page_from_ocr(number: int | None, page: OcrPage, levels: dict[float, int]) -> ParsedPage:
    median = _median_height(page)
    blocks: list[str] = []
    headings: list[tuple[int, str]] = []
    for block in page.blocks:
        text = block.text.strip()
        if not text:
            continue
        if is_heading(block, median) and block.line_height is not None:
            level = levels.get(round(block.line_height, 1), 1)
            headings.append((level, text))
        blocks.append(text)
    return ParsedPage(
        number=number,
        text="\n\n".join(blocks),
        headings=headings,
        ocr=True,
        confidence=page.confidence,
        ocr_blocks=list(page.blocks),
        size=(page.width, page.height),
    )
