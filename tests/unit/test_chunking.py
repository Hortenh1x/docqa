import pytest

from app.config import get_settings
from app.ingestion.chunking import chunk_document
from app.ingestion.parsers.base import ParsedDocument, ParsedPage


@pytest.fixture
def small_chunks(monkeypatch):
    """Shrink chunk sizes so section-boundary behaviour is testable with short texts."""
    monkeypatch.setenv("CHUNK_TARGET_TOKENS", "60")
    monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "15")
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "90")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    yield
    get_settings.cache_clear()


def sentences(n: int, prefix: str = "Sentence") -> str:
    return " ".join(
        f"{prefix} number {i} talks about corporate travel policies and reimbursement rules."
        for i in range(n)
    )


def test_long_section_splits_with_overlap():
    body = sentences(60)  # ~900 tokens >> target 450
    page = ParsedPage(number=1, text=f"Long Section\n\n{body}", headings=[(1, "Long Section")])

    chunks = chunk_document(ParsedDocument(pages=[page]))

    assert len(chunks) >= 2
    assert all(c.token_count <= 512 for c in chunks)
    assert all(c.section_path == "Long Section" for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # sliding window: consecutive chunks share at least one sentence
    for a, b in zip(chunks, chunks[1:], strict=False):
        a_sentences = {s.strip() for s in a.content.split(".") if s.strip()}
        b_sentences = {s.strip() for s in b.content.split(".") if s.strip()}
        assert a_sentences & b_sentences


def test_short_sections_merge_into_one_chunk():
    text = "Alpha\n\nShort alpha text.\n\nBeta\n\nShort beta text.\n\nGamma\n\nShort gamma text."
    page = ParsedPage(number=1, text=text, headings=[(1, "Alpha"), (1, "Beta"), (1, "Gamma")])

    chunks = chunk_document(ParsedDocument(pages=[page]))

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.section_path == "Alpha"  # merged chunks keep the first section's path
    for piece in ("Short alpha text.", "Short beta text.", "Short gamma text."):
        assert piece in chunk.content


def test_chunk_spanning_pages_maps_page_range():
    p1 = ParsedPage(number=1, text="Intro\n\n" + sentences(2), headings=[(1, "Intro")])
    p2 = ParsedPage(number=2, text=sentences(2, prefix="Continuation"), headings=[])

    chunks = chunk_document(ParsedDocument(pages=[p1, p2]))

    assert len(chunks) == 1
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)


def test_pageless_formats_have_null_pages():
    page = ParsedPage(number=None, text="Title\n\nJust some text.", headings=[(1, "Title")])
    chunks = chunk_document(ParsedDocument(pages=[page]))
    assert (chunks[0].page_start, chunks[0].page_end) == (None, None)


def test_nested_breadcrumbs(small_chunks):
    text = (
        "Travel\n\n" + sentences(8, prefix="General") + "\n\n"
        "Per-diems\n\n" + sentences(8, prefix="Rates") + "\n\n"
        "Approvals\n\n" + sentences(8, prefix="Approval")
    )
    page = ParsedPage(
        number=None,
        text=text,
        headings=[(1, "Travel"), (2, "Per-diems"), (2, "Approvals")],
    )

    chunks = chunk_document(ParsedDocument(pages=[page]))
    paths = {c.section_path for c in chunks}

    assert "Travel" in paths
    assert "Travel > Per-diems" in paths
    # a sibling H2 replaces the previous H2 in the breadcrumbs, not nests under it
    assert "Travel > Approvals" in paths


def test_near_max_unit_terminates_and_respects_cap(small_chunks):
    """Regression: an atomic unit close to the hard cap must not stall the window loop
    or produce overlap-only chunks."""
    big_table = "\n".join(
        ["| Key | Value |", "| --- | --- |"]
        + [f"| K{i} | a long value cell with plenty of words inside {i} |" for i in range(10)]
    )
    text = (
        "Data\n\n"
        + sentences(12, prefix="Lead")
        + "\n\n"
        + big_table
        + "\n\n"
        + sentences(12, prefix="Trail")
    )
    page = ParsedPage(number=1, text=text, headings=[(1, "Data")])

    chunks = chunk_document(ParsedDocument(pages=[page]))  # must terminate

    assert all(c.token_count <= 90 for c in chunks)
    assert sum("| K0 |" in c.content for c in chunks) >= 1
    # no chunk consists purely of a repeated overlap of a neighbour
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.content not in a.content


def test_table_rows_stay_together(small_chunks):
    table = "\n".join(
        ["| Country | Rate |", "| --- | --- |"] + [f"| C{i} | €{20 + i} |" for i in range(6)]
    )
    text = "Rates\n\n" + sentences(10, prefix="Filler") + "\n\n" + table
    page = ParsedPage(number=1, text=text, headings=[(1, "Rates")])

    chunks = chunk_document(ParsedDocument(pages=[page]))

    with_table = [c for c in chunks if "| C0 |" in c.content]
    assert len(with_table) == 1
    for i in range(6):
        assert f"| C{i} |" in with_table[0].content  # the table was not torn apart
