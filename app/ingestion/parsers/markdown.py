"""Markdown and plain-text parsers.

Markdown: ATX headings (``#`` … ``######``) become headings; hashes inside fenced code
blocks are ignored. A YAML front matter block is not text a reader would see: its known
keys (doc id, version, dates, owner, classification) are rendered as one metadata line —
the same header the PDF/DOCX builds carry — and an ``access:`` key becomes a standalone
``Access: …`` marker line so document-level restrictions survive; unknown keys are
dropped. Plain text: one page, no headings.
"""

import re
from pathlib import Path

from app.ingestion.parsers.base import ParsedDocument, ParsedPage, ParserError

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```|~~~)")
_FRONT_MATTER_RE = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", re.S)
_HEADER_KEYS = ("doc_id", "version", "effective_date", "supersedes", "owner", "classification")


def split_front_matter(source: str) -> tuple[dict[str, str], str]:
    """(front matter as key → value, body without it). Tolerates quoted values."""
    match = _FRONT_MATTER_RE.match(source)
    if not match:
        return {}, source
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        key, value = line.split(":", 1)
        value = value.split(" #", 1)[0].strip().strip("\"'")
        if value:
            meta[key.strip().lower()] = value
    return meta, source[match.end() :]


def front_matter_blocks(meta: dict[str, str]) -> list[str]:
    blocks: list[str] = []
    parts = [f"{key.replace('_', ' ').title()}: {meta[key]}" for key in _HEADER_KEYS if key in meta]
    if parts:
        blocks.append(" · ".join(parts))
    if meta.get("access"):
        blocks.append(f"Access: {meta['access']}")
    return blocks


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParserError(f"cannot read file: {exc}") from exc


class MarkdownParser:
    def parse(self, path: Path) -> ParsedDocument:
        meta, source = split_front_matter(_read_text(path))
        blocks: list[str] = front_matter_blocks(meta)
        headings: list[tuple[int, str]] = []
        paragraph: list[str] = []
        in_fence = False

        def flush() -> None:
            if paragraph:
                blocks.append("\n".join(paragraph))
                paragraph.clear()

        for line in source.splitlines():
            if _FENCE_RE.match(line.strip()):
                in_fence = not in_fence
                paragraph.append(line)
                continue
            if not in_fence:
                match = _HEADING_RE.match(line)
                if match:
                    flush()
                    level, text = len(match.group(1)), match.group(2).strip()
                    headings.append((level, text))
                    blocks.append(text)
                    continue
                if not line.strip():
                    flush()
                    continue
            paragraph.append(line)
        flush()

        return ParsedDocument(
            pages=[ParsedPage(number=None, text="\n\n".join(blocks), headings=headings)]
        )


class PlainTextParser:
    def parse(self, path: Path) -> ParsedDocument:
        return ParsedDocument(pages=[ParsedPage(number=None, text=_read_text(path).strip())])
