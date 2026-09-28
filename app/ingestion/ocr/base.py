"""OCR provider contract.

``recognize`` takes an already-prepared page image (see ``preprocess``) and returns
paragraph-level blocks with bounding boxes in that image's pixel coordinates, so the
layout heuristics, the searchable PDF and field-extraction evidence all speak one
coordinate system. Providers without geometry (vision LLM) return blocks with no bbox.
"""

from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image

from app.config import Settings


class OcrError(Exception):
    """Recognition failed for this page in a way a retry will not fix."""


class OcrUnavailableError(OcrError):
    """The engine is not installed or not reachable — a deployment problem."""


@dataclass(frozen=True)
class OcrBlock:
    text: str
    # (x0, y0, x1, y1) in image pixels; None when the provider has no geometry
    bbox: tuple[int, int, int, int] | None
    # 0–100, mean word confidence; None when the provider gives none
    confidence: float | None
    # median line height in pixels — the OCR stand-in for font size
    line_height: float | None = None
    lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OcrPage:
    width: int
    height: int
    blocks: list[OcrBlock]

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text)

    @property
    def confidence(self) -> float | None:
        scored = [b for b in self.blocks if b.confidence is not None and b.text]
        if not scored:
            return None
        weights = [max(len(b.text), 1) for b in scored]
        total = sum(weights)
        return sum((b.confidence or 0.0) * w for b, w in zip(scored, weights, strict=True)) / total


class OcrProvider(Protocol):
    def recognize(self, image: Image.Image) -> OcrPage: ...

    @property
    def name(self) -> str: ...


def get_ocr_provider(settings: Settings) -> OcrProvider:
    if settings.ocr_provider == "tesseract":
        from app.ingestion.ocr.tesseract import TesseractOcr

        return TesseractOcr(languages=settings.ocr_languages)
    if settings.ocr_provider == "vision":
        from app.ingestion.ocr.vision import VisionOcr

        return VisionOcr(
            base_url=settings.ocr_vision_base_url or settings.llm_base_url,
            api_key=settings.ocr_vision_api_key or settings.llm_api_key,
            model=settings.ocr_vision_model,
            timeout_s=settings.llm_timeout_s,
        )
    from app.ingestion.ocr.stub import StubOcr

    return StubOcr()
