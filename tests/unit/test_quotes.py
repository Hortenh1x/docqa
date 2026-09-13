"""Pinpoint quotes: the QUOTES section is split off the stream, parsed and located."""

import uuid

from app.generation.prompts import ContextBlock
from app.generation.quotes import (
    QuoteSplitter,
    fallback_spans,
    locate,
    parse_quotes,
    resolve_quotes,
)
from app.retrieval.base import RetrievedChunk

CHUNK = (
    "Annual leave. Employees receive 27 vacation days per year, accrued monthly.\n"
    "Unused days expire on March 31 of the following year; exceptions need HR approval.\n"
    "| Country | Per-diem |\n| Germany | €28 |\n| France | €35 |"
)


def block(n: int, content: str = CHUNK) -> ContextBlock:
    chunk = RetrievedChunk(
        chunk_id=n,
        document_id=uuid.uuid4(),
        filename="POL-001.md",
        content=content,
        page_start=None,
        page_end=None,
        section_path="Leave",
        score=0.9,
    )
    return ContextBlock(n=n, chunk=chunk, text=content)


# --- stream splitting ---


def feed_all(pieces: list[str]) -> tuple[str, str]:
    splitter = QuoteSplitter()
    out = "".join(splitter.feed(p) for p in pieces)
    out += splitter.flush()
    return out, splitter.section


def test_marker_split_across_deltas_never_reaches_the_answer():
    answer, section = feed_all(
        ["Employees get 27 days [1].", "\n\nQUO", 'TES:\n[1] "27 vacation days', ' per year"\n']
    )
    assert answer == "Employees get 27 days [1]."
    assert section.strip() == '[1] "27 vacation days per year"'


def test_no_marker_releases_everything():
    answer, section = feed_all(["Plain answer ", "with two", " deltas."])
    assert answer == "Plain answer with two deltas."
    assert section == ""


def test_marker_variants_are_recognised():
    for marker in ["QUOTES:", "**QUOTES:**", "Quotes:", "QUOTES"]:
        answer, section = feed_all([f'Answer [1].\n{marker}\n[1] "x"'])
        assert answer == "Answer [1].", marker
        assert '[1] "x"' in section, marker


def test_marker_at_flush_without_trailing_newline():
    answer, section = feed_all(["Answer [1].\n\nQUOTES:"])
    assert answer == "Answer [1]."
    assert section == ""


def test_word_quotes_inside_prose_is_not_a_marker():
    answer, section = feed_all(["The policy quotes: 27 days [1]. QUOTES are fine mid-line."])
    assert answer == "The policy quotes: 27 days [1]. QUOTES are fine mid-line."
    assert section == ""


def test_hold_back_window_releases_progressively():
    splitter = QuoteSplitter()
    first = splitter.feed("A" * 100)
    assert 0 < len(first) < 100  # most of it flows, a short tail is held
    assert first + splitter.flush() == "A" * 100


# --- parsing ---


def test_parse_quote_lines_tolerates_formatting():
    section = (
        '[1] "Employees receive 27 vacation days per year"\n'
        "- [2]: “Unused days expire on March 31”\n"
        "[3] «Germany | €28»\n"
        "[x] not a citation\n"
        "[4]\n"
    )
    assert parse_quotes(section) == [
        (1, "Employees receive 27 vacation days per year"),
        (2, "Unused days expire on March 31"),
        (3, "Germany | €28"),
    ]


# --- locating ---


def test_locate_exact():
    span = locate("Unused days expire on March 31", CHUNK)
    assert span is not None
    assert CHUNK[span[0] : span[1]] == "Unused days expire on March 31"


def test_locate_normalised_whitespace_and_quotes():
    # the model collapsed the newline and used straight quotes / a hyphen
    span = locate("Employees receive 27 vacation days per year, accrued monthly. Unused", CHUNK)
    assert span is not None
    assert CHUNK[span[0] : span[1]].startswith("Employees receive 27")
    assert CHUNK[span[0] : span[1]].endswith("Unused")
    span = locate("Per-diem | Germany | €28", "Per‑diem | Germany | €28")  # non-breaking hyphen
    assert span == (0, len("Per‑diem | Germany | €28"))


def test_locate_fuzzy_small_deviation():
    span = locate("Unused days expire on March 31st of the following year", CHUNK)
    assert span is not None
    assert "Unused days expire on March 31" in CHUNK[span[0] : span[1]]


def test_locate_rejects_unrelated_text():
    assert locate("The quick brown fox jumps over the lazy dog", CHUNK) is None
    assert locate("", CHUNK) is None


def test_fallback_picks_the_overlapping_sentence():
    spans = fallback_spans("Unused vacation days expire on March 31 [1].", CHUNK)
    assert len(spans) == 1
    assert CHUNK[spans[0][0] : spans[0][1]].startswith("Unused days expire on March 31")


def test_fallback_numbers_anchor_a_translated_claim():
    spans = fallback_spans("Sotrudniki poluchayut 27 dney otpuska [1].", CHUNK)
    assert spans and "27 vacation days" in CHUNK[spans[0][0] : spans[0][1]]


# --- resolution end to end ---


def test_resolve_uses_model_quotes_then_falls_back():
    blocks = [block(1), block(2, "Remote work is allowed two days a week. Equipment is provided.")]
    answer = "Employees receive 27 vacation days [1]. Remote work: two days a week [2]."
    section = (
        '[1] "Employees receive 27 vacation days per year"\n[2] "nothing like this here at all"'
    )
    resolved = resolve_quotes(section, answer, blocks)
    assert [q.method for q in resolved[1]] == ["exact"]
    assert CHUNK[resolved[1][0].start : resolved[1][0].end] == (
        "Employees receive 27 vacation days per year"
    )
    # the bogus quote for [2] is replaced by the overlapping sentence
    assert [q.method for q in resolved[2]] == ["fallback"]
    assert (
        blocks[1]
        .chunk.content[resolved[2][0].start : resolved[2][0].end]
        .startswith("Remote work is allowed two days a week")
    )


def test_resolve_without_section_still_covers_cited_blocks():
    blocks = [block(1)]
    resolved = resolve_quotes("", "Days expire on March 31 [1].", blocks)
    assert resolved[1] and resolved[1][0].method == "fallback"


def test_resolve_ignores_uncited_and_unknown_blocks():
    blocks = [block(1), block(2)]
    resolved = resolve_quotes('[2] "x"\n[7] "y"', "Only [1] is cited.", blocks)
    assert set(resolved) == {1}


def test_resolve_merges_overlapping_spans_and_keeps_order():
    blocks = [block(1)]
    section = (
        '[1] "Unused days expire on March 31"\n'
        '[1] "Employees receive 27 vacation days"\n'
        '[1] "expire on March 31 of the following year"'
    )
    resolved = resolve_quotes(section, "Both facts [1].", blocks)
    spans = [(q.start, q.end) for q in resolved[1]]
    assert spans == sorted(spans)
    assert len(spans) == 2  # the two March-31 quotes overlap and merge
