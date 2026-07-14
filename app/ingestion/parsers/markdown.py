"""Markdown and plain-text parsers.

Markdown: ATX headings (``#`` … ``######``) become headings; hashes inside fenced code
blocks are ignored. Plain text: one page, no headings.
"""

import re
from pathlib import Path

from app.ingestion.parsers.base import ParsedDocument, ParsedPage, ParserError

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```|~~~)")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParserError(f"cannot read file: {exc}") from exc


class MarkdownParser:
    def parse(self, path: Path) -> ParsedDocument:
        source = _read_text(path)
        blocks: list[str] = []
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
