"""PDF parser (PyMuPDF) with font-based heading detection.

Heuristic (timeboxed by design; exotic layouts degrade to flat text, which is fine):
a line is a heading when its font size exceeds the page median by 15%, or when it is
bold, short (< 80 chars) and doesn't end like a sentence. Heading levels come from
clustering heading font sizes across the document (at most 3 levels).
"""

import statistics
from dataclasses import dataclass
from pathlib import Path

import fitz

from app.config import get_settings
from app.ingestion.parsers.base import ParsedDocument, ParsedPage, ParserError

_BOLD_FLAG = 1 << 4  # PyMuPDF span flag
_SIZE_FACTOR = 1.15
_MAX_HEADING_CHARS = 80
_CLUSTER_RATIO = 0.92  # sizes within 8% of a cluster head share its level
_MAX_LEVELS = 3


@dataclass
class _Line:
    page_index: int
    y: float
    x: float
    block: int
    text: str
    size: float
    bold: bool
    is_heading: bool = False
    level: int = 0


def _extract_lines(page: fitz.Page, page_index: int) -> list[_Line]:
    lines: list[_Line] = []
    data = page.get_text("dict")
    for block_no, block in enumerate(data.get("blocks", [])):
        if block.get("type") != 0:  # images etc.
            continue
        for raw_line in block.get("lines", []):
            spans = raw_line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            x0, y0, _, _ = raw_line.get("bbox", (0.0, 0.0, 0.0, 0.0))
            lines.append(
                _Line(
                    page_index=page_index,
                    y=round(float(y0), 1),
                    x=round(float(x0), 1),
                    block=block_no,
                    text=text,
                    size=max((float(s.get("size", 0.0)) for s in spans), default=0.0),
                    bold=all(int(s.get("flags", 0)) & _BOLD_FLAG for s in spans),
                )
            )
    lines.sort(key=lambda ln: (ln.y, ln.x))
    return lines


def _mark_headings(page_lines: list[_Line]) -> None:
    sizes = [ln.size for ln in page_lines if ln.size > 0]
    if not sizes:
        return
    median = statistics.median(sizes)
    for ln in page_lines:
        looks_bigger = ln.size > median * _SIZE_FACTOR
        looks_bold_title = (
            ln.bold
            and len(ln.text) < _MAX_HEADING_CHARS
            and not ln.text.endswith((".", ",", ";", ":"))
        )
        ln.is_heading = looks_bigger or looks_bold_title


def _assign_levels(all_lines: list[_Line]) -> None:
    """Cluster heading sizes document-wide: biggest cluster -> level 1, and so on."""
    heading_sizes = sorted({round(ln.size, 1) for ln in all_lines if ln.is_heading}, reverse=True)
    if not heading_sizes:
        return
    level_by_size: dict[float, int] = {}
    cluster_head = heading_sizes[0]
    level = 1
    for size in heading_sizes:
        if size < cluster_head * _CLUSTER_RATIO:
            cluster_head = size
            level = min(level + 1, _MAX_LEVELS)
        level_by_size[size] = level
    for ln in all_lines:
        if ln.is_heading:
            ln.level = level_by_size[round(ln.size, 1)]


def _page_from_lines(number: int, page_lines: list[_Line]) -> ParsedPage:
    blocks: list[str] = []
    headings: list[tuple[int, str]] = []
    paragraph: list[str] = []
    paragraph_block = -1

    def flush() -> None:
        if paragraph:
            blocks.append(" ".join(paragraph))
            paragraph.clear()

    for ln in page_lines:
        if ln.is_heading:
            flush()
            blocks.append(ln.text)
            headings.append((ln.level, ln.text))
            continue
        if paragraph and ln.block != paragraph_block:
            flush()
        paragraph.append(ln.text)
        paragraph_block = ln.block
    flush()

    return ParsedPage(number=number, text="\n\n".join(blocks), headings=headings)


class PdfParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            doc = fitz.open(path)
        except Exception as exc:
            raise ParserError(f"cannot open PDF: {exc}") from exc

        with doc:
            if doc.is_encrypted and not doc.authenticate(""):
                raise ParserError("PDF is password-protected")
            max_pages = get_settings().max_pages
            if doc.page_count > max_pages:
                raise ParserError(f"PDF has {doc.page_count} pages; the limit is {max_pages}")

            all_lines: list[_Line] = []
            per_page: list[list[_Line]] = []
            for index, page in enumerate(doc):
                page_lines = _extract_lines(page, index)
                _mark_headings(page_lines)
                per_page.append(page_lines)
                all_lines.extend(page_lines)

        _assign_levels(all_lines)
        pages = [
            _page_from_lines(index + 1, page_lines) for index, page_lines in enumerate(per_page)
        ]
        return ParsedDocument(pages=pages)
