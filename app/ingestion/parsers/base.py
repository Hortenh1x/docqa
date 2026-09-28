"""Parser contract.

Contract details the chunker relies on:

- ``ParsedPage.text`` consists of blocks separated by blank lines; every heading from
  ``ParsedPage.headings`` also appears in the text as its own block, in the same order.
  The chunker matches heading blocks sequentially to build section breadcrumbs.
- ``number`` is None for formats without pages (docx/md/txt).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.ingestion.ocr.base import OcrBlock


class ParserError(Exception):
    """Unrecoverable parse failure. The document is marked failed — no retry will help."""


@dataclass
class ParsedPage:
    number: int | None
    text: str
    headings: list[tuple[int, str]] = field(default_factory=list)  # (level, text)
    # set by OCR: recognised (not extracted) text, mean confidence 0–100, the blocks with
    # their boxes in ``size`` pixel space (searchable PDF, extraction evidence)
    ocr: bool = False
    confidence: float | None = None
    ocr_blocks: list["OcrBlock"] | None = None
    size: tuple[int, int] | None = None


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]


class Parser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...


def get_parser(mime: str) -> Parser:
    # imported lazily to keep optional heavy deps (pymupdf, python-docx) out of import chains
    from app.ingestion.mime import DOCX_MIME, IMAGE_MIMES, MARKDOWN_MIME, PDF_MIME, TEXT_MIME
    from app.ingestion.parsers.docx import DocxParser
    from app.ingestion.parsers.image import ImageParser
    from app.ingestion.parsers.markdown import MarkdownParser, PlainTextParser
    from app.ingestion.parsers.pdf import PdfParser

    parsers: dict[str, Parser] = {
        PDF_MIME: PdfParser(),
        DOCX_MIME: DocxParser(),
        MARKDOWN_MIME: MarkdownParser(),
        TEXT_MIME: PlainTextParser(),
        **{mime: ImageParser() for mime in IMAGE_MIMES},
    }
    parser = parsers.get(mime)
    if parser is None:
        raise ParserError(f"no parser for MIME type {mime!r}")
    return parser
