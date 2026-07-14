"""Parser tests on fixtures generated at test time (no binaries in the repo)."""

import fitz
import pytest
from docx import Document as DocxBuilder

from app.ingestion.parsers import ParserError, get_parser
from app.ingestion.parsers.markdown import MarkdownParser, PlainTextParser


@pytest.fixture
def pdf_file(tmp_path):
    """Two pages; headings in a larger font than the body."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "1. Introduction", fontsize=20)
    for i in range(6):
        page.insert_text(
            (72, 130 + i * 18), f"Body line {i} about the vacation policy.", fontsize=11
        )
    page.insert_text((72, 260), "1.1 Scope", fontsize=15)
    page.insert_text((72, 290), "This section applies to all employees.", fontsize=11)
    page2 = doc.new_page()
    page2.insert_text((72, 80), "2. Carryover", fontsize=20)
    page2.insert_text((72, 130), "Unused days expire on March 31.", fontsize=11)
    path = tmp_path / "sample.pdf"
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def docx_file(tmp_path):
    builder = DocxBuilder()
    builder.add_heading("Travel Policy", level=1)
    builder.add_paragraph("Trips must be booked two weeks in advance.")
    builder.add_heading("Per-diem rates", level=2)
    table = builder.add_table(rows=3, cols=2)
    for row, (country, rate) in zip(
        table.rows, [("Country", "Rate"), ("DE", "€28"), ("PT", "€24")], strict=True
    ):
        row.cells[0].text, row.cells[1].text = country, rate
    path = tmp_path / "sample.docx"
    builder.save(path)
    return path


def test_pdf_pages_and_headings(pdf_file):
    parsed = get_parser("application/pdf").parse(pdf_file)

    assert [p.number for p in parsed.pages] == [1, 2]
    page1, page2 = parsed.pages
    assert [text for _, text in page1.headings] == ["1. Introduction", "1.1 Scope"]
    # 20pt clusters above 15pt: outer heading gets a shallower level
    level_intro = page1.headings[0][0]
    level_scope = page1.headings[1][0]
    assert level_intro < level_scope
    assert page2.headings == [(level_intro, "2. Carryover")]
    assert "Body line 0 about the vacation policy." in page1.text
    # contract: every heading appears as its own block, in order
    blocks = page1.text.split("\n\n")
    assert "1. Introduction" in blocks
    assert "1.1 Scope" in blocks


def test_pdf_rejects_garbage(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4 not really a pdf")
    with pytest.raises(ParserError):
        get_parser("application/pdf").parse(bad)


def test_docx_headings_and_table(docx_file):
    parsed = get_parser(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ).parse(docx_file)

    assert len(parsed.pages) == 1
    page = parsed.pages[0]
    assert page.number is None
    assert page.headings == [(1, "Travel Policy"), (2, "Per-diem rates")]
    assert "| Country | Rate |" in page.text
    assert "| DE | €28 |" in page.text
    assert "| --- | --- |" in page.text


def test_markdown_headings_and_fences(tmp_path):
    md = tmp_path / "sample.md"
    md.write_text(
        "# Title\n\nIntro paragraph.\n\n## Section A\n\ntext a\n\n"
        "```\n# not a heading, just code\n```\n\n### Deep\n\nmore\n",
        encoding="utf-8",
    )
    parsed = MarkdownParser().parse(md)
    page = parsed.pages[0]

    assert page.headings == [(1, "Title"), (2, "Section A"), (3, "Deep")]
    assert "# not a heading, just code" in page.text
    blocks = page.text.split("\n\n")
    assert "Section A" in blocks  # heading text is its own block, hash stripped


def test_plain_text(tmp_path):
    txt = tmp_path / "sample.txt"
    txt.write_text("just one paragraph\nwith two lines", encoding="utf-8")
    parsed = PlainTextParser().parse(txt)

    assert len(parsed.pages) == 1
    assert parsed.pages[0].number is None
    assert parsed.pages[0].headings == []
    assert "just one paragraph" in parsed.pages[0].text


def test_registry_rejects_unknown_mime():
    with pytest.raises(ParserError):
        get_parser("application/zip")
