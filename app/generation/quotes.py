"""Pinpoint quotes: which words in a cited passage actually support the claim.

The model ends its answer with a ``QUOTES:`` section — one ``[n] "verbatim passage"`` line
per cited block (prompts.SYSTEM_PROMPT rule 7). Three pieces turn that into character
spans inside the chunk text the client can highlight:

- ``QuoteSplitter`` keeps the section out of the streamed answer. Deltas are released with a
  short hold-back window so a marker split across deltas is still caught; everything after
  the marker is collected, never emitted. The head-of-stream twin is ``SentinelBuffer``.
- ``locate`` finds a quoted string in the chunk: exact, then whitespace/quote/dash-normalised
  (with an index map back to the original offsets), then fuzzy. Models paraphrase a little
  even when told not to; a near miss must not lose the highlight.
- ``fallback_spans`` needs no model quote at all: the chunk sentence with the largest
  lexical overlap with the answer sentence that carries ``[n]`` (numbers count double —
  they anchor a claim even when the answer is in another language than the document).

Offsets are into ``chunk.content``; the prompt's block text is an exact prefix of it.
"""

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.generation.prompts import ContextBlock

# a line that is only the word QUOTES, optionally decorated: "QUOTES:", "**Quotes:**", "QUOTES"
MARKER_RE = re.compile(
    r"(?:^|\n)[ \t]*[*_#>\-]*[ \t]*quotes[ \t]*:?[ \t]*[*_]*[ \t]*(?=\n|$)", re.I
)
QUOTE_LINE_RE = re.compile(r"^\s*[-*•]?\s*\[(\d+)\]\s*:?\s*(.*?)\s*$")
CITATION_RE = re.compile(r"\[(\d+)\]")
_SENTENCE_RE = re.compile(r"(?<=[.!?…;])\s+|\n+")
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_WRAPPING_QUOTES = "\"“”„«»‟'‘’‚‹›`"

HOLD_BACK = 24  # longer than any decorated marker, short enough to be invisible
FUZZY_MIN_RATIO = 0.75
MIN_QUOTE_CHARS = 3


class QuoteSplitter:
    """Release answer text as it streams; swallow the QUOTES section at the tail."""

    def __init__(self) -> None:
        self._pending = ""
        self._section = ""
        self._collecting = False

    @property
    def section(self) -> str:
        return self._section

    def feed(self, text: str) -> str:
        if self._collecting:
            self._section += text
            return ""
        self._pending += text
        match = MARKER_RE.search(self._pending)
        if match:
            head = self._pending[: match.start()]
            self._section = self._pending[match.end() :]
            self._pending = ""
            self._collecting = True
            return head.rstrip()
        if len(self._pending) <= HOLD_BACK:
            return ""
        out, self._pending = self._pending[:-HOLD_BACK], self._pending[-HOLD_BACK:]
        return out

    def flush(self) -> str:
        """Call at stream end: releases a held tail that never became the marker."""
        if self._collecting:
            return ""
        match = MARKER_RE.search(self._pending)
        if match:
            head = self._pending[: match.start()]
            self._section = self._pending[match.end() :]
            self._pending = ""
            self._collecting = True
            return head.rstrip()
        out, self._pending = self._pending, ""
        return out


def parse_quotes(section: str) -> list[tuple[int, str]]:
    quotes: list[tuple[int, str]] = []
    for line in section.splitlines():
        match = QUOTE_LINE_RE.match(line)
        if not match:
            continue
        text = match.group(2).strip().strip(_WRAPPING_QUOTES).strip()
        if len(text) >= MIN_QUOTE_CHARS:
            quotes.append((int(match.group(1)), text))
    return quotes


# --- normalisation with an index map back to the source text ---

_CHAR_MAP = str.maketrans(
    {
        **dict.fromkeys("“”„«»‟", '"'),
        **dict.fromkeys("‘’‚‹›", "'"),
        **dict.fromkeys("–—‑−", "-"),
    }
)


def _normalise(text: str) -> tuple[str, list[int]]:
    """Casefold, unify quotes/dashes, collapse whitespace; ``index[i]`` is the offset in
    ``text`` of the character that produced ``out[i]``."""
    out: list[str] = []
    index: list[int] = []
    in_space = False
    for i, raw in enumerate(text):
        if raw.isspace():
            if in_space:
                continue
            in_space = True
            out.append(" ")
            index.append(i)
            continue
        in_space = False
        out.append(raw.translate(_CHAR_MAP).casefold())
        index.append(i)
    return "".join(out), index


