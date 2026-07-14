"""MIME allowlist shared by the upload service and the parser registry."""

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
MARKDOWN_MIME = "text/markdown"
TEXT_MIME = "text/plain"

EXT_BY_MIME = {
    PDF_MIME: ".pdf",
    DOCX_MIME: ".docx",
    MARKDOWN_MIME: ".md",
    TEXT_MIME: ".txt",
}

TEXT_EXT_MIME = {".md": MARKDOWN_MIME, ".markdown": MARKDOWN_MIME, ".txt": TEXT_MIME}
