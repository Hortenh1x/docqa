"""Section-aware chunking.

The unit of chunking is a section (text between headings). Small adjacent sections are
merged into one chunk (up to the target size); a section longer than the target is cut
with a sliding sentence window (target ~450 tokens, overlap 60, hard cap 512). Markdown
tables are kept atomic; oversized tables are split by rows with the header repeated.

Tokens are counted with tiktoken's ``o200k_base`` as a universal approximation — for
bge-m3 it is inexact but stable; when the encoding cannot be loaded (offline), a
whitespace-based heuristic is used instead. Exactness is not required: the hard cap sits
far below embedding context limits.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.config import get_settings
from app.ingestion.access import LABEL_ALL, parse_access_marker
from app.ingestion.parsers.base import ParsedDocument

if TYPE_CHECKING:
    from tiktoken import Encoding

log = structlog.get_logger("docqa.chunking")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class ChunkDraft:
    chunk_index: int
    content: str
    token_count: int
    page_start: int | None
    page_end: int | None
    section_path: str | None
    access_label: str = LABEL_ALL


class TokenCounter:
    _encoding: "Encoding | None"

    def __init__(self) -> None:
        try:
            import tiktoken

            self._encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            self._encoding = None
            log.warning("tiktoken_unavailable", fallback="whitespace heuristic")

    def count(self, text: str) -> int:
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return max(1, round(len(text.split()) * 1.3))

    def hard_split(self, text: str, max_tokens: int) -> list[str]:
        """Last resort for a single monster sentence: split by token slices."""
        if self._encoding is not None:
            tokens = self._encoding.encode(text)
            return [
                self._encoding.decode(tokens[i : i + max_tokens])
                for i in range(0, len(tokens), max_tokens)
            ]
        words = text.split()
        per_piece = max(1, int(max_tokens / 1.3))
        return [" ".join(words[i : i + per_piece]) for i in range(0, len(words), per_piece)]


@dataclass
class _Block:
    text: str
    page: int | None
    tokens: int


@dataclass
class _Section:
    path: str | None
    blocks: list[_Block]
    access_label: str = LABEL_ALL

    @property
    def tokens(self) -> int:
        return sum(b.tokens for b in self.blocks)


def _is_table(block: str) -> bool:
    return block.lstrip().startswith("|")


def _build_sections(parsed: ParsedDocument, counter: TokenCounter) -> list[_Section]:
    """Sections with heading breadcrumbs and access labels.

    Access labels (app/ingestion/access.py): a marker block right after a heading labels
    that heading's section; sub-sections inherit the label of their nearest ancestor
    heading; a marker before the first heading labels the whole document. The marker
    stays in the text (the LLM sees "Access: … only" like a reader would).
    """
    sections: list[_Section] = []
    stack: list[tuple[int, str, str]] = []  # heading breadcrumbs: (level, text, label)
    current: list[_Block] = []
    current_path: str | None = None
    doc_label = LABEL_ALL
    current_label = LABEL_ALL
    after_heading = False

    def close() -> None:
        nonlocal current
        if current:
            sections.append(_Section(path=current_path, blocks=current, access_label=current_label))
            current = []

    for page in parsed.pages:
        pending = list(page.headings)
        for raw_block in page.text.split("\n\n"):
            block = raw_block.strip()
            if not block:
                continue
            if pending and block == pending[0][1]:
                level, text = pending.pop(0)
                close()
                parents = [h for h in stack if h[0] < level]
                inherited = parents[-1][2] if parents else doc_label
                stack[:] = parents + [(level, text, inherited)]
                current_path = " > ".join(h[1] for h in stack)
                current_label = inherited
                after_heading = True
                # the heading itself opens the section content — it helps retrieval
                current.append(_Block(text=text, page=page.number, tokens=counter.count(text)))
                continue
            if after_heading or not stack:
                label = parse_access_marker(block)
                if label is not None:
                    if stack:
                        level, text, _ = stack[-1]
                        stack[-1] = (level, text, label)
                    else:
                        doc_label = label
                    current_label = label
            after_heading = False
            current.append(_Block(text=block, page=page.number, tokens=counter.count(block)))
    close()
    return sections


def _split_table(block: _Block, counter: TokenCounter, max_tokens: int) -> list[_Block]:
    """Split an oversized markdown table by rows, repeating the header in every piece."""
    lines = block.text.splitlines()
    if len(lines) < 3:
        return [block]
    header, rows = lines[:2], lines[2:]
    pieces: list[_Block] = []
    bucket: list[str] = []
    for row in rows:
        candidate = "\n".join(header + bucket + [row])
        if bucket and counter.count(candidate) > max_tokens:
            text = "\n".join(header + bucket)
            pieces.append(_Block(text=text, page=block.page, tokens=counter.count(text)))
            bucket = []
        bucket.append(row)
    if bucket:
        text = "\n".join(header + bucket)
        pieces.append(_Block(text=text, page=block.page, tokens=counter.count(text)))
    return pieces


def _sentence_units(section: _Section, counter: TokenCounter, max_tokens: int) -> list[_Block]:
    units: list[_Block] = []
    for block in section.blocks:
        if _is_table(block.text):
            if block.tokens > max_tokens:
                units.extend(_split_table(block, counter, max_tokens))
            else:
                units.append(block)
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(block.text):
            sentence = sentence.strip()
            if not sentence:
                continue
            tokens = counter.count(sentence)
            if tokens > max_tokens:
                for piece in counter.hard_split(sentence, max_tokens):
                    units.append(_Block(text=piece, page=block.page, tokens=counter.count(piece)))
            else:
                units.append(_Block(text=sentence, page=block.page, tokens=tokens))
    return units


def _page_span(blocks: list[_Block]) -> tuple[int | None, int | None]:
    pages = [b.page for b in blocks if b.page is not None]
    return (min(pages), max(pages)) if pages else (None, None)


def _overlap_tail(window: list[_Block], overlap: int) -> list[_Block]:
    """Trailing units totalling >= overlap tokens, bounded to the last half of the window."""
    tail: list[_Block] = []
    tail_tokens = 0
    for prev in reversed(window[len(window) // 2 :]):
        if tail_tokens >= overlap:
            break
        tail.insert(0, prev)
        tail_tokens += prev.tokens
    return tail


def _windows(units: list[_Block], target: int, overlap: int, max_tokens: int) -> list[list[_Block]]:
    """Greedy sliding window over sentence units: aim for target, never exceed max.

    Progress is guaranteed: every iteration either consumes a unit or closes a window
    whose overlap tail is dropped when it cannot coexist with the incoming unit.
    """
    windows: list[list[_Block]] = []
    window: list[_Block] = []
    window_tokens = 0
    tail_only = False  # True while the window holds nothing but the carried-over overlap
    index = 0
    while index < len(units):
        unit = units[index]
        if not window:
            window = [unit]
            window_tokens = unit.tokens
            tail_only = False
            index += 1
            continue
        # a tail-only window may grow to the hard cap so an oversized unit
        # still gets its overlap context; normal windows aim for the target
        allowed = max_tokens if tail_only else target
        if window_tokens + unit.tokens <= allowed:
            window.append(unit)
            window_tokens += unit.tokens
            tail_only = False
            index += 1
            continue
        # the window always contains at least one fresh unit here (tail-only windows
        # only ever reject units that were pre-dropped below), so no duplicate chunks
        windows.append(window)
        tail = _overlap_tail(window, overlap)
        tail_tokens = sum(b.tokens for b in tail)
        if tail_tokens + unit.tokens > max_tokens:
            tail, tail_tokens = [], 0  # overlap impossible next to this unit — drop it
        window = tail
        window_tokens = tail_tokens
        tail_only = bool(tail)
    if window:
        windows.append(window)
    return windows


def chunk_document(parsed: ParsedDocument) -> list[ChunkDraft]:
    settings = get_settings()
    target = settings.chunk_target_tokens
    overlap = settings.chunk_overlap_tokens
    max_tokens = settings.chunk_max_tokens

    counter = TokenCounter()
    sections = _build_sections(parsed, counter)

    drafts: list[ChunkDraft] = []
    buffer: list[_Section] = []

    def flush_buffer() -> None:
        if not buffer:
            return
        blocks = [b for s in buffer for b in s.blocks]
        content = "\n\n".join(b.text for b in blocks)
        page_start, page_end = _page_span(blocks)
        drafts.append(
            ChunkDraft(
                chunk_index=0,
                content=content,
                token_count=counter.count(content),
                page_start=page_start,
                page_end=page_end,
                # merged short sections keep the first section's breadcrumbs
                section_path=buffer[0].path,
                access_label=buffer[0].access_label,
            )
        )
        buffer.clear()

    for section in sections:
        if section.tokens > target:
            flush_buffer()
            units = _sentence_units(section, counter, max_tokens)
            for window in _windows(units, target, overlap, max_tokens):
                content = _join_units(window)
                page_start, page_end = _page_span(window)
                drafts.append(
                    ChunkDraft(
                        chunk_index=0,
                        content=content,
                        token_count=counter.count(content),
                        page_start=page_start,
                        page_end=page_end,
                        section_path=section.path,
                        access_label=section.access_label,
                    )
                )
            continue
        # a chunk carries exactly one access label: sections with different labels are
        # never merged, or a restricted paragraph would ride along in an open chunk
        if buffer and (
            buffer[0].access_label != section.access_label
            or sum(s.tokens for s in buffer) + section.tokens > target
        ):
            flush_buffer()
        buffer.append(section)
    flush_buffer()

    for index, draft in enumerate(drafts):
        draft.chunk_index = index
    return [d for d in drafts if d.content.strip()]


def _join_units(units: list[_Block]) -> str:
    """Sentences flow with spaces; tables stay on their own lines."""
    parts: list[str] = []
    for unit in units:
        if _is_table(unit.text):
            parts.append("\n\n" + unit.text + "\n\n")
        else:
            parts.append(unit.text + " ")
    return "".join(parts).strip()
