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
from PIL import Image, ImageOps, ImageSequence

from app.ingestion.ocr.base import OcrBlock
from app.ingestion.parsers.base import ParsedDocument

_FONT = "helv"


def _layer(page: fitz.Page, blocks: list[OcrBlock], image_size: tuple[int, int]) -> None:
    width, height = image_size
    if width <= 0 or height <= 0:
        return
    sx = page.rect.width / width
    sy = page.rect.height / height
    font = fitz.Font(_FONT)
    writer = fitz.TextWriter(page.rect)
    for block_index, block in enumerate(blocks):
        if not block.text:
            continue
        # Vision transcription has no geometry: retain searchable text in reading
        # order without pretending that these synthetic boxes are OCR evidence.
        x0, y0, x1, y1 = block.bbox or (
            0,
            height * block_index / len(blocks),
            width,
            height * (block_index + 1) / len(blocks),
        )
        lines = block.lines or [block.text]
        line_h = (y1 - y0) * sy / len(lines)
        available_width = max(0.0, min(x1 * sx, page.rect.width) - x0 * sx)
        if available_width <= 0 or line_h <= 0:
            continue
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            # TextWriter embeds fallback fonts for Unicode. Fit long OCR lines
            # inside their box so PDF readers do not drop text outside the page.
            fontsize = min(
                line_h * 0.8, 40.0, available_width / max(font.text_length(line, fontsize=1), 1)
            )
            baseline = y0 * sy + line_h * (i + 0.85)
            writer.append((x0 * sx, baseline), line, font=font, fontsize=fontsize)
    writer.write_text(page, render_mode=3)


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
                frame = ImageOps.exif_transpose(frame)
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
