"""MIME allowlist shared by the upload service, storage keys and the parser registry."""

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
MARKDOWN_MIME = "text/markdown"
TEXT_MIME = "text/plain"

# images are OCR'd (one page per image or frame); HEIC/HEIF is what phones produce
IMAGE_MIMES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
}

EXT_BY_MIME = {
    PDF_MIME: ".pdf",
    DOCX_MIME: ".docx",
    MARKDOWN_MIME: ".md",
    TEXT_MIME: ".txt",
    **IMAGE_MIMES,
}

# derived artefacts stored next to the original under the same content address
SEARCHABLE_PDF_EXT = ".ocr.pdf"

STORAGE_EXTENSIONS = frozenset({*EXT_BY_MIME.values(), SEARCHABLE_PDF_EXT})

TEXT_EXT_MIME = {".md": MARKDOWN_MIME, ".markdown": MARKDOWN_MIME, ".txt": TEXT_MIME}

UPLOAD_TYPES_HUMAN = (
    "PDF, DOCX, Markdown, plain text, or an image (PNG, JPEG, TIFF, BMP, WEBP, GIF, HEIC)"
)
