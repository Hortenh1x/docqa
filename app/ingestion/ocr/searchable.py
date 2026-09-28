"""Searchable PDF: the original pages with an invisible OCR text layer.

For a scanned PDF the original file is copied and each OCR'd page gets its words drawn in
render mode 3 (invisible) at the recognised boxes; for images a new PDF is built with one
page per frame. Boxes are in the *prepared* image space (after EXIF rotation, deskew and
upscale); the text is placed by scaling only, so a deskewed photo's layer is offset by the
correction angle — good enough for select/search, not for pixel-exact highlighting.
"""

import io
from pathlib import Path

import fitz
from PIL import Image, ImageSequence

from app.ingestion.ocr.base import OcrBlock
from app.ingestion.parsers.base import ParsedDocument

_FONT = "helv"


def _layer(page: fitz.Page, blocks: list[OcrBlock], image_size: tuple[int, int]) -> None:
    width, height = image_size
    if width <= 0 or height <= 0:
        return
    sx = page.rect.width / width
    sy = page.rect.height / height
    for block in blocks:
        if block.bbox is None or not block.text:
            continue
        x0, y0, x1, y1 = block.bbox
        line_count = max(len(block.lines), 1)
        line_h = (y1 - y0) * sy / line_count
        fontsize = max(4.0, min(line_h * 0.8, 40.0))
        lines = block.lines or [block.text]
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            baseline = y0 * sy + line_h * (i + 0.85)
            try:
                page.insert_text(
                    (x0 * sx, baseline),
                    line,
                    fontsize=fontsize,
                    fontname=_FONT,
                    render_mode=3,
                )
            except Exception:
                continue  # a glyph the base font cannot encode never breaks the layer


def build_searchable_pdf(source: Path, is_pdf: bool, parsed: ParsedDocument) -> bytes | None:
    """Bytes of the derived PDF, or None when no page was OCR'd."""
    if not any(page.ocr and page.ocr_blocks for page in parsed.pages):
        return None
    if is_pdf:
        doc = fitz.open(source)
        try:
            for parsed_page in parsed.pages:
                if not parsed_page.ocr or parsed_page.number is None or not parsed_page.size:
                    continue
                page = doc[parsed_page.number - 1]
                _layer(page, parsed_page.ocr_blocks or [], parsed_page.size)
            return bytes(doc.tobytes(garbage=3, deflate=True))
        finally:
            doc.close()

    doc = fitz.open()
    try:
        with Image.open(source) as image:
            for parsed_page, frame in zip(
                parsed.pages, ImageSequence.Iterator(image), strict=False
            ):
                buffer = io.BytesIO()
                frame.convert("RGB").save(buffer, format="JPEG", quality=80)
                w, h = frame.size
                page = doc.new_page(width=w, height=h)
                page.insert_image(page.rect, stream=buffer.getvalue())
                if parsed_page.ocr and parsed_page.size:
                    _layer(page, parsed_page.ocr_blocks or [], parsed_page.size)
        return bytes(doc.tobytes(garbage=3, deflate=True))
    finally:
        doc.close()
