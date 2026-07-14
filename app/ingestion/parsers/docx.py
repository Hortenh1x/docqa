"""DOCX parser (python-docx).

Paragraphs styled ``Heading N`` become headings of level N. Tables are converted to
Markdown tables so tabular facts (per-diem rates, budgets) survive chunking intact.
DOCX has no page geometry — the whole document is one ParsedPage with number=None.
"""

import re
from pathlib import Path

from docx import Document as load_docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.parsers.base import ParsedDocument, ParsedPage, ParserError

_HEADING_STYLE_RE = re.compile(r"^Heading (\d)$", re.IGNORECASE)


def _cell_text(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _table_to_markdown(table: Table) -> str:
    rows = [[_cell_text(cell.text) for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)


class DocxParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            document = load_docx(str(path))
        except Exception as exc:
            raise ParserError(f"cannot open DOCX: {exc}") from exc

        blocks: list[str] = []
        headings: list[tuple[int, str]] = []

        for item in document.iter_inner_content():
            if isinstance(item, Table):
                markdown = _table_to_markdown(item)
                if markdown:
                    blocks.append(markdown)
                continue
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if not text:
                    continue
                style_name = (item.style.name if item.style is not None else "") or ""
                match = _HEADING_STYLE_RE.match(style_name)
                if match:
                    level = int(match.group(1))
                    headings.append((level, text))
                blocks.append(text)

        return ParsedDocument(
            pages=[ParsedPage(number=None, text="\n\n".join(blocks), headings=headings)]
        )
