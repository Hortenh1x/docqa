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


# --- access labels ---


def _md(text: str, headings: list[tuple[int, str]]) -> ParsedDocument:
    return ParsedDocument(pages=[ParsedPage(number=None, text=text, headings=headings)])


def test_marker_labels_section_and_subsections_until_next_same_level(small_chunks):
    text = "\n\n".join(
        [
            "1. Purpose",
            sentences(6, "Open"),
            "7. Calibration",
            "Access: Managers only",
            sentences(6, "Restricted"),
            "7.1 Ratings",
            sentences(6, "Inherited"),
            "8. Questions",
            sentences(6, "OpenAgain"),
        ]
    )
    headings = [(2, "1. Purpose"), (2, "7. Calibration"), (3, "7.1 Ratings"), (2, "8. Questions")]

    chunks = chunk_document(_md(text, headings))

    by_path = {c.section_path: c.access_label for c in chunks}
    assert by_path["1. Purpose"] == "all"
    assert by_path["7. Calibration"] == "managers"
    assert by_path["7. Calibration > 7.1 Ratings"] == "managers"  # inherited
    assert by_path["8. Questions"] == "all"  # reset at the next same-level heading
    assert "Access: Managers only" in next(
        c.content for c in chunks if c.section_path == "7. Calibration"
    )


def test_marker_before_first_heading_labels_the_whole_document(small_chunks):
    text = "\n\n".join(
        [
            "Doc Id: EXEC-001",
            "Access: Leadership only",
            "Compensation Bands",
            sentences(6, "Intro"),
            "2. Bands",
            sentences(6, "Bands"),
            "3. Budget",
            sentences(6, "Budget"),
        ]
    )
    headings = [(1, "Compensation Bands"), (2, "2. Bands"), (2, "3. Budget")]

    chunks = chunk_document(_md(text, headings))

    assert chunks and all(c.access_label == "leadership" for c in chunks)


def test_sections_with_different_labels_are_never_merged(small_chunks):
    # two tiny sections would normally share one chunk — not when their labels differ
    text = "\n\n".join(
        ["1. Open", "Short open text.", "2. Closed", "Access: HR only", "Short closed text."]
    )
    headings = [(2, "1. Open"), (2, "2. Closed")]

    chunks = chunk_document(_md(text, headings))

    assert [c.access_label for c in chunks] == ["all", "hr"]
    assert "Short closed text." not in chunks[0].content
    assert "Short open text." not in chunks[1].content


def test_sections_with_the_same_label_still_merge(small_chunks):
    text = "\n\n".join(
        ["1. A", "Access: HR only", "Short a.", "2. B", "Access: HR only", "Short b."]
    )
    headings = [(2, "1. A"), (2, "2. B")]

    chunks = chunk_document(_md(text, headings))

    assert len(chunks) == 1 and chunks[0].access_label == "hr"


def test_long_restricted_section_windows_all_carry_the_label(small_chunks):
    text = "\n\n".join(["9. Disclosure", "Access: Leadership only", sentences(40, "Long")])
    chunks = chunk_document(_md(text, [(2, "9. Disclosure")]))

    assert len(chunks) >= 2
    assert all(c.access_label == "leadership" for c in chunks)


def test_marker_only_counts_right_after_a_heading(small_chunks):
    # a marker-looking line buried mid-section is ordinary text
    text = "\n\n".join(
        ["1. Purpose", sentences(3, "Open"), "Access: Finance only", sentences(3, "More")]
    )
    chunks = chunk_document(_md(text, [(2, "1. Purpose")]))

    assert all(c.access_label == "all" for c in chunks)


def test_unknown_group_fails_closed(small_chunks):
    text = "\n\n".join(["4. Rates", "Access: Finannce only", sentences(3, "Rates")])
    chunks = chunk_document(_md(text, [(2, "4. Rates")]))

    assert all(c.access_label == "leadership" for c in chunks)


def test_marker_survives_pdf_rendering(tmp_path, small_chunks):
    import fitz

    from app.ingestion.parsers.pdf import PdfParser

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "1. Purpose", fontsize=20)
    page.insert_text((72, 110), "Everyone may read this paragraph about travel.", fontsize=11)
    page.insert_text((72, 160), "8. Card limits", fontsize=20)
    page.insert_text((72, 190), "Access: Finance only", fontsize=11)
    page.insert_text(
        (72, 220), "The single-transaction limit needs CFO approval above it.", fontsize=11
    )
    path = tmp_path / "fin.pdf"
    doc.save(path)
    doc.close()

    chunks = chunk_document(PdfParser().parse(path))

    labels = {c.section_path: c.access_label for c in chunks}
    assert labels["1. Purpose"] == "all"
    assert labels["8. Card limits"] == "finance"