def _fuzzy_span(norm_text: str, norm_quote: str) -> tuple[int, int] | None:
    """Best window of the text that resembles the quote (ratio ≥ FUZZY_MIN_RATIO), trimmed
    to its first and last matching characters."""
    m = len(norm_quote)
    if m == 0 or len(norm_text) < m // 2:
        return None
    stride = max(1, m // 4)
    best: tuple[float, int] | None = None
    for start in range(0, max(1, len(norm_text) - m // 2), stride):
        window = norm_text[start : start + m + m // 4]
        matcher = SequenceMatcher(None, window, norm_quote, autojunk=False)
        if matcher.quick_ratio() < FUZZY_MIN_RATIO:
            continue
        ratio = matcher.ratio()
        if ratio >= FUZZY_MIN_RATIO and (best is None or ratio > best[0]):
            best = (ratio, start)
    if best is None:
        return None
    start = best[1]
    window = norm_text[start : start + m + m // 4]
    matcher = SequenceMatcher(None, window, norm_quote, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size]
    if not blocks:
        return None
    return start + blocks[0].a, start + blocks[-1].a + blocks[-1].size


def _locate(quote: str, text: str) -> tuple[int, int, str] | None:
    quote = quote.strip()
    if len(quote) < MIN_QUOTE_CHARS or not text:
        return None
    at = text.find(quote)
    if at >= 0:
        return at, at + len(quote), "exact"
    norm_text, index = _normalise(text)
    norm_quote, _ = _normalise(quote)
    norm_quote = norm_quote.strip()
    if not norm_quote:
        return None
    at = norm_text.find(norm_quote)
    if at >= 0:
        return index[at], index[at + len(norm_quote) - 1] + 1, "normalized"
    span = _fuzzy_span(norm_text, norm_quote)
    if span is not None and span[1] > span[0]:
        return index[span[0]], index[span[1] - 1] + 1, "fuzzy"
    return None


def locate(quote: str, text: str) -> tuple[int, int] | None:
    """Character span of ``quote`` inside ``text`` (exact → normalised → fuzzy), or None."""
    found = _locate(quote, text)
    return (found[0], found[1]) if found else None


# --- lexical fallback ---


def _sentences(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_RE.finditer(text):
        if match.start() > start:
            spans.append((start, match.start()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _tokens(text: str) -> set[str]:
    return {t.casefold() for t in _TOKEN_RE.findall(text) if len(t) >= 3 or t.isdigit()}


def _overlap(claim: set[str], sentence: str) -> float:
    shared = claim & _tokens(sentence)
    if not shared:
        return 0.0
    # numbers count double: "27" or "2025" pins a claim regardless of language
    score = sum(2.0 if t.isdigit() else 1.0 for t in shared)
    # mild length penalty so a long paragraph does not win on volume alone
    return score / (1.0 + math.log1p(len(sentence) / 200.0))


def fallback_spans(claim: str, content: str) -> list[tuple[int, int]]:
    """The chunk sentence(s) that overlap the claim the most; empty when nothing overlaps."""
    tokens = _tokens(CITATION_RE.sub(" ", claim))
    if not tokens:
        return []
    sentences = _sentences(content)
    scored = [(_overlap(tokens, content[s:e]), i) for i, (s, e) in enumerate(sentences)]
    best_score, best = max(scored, default=(0.0, -1))
    if best < 0 or best_score <= 0:
        return []
    chosen = {best}
    # take an adjacent sentence that carries most of the same evidence (a claim that spans
    # two sentences, or a table header plus its row)
    for neighbour in (best - 1, best + 1):
        if 0 <= neighbour < len(sentences) and scored[neighbour][0] >= 0.6 * best_score:
            chosen.add(neighbour)
    return _merge([sentences[i] for i in sorted(chosen)])


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# --- resolution ---


@dataclass(frozen=True)
class Quote:
    start: int
    end: int
    method: str  # exact | normalized | fuzzy | fallback


def cited_blocks(answer: str, blocks: list[ContextBlock]) -> list[int]:
    """Block numbers cited in the answer, first-appearance order, unknown ones dropped."""
    known = {b.n for b in blocks}
    seen: list[int] = []
    for match in CITATION_RE.finditer(answer):
        n = int(match.group(1))
        if n in known and n not in seen:
            seen.append(n)
    return seen


def resolve_quotes(section: str, answer: str, blocks: list[ContextBlock]) -> dict[int, list[Quote]]:
    """Spans per cited block: the model's quotes where they can be located, otherwise the
    best-overlapping chunk sentence, otherwise an empty list (the client shows the whole
    passage)."""
    by_n = {b.n: b for b in blocks}
    quoted: dict[int, list[str]] = {}
    for n, text in parse_quotes(section):
        quoted.setdefault(n, []).append(text)
    claims = [s for s in re.split(r"(?<=[.!?…])\s+|\n+", answer) if s.strip()]

    resolved: dict[int, list[Quote]] = {}
    for n in cited_blocks(answer, blocks):
        content = by_n[n].chunk.content
        located = [
            (hit[0], hit[1], hit[2])
            for text in quoted.get(n, [])
            if (hit := _locate(text, content)) is not None
        ]
        if located:
            rank = {"exact": 0, "normalized": 1, "fuzzy": 2}
            resolved[n] = [
                Quote(
                    s,
                    e,
                    # a merged span is as trustworthy as its least certain member
                    max((m for ls, le, m in located if ls < e and le > s), key=rank.__getitem__),
                )
                for s, e in _merge([(ls, le) for ls, le, _ in located])
            ]
            continue
        spans = _merge(
            [
                span
                for claim in claims
                if f"[{n}]" in claim
                for span in fallback_spans(claim, content)
            ]
        )
        resolved[n] = [Quote(s, e, "fallback") for s, e in spans]
    return resolved
