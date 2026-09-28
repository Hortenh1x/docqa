"""Notion blocks → Markdown: the shape the MarkdownParser and the chunker rely on."""

from app.sources.notion.render import MarkdownRenderer, page_properties, page_title, rich_text


def _t(text, **ann):
    return {"type": "text", "plain_text": text, "annotations": ann, "text": {"content": text}}


def _block(kind, text=None, children=None, **extra):
    block = {"id": f"id-{kind}-{abs(hash(text)) % 10_000}", "type": kind, "has_children": False}
    data = dict(extra)
    if text is not None:
        data["rich_text"] = [_t(text)]
    block[kind] = data
    if children:
        block["has_children"] = True
        block["_children"] = children
    return block


def _renderer(*blocks):
    index = {}

    def collect(items):
        for item in items:
            index[item["id"]] = item.get("_children", [])
            collect(item.get("_children", []))

    collect(blocks)
    return MarkdownRenderer(lambda block_id: iter(index.get(block_id, []))), list(blocks)


PAGE = {
    "object": "page",
    "id": "p1",
    "url": "https://notion.so/p1",
    "parent": {"type": "workspace", "workspace": True},
    "properties": {"title": {"type": "title", "title": [_t("Travel policy")]}},
}


def test_rich_text_annotations_links_and_mentions():
    parts = [
        _t("bold", bold=True),
        _t(" and "),
        _t("code", code=True),
        {"type": "text", "plain_text": "site", "href": "https://x.y", "annotations": {}},
        {
            "type": "mention",
            "plain_text": "@Alice",
            "annotations": {},
            "mention": {"type": "user"},
        },
        {
            "type": "mention",
            "plain_text": "date",
            "annotations": {},
            "mention": {"type": "date", "date": {"start": "2026-01-01", "end": "2026-01-03"}},
        },
        {"type": "equation", "plain_text": "E=mc^2", "annotations": {}},
    ]
    assert (
        rich_text(parts)
        == "**bold** and `code`[site](https://x.y)@Alice2026-01-01 → 2026-01-03$E=mc^2$"
    )


def test_page_renders_title_headings_lists_and_blank_line_blocks():
    renderer, blocks = _renderer(
        _block("heading_1", "Scope"),
        _block("paragraph", "Applies to all employees."),
        _block("bulleted_list_item", "Flights"),
        _block(
            "bulleted_list_item",
            "Hotels",
            children=[_block("bulleted_list_item", "Max 150 EUR")],
        ),
        _block("numbered_list_item", "First"),
        _block("numbered_list_item", "Second"),
        _block("to_do", "Book", checked=True),
        _block("heading_2", "Per-diems"),
        _block("quote", "Keep receipts."),
        _block("code", "print(1)", language="python"),
        _block("divider"),
        _block("child_page", title="Country supplement"),
    )
    md = renderer.render_page(PAGE, blocks)
    assert md.startswith("# Travel policy\n\n## Scope\n\nApplies to all employees.\n\n")
    assert "- Flights\n- Hotels\n  - Max 150 EUR\n1. First\n2. Second\n- [x] Book\n\n" in md
    assert "\n\n### Per-diems\n\n> Keep receipts.\n\n```python\nprint(1)\n```\n\n---\n\n" in md
    assert md.endswith("Sub-page: Country supplement\n")


def test_callout_access_marker_stays_a_plain_block():
    """An ``Access: … only`` callout must survive as its own block: the chunker only
    recognises the marker at the start of a block."""
    renderer, blocks = _renderer(
        _block("heading_1", "Bonus pool"),
        _block("callout", "Access: leadership only", icon={"emoji": "🔒"}),
        _block("paragraph", "The pool is 1.2 M EUR."),
    )
    md = renderer.render_page(PAGE, blocks)
    assert "## Bonus pool\n\nAccess: leadership only\n\nThe pool is 1.2 M EUR." in md


def test_table_renders_as_markdown_table_with_escaped_pipes():
    table = _block(
        "table",
        table_width=2,
        has_column_header=True,
        children=[
            {
                "id": "r1",
                "type": "table_row",
                "table_row": {"cells": [[_t("Country")], [_t("Rate")]]},
            },
            {
                "id": "r2",
                "type": "table_row",
                "table_row": {"cells": [[_t("DE")], [_t("28 | 14")]]},
            },
        ],
    )
    renderer, blocks = _renderer(table)
    md = renderer.render_page(PAGE, blocks)
    assert "| Country | Rate |\n| --- | --- |\n| DE | 28 \\| 14 |" in md


def test_database_row_lists_readable_properties_before_body():
    row = {
        "object": "page",
        "id": "row",
        "parent": {"type": "database_id", "database_id": "db"},
        "properties": {
            "Name": {"type": "title", "title": [_t("Berlin office")]},
            "Country": {"type": "select", "select": {"name": "DE"}},
            "Tags": {"type": "multi_select", "multi_select": [{"name": "eu"}, {"name": "hq"}]},
            "Seats": {"type": "number", "number": 120},
            "Opened": {"type": "date", "date": {"start": "2020-05-01", "end": None}},
            "Active": {"type": "checkbox", "checkbox": True},
            "Owner": {"type": "people", "people": [{"name": "Kim"}]},
            "Link": {"type": "relation", "relation": [{"id": "x"}]},
            "Total": {"type": "formula", "formula": {"type": "number", "number": 3.5}},
            "Key": {"type": "unique_id", "unique_id": {"prefix": "OFF", "number": 7}},
        },
    }
    assert page_title(row) == "Berlin office"
    assert page_properties(row) == [
        ("Country", "DE"),
        ("Tags", "eu, hq"),
        ("Seats", "120"),
        ("Opened", "2020-05-01"),
        ("Active", "yes"),
        ("Owner", "Kim"),
        ("Total", "3.5"),
        ("Key", "OFF-7"),
    ]
    renderer, blocks = _renderer(_block("paragraph", "Body."))
    md = renderer.render_page(row, blocks)
    assert md.startswith("# Berlin office\n\n- Country: DE\n- Tags: eu, hq\n")
    assert md.endswith("- Key: OFF-7\n\nBody.\n")


def test_untitled_and_unknown_blocks_keep_text():
    renderer, blocks = _renderer(
        _block(
            "column_list",
            children=[_block("column", children=[_block("paragraph", "In a column")])],
        ),
        _block("toggle", "Details", children=[_block("paragraph", "Hidden text")]),
        _block("mystery_block", "Still text"),
        _block("bookmark", url="https://example.com"),
        _block("image", caption=[_t("Org chart")]),
    )
    md = renderer.render_page({"object": "page", "properties": {}}, blocks)
    assert md.startswith("# Untitled\n\nIn a column\n\n**Details**\n\nHidden text\n\nStill text")
    assert "[https://example.com](https://example.com)" in md
    assert "[image: Org chart]" in md


def test_nul_bytes_never_reach_markdown():
    assert rich_text([_t("a\x00b")]) == "ab"
