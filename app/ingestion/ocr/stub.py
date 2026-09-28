"""Deterministic OCR for tests and the offline demo: the page text is read from the
image's ``ocr_text`` metadata (a PNG tEXt chunk); paragraphs separated by blank lines
become blocks stacked top to bottom. Images without the tag yield no text."""

from PIL import Image

from app.ingestion.ocr.base import OcrBlock, OcrPage

STUB_TEXT_KEY = "ocr_text"
_LINE_HEIGHT = 24


class StubOcr:
    @property
    def name(self) -> str:
        return "stub"

    def recognize(self, image: Image.Image) -> OcrPage:
        raw = image.info.get(STUB_TEXT_KEY)
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw or "")
        blocks: list[OcrBlock] = []
        y = 10
        for paragraph in text.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            lines = paragraph.splitlines()
            # a paragraph written as "# Title" is a heading: taller line height
            heading = paragraph.startswith("# ")
            if heading:
                paragraph = paragraph[2:]
                lines = [paragraph]
            height = _LINE_HEIGHT * (2 if heading else 1)
            blocks.append(
                OcrBlock(
                    text=" ".join(line.strip() for line in lines),
                    bbox=(10, y, max(20, image.width - 10), y + height * len(lines)),
                    confidence=95.0,
                    line_height=float(height),
                    lines=lines,
                )
            )
            y += height * len(lines) + _LINE_HEIGHT
        return OcrPage(width=image.width, height=image.height, blocks=blocks)
