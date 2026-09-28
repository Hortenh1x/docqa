"""OCR for scanned pages and photos, behind a Protocol (Tesseract offline by default)."""

from app.ingestion.ocr.base import OcrBlock, OcrError, OcrPage, OcrProvider, get_ocr_provider

__all__ = ["OcrBlock", "OcrError", "OcrPage", "OcrProvider", "get_ocr_provider"]
