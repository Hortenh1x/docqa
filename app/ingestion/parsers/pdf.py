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
from PIL import Image

from app.config import get_settings
from app.ingestion.ocr.base import OcrError, OcrPage
from app.ingestion.ocr.layout import heading_levels, page_from_ocr
from app.ingestion.ocr.preprocess import MAX_SIDE
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


def _line_text(spans: list[dict[str, object]]) -> str:
    # broken font encodings surface as NUL bytes, which Postgres text columns reject
    return "".join(str(span.get("text", "")) for span in spans).replace("\x00", "").strip()


def _extract_lines(page: fitz.Page, page_index: int) -> list[_Line]:
    lines: list[_Line] = []
    # expand ligatures (ﬀ -> ff, ﬁ -> fi): they would silently break exact-match search
    data = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_LIGATURES)
    for block_no, block in enumerate(data.get("blocks", [])):
        if block.get("type") != 0:  # images etc.
            continue
        for raw_line in block.get("lines", []):
            spans = raw_line.get("spans", [])
            text = _line_text(spans)
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


def _needs_ocr(page: fitz.Page, page_lines: list[_Line], min_chars: int) -> bool:
    """A page with (almost) no text layer but with an image is a scan."""
    chars = sum(len(ln.text) for ln in page_lines)
    if chars >= min_chars:
        return False
    try:
        return bool(page.get_images(full=False))
    except Exception:
        return False


def _rasterize(page: fitz.Page, dpi: int) -> Image.Image:
    scale = min(dpi / 72, MAX_SIDE / max(page.rect.width, page.rect.height))
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)


class PdfParser:
    def parse(self, path: Path) -> ParsedDocument:
        from app.ingestion.parsers.image import ocr_page_limit, recognize_image

        settings = get_settings()
        try:
            doc = fitz.open(path)
        except Exception as exc:
            raise ParserError(f"cannot open PDF: {exc}") from exc

        ocr_results: dict[int, OcrPage] = {}
        with doc:
            if doc.is_encrypted and not doc.authenticate(""):
                raise ParserError("PDF is password-protected")
            max_pages = settings.max_pages
            if doc.page_count > max_pages:
                raise ParserError(f"PDF has {doc.page_count} pages; the limit is {max_pages}")

            all_lines: list[_Line] = []
            per_page: list[list[_Line]] = []
            ocr_limit = ocr_page_limit()
            for index, page in enumerate(doc):
                page_lines = _extract_lines(page, index)
                if _needs_ocr(page, page_lines, settings.ocr_min_chars_per_page):
                    if len(ocr_results) >= ocr_limit:
                        raise ParserError(
                            f"PDF has more than {ocr_limit} scanned pages; the OCR limit is "
                            f"{ocr_limit}"
                        )
                    try:
                        ocr_results[index] = recognize_image(_rasterize(page, settings.ocr_dpi))
                    except OcrError as exc:
                        raise ParserError(f"OCR failed on page {index + 1}: {exc}") from exc
                    page_lines = []
                _mark_headings(page_lines)
                per_page.append(page_lines)
                all_lines.extend(page_lines)

        _assign_levels(all_lines)
        levels = heading_levels(list(ocr_results.values()))
        pages = [
            page_from_ocr(index + 1, ocr_results[index], levels)
            if index in ocr_results
            else _page_from_lines(index + 1, page_lines)
            for index, page_lines in enumerate(per_page)
        ]
        return ParsedDocument(pages=pages)
