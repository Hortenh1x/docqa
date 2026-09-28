"""Image parser: every image (or TIFF/GIF frame) is one OCR'd page.

Pillow decodes PNG/JPEG/TIFF/BMP/WEBP/GIF natively and HEIC/HEIF through pillow-heif
(registered on import). Phone photos go through the preprocessing pipeline; the OCR
provider is resolved lazily so uploads of ordinary documents never touch it.
"""

from pathlib import Path

import pillow_heif
from PIL import Image, ImageSequence, UnidentifiedImageError

from app.config import get_settings
from app.ingestion.ocr import OcrPage, get_ocr_provider
from app.ingestion.ocr.base import OcrError
from app.ingestion.ocr.layout import heading_levels, page_from_ocr
from app.ingestion.ocr.preprocess import prepare
from app.ingestion.parsers.base import ParsedDocument, ParserError

pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS = 80_000_000  # ~9k × 9k: enough for any scan, blocks decompression bombs


def frame_count(path: Path) -> int | None:
    """Frames for early rejection; undecodable files are left to the worker to fail."""
    try:
        with Image.open(path) as image:
            return int(getattr(image, "n_frames", 1))
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def ocr_page_limit() -> int:
    settings = get_settings()
    limit = settings.ocr_max_pages
    if settings.demo_mode:
        limit = min(limit, settings.demo_max_ocr_pages)
    return limit


def recognize_image(image: Image.Image) -> OcrPage:
    settings = get_settings()
    prepared = prepare(image, deskew=settings.ocr_deskew)
    return get_ocr_provider(settings).recognize(prepared.image)


class ImageParser:
    def parse(self, path: Path) -> ParsedDocument:
        limit = ocr_page_limit()
        ocr_pages: list[OcrPage] = []
        try:
            with Image.open(path) as image:
                frames = int(getattr(image, "n_frames", 1))
                if frames > limit:
                    raise ParserError(f"Image has {frames} frames; the OCR limit is {limit}")
                for frame in ImageSequence.Iterator(image):
                    ocr_pages.append(recognize_image(frame.copy()))
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ParserError(f"cannot decode image: {exc}") from exc
        except OcrError as exc:
            raise ParserError(f"OCR failed: {exc}") from exc
        levels = heading_levels(ocr_pages)
        return ParsedDocument(
            pages=[page_from_ocr(i + 1, page, levels) for i, page in enumerate(ocr_pages)]
        )
