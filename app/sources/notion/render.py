"""Notion blocks → Markdown the existing MarkdownParser understands.

Rules that matter downstream:

- The page title is the ``#`` heading; Notion ``heading_n`` becomes ``#`` × (n+1), so
  breadcrumbs read "Page > Section > Subsection".
- Blocks are separated by blank lines (the chunker splits on them); list items of one
  list stay in one block.
- Callouts render as plain paragraphs so an ``Access: <group> only`` marker survives
  (a ``>`` or emoji prefix would hide it from ``parse_access_marker``).
- Child pages / databases are not inlined: they are documents of their own. A link line
  keeps the relationship readable.
"""

from collections.abc import Callable, Iterator
from typing import Any

BlockChildren = Callable[[str], Iterator[dict[str, Any]]]

_LIST_TYPES = {"bulleted_list_item", "numbered_list_item", "to_do"}
_MAX_DEPTH = 8


def rich_text(parts: list[dict[str, Any]] | None) -> str:
    out: list[str] = []
    for part in parts or []:
        text = str(part.get("plain_text") or "")
        if not text:
            continue
        kind = part.get("type")
        if kind == "equation":
            text = f"${text}$"
        elif kind == "mention":
            mention = part.get("mention") or {}
            if mention.get("type") == "date":
                date = mention.get("date") or {}
                text = str(date.get("start") or text)
                if date.get("end"):
                    text = f"{text} → {date['end']}"
        annotations = part.get("annotations") or {}
        if annotations.get("code"):
            text = f"`{text}`"
        else:
            if annotations.get("bold"):
                text = f"**{text}**"
            if annotations.get("italic"):
                text = f"*{text}*"
            if annotations.get("strikethrough"):
                text = f"~~{text}~~"
        href = part.get("href")
        if href and kind == "text":
            text = f"[{text}]({href})"
        out.append(text)
    return "".join(out).replace("\x00", "")


def page_title(page: dict[str, Any]) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            title = rich_text(prop.get("title"))
            if title:
                return title
    if page.get("object") == "database":
        title = rich_text(page.get("title"))
        if title:
            return title
    return "Untitled"


def _property_value(prop: dict[str, Any]) -> str | None:
    kind = prop.get("type")
    value = prop.get(kind) if kind else None
    if value is None:
        return None
    match kind:
        case "title" | "rich_text":
            return rich_text(value) or None
        case "number":
            return str(value)
        case "select" | "status":
            return str(value.get("name") or "") or None
        case "multi_select":
            return ", ".join(str(v.get("name") or "") for v in value) or None
        case "date":
            start, end = value.get("start"), value.get("end")
            return f"{start} → {end}" if start and end else (str(start) if start else None)
        case "checkbox":
            return "yes" if value else "no"
        case "url" | "email" | "phone_number":
            return str(value)
        case "people":
            return ", ".join(str(p.get("name") or "") for p in value if p.get("name")) or None
        case "files":
            return ", ".join(str(f.get("name") or "") for f in value if f.get("name")) or None
        case "formula" | "rollup":
            inner_kind = value.get("type")
            inner = value.get(inner_kind) if inner_kind else None
            if inner is None or isinstance(inner, list | dict):
                return None
            return str(inner)
        case "unique_id":
            prefix, number = value.get("prefix"), value.get("number")
            return f"{prefix}-{number}" if prefix else (str(number) if number is not None else None)
        case "created_time" | "last_edited_time":
            return str(value)
    return None  # relation, created_by, people ids, etc. are not readable text


def page_properties(page: dict[str, Any]) -> list[tuple[str, str]]:
    """Readable (name, value) pairs of a database row, title excluded."""
    rows: list[tuple[str, str]] = []
    for name, prop in (page.get("properties") or {}).items():
        if prop.get("type") == "title":
            continue
        value = _property_value(prop)
        if value:
            rows.append((str(name), value))
    return rows


class MarkdownRenderer:
    def __init__(self, children_of: BlockChildren) -> None:
        self._children_of = children_of

    def render_page(self, page: dict[str, Any], blocks: list[dict[str, Any]]) -> str:
        title = page_title(page)
        parts: list[str] = [f"# {title}"]
        props = (
            page_properties(page) if (page.get("parent") or {}).get("type") == "database_id" else []
        )
        if props:
            parts.append("\n".join(f"- {name}: {value}" for name, value in props))
        parts.extend(self._render_blocks(blocks, depth=0))
        return "\n\n".join(part for part in parts if part.strip()) + "\n"

    # -- blocks ----------------------------------------------------------------------

    def _render_blocks(self, blocks: list[dict[str, Any]], depth: int) -> list[str]:
        out: list[str] = []
        list_lines: list[str] = []
        numbered = 0

        def flush_list() -> None:
            nonlocal numbered
            if list_lines:
                out.append("\n".join(list_lines))
                list_lines.clear()
            numbered = 0

        for block in blocks:
            kind = block.get("type")
            if kind in _LIST_TYPES:
                if kind == "numbered_list_item":
                    numbered += 1
                    marker = f"{numbered}."
                elif kind == "to_do":
                    checked = bool((block.get("to_do") or {}).get("checked"))
                    marker = "- [x]" if checked else "- [ ]"
                else:
                    marker = "-"
                    numbered = 0
                text = rich_text((block.get(kind) or {}).get("rich_text"))
                list_lines.append(f"{marker} {text}".rstrip())
                for child in self._children_markdown(block, depth):
                    list_lines.extend("  " + line for line in child.splitlines())
                continue
            flush_list()
            out.extend(self._render_block(block, depth))
        flush_list()
        return out

    def _children_markdown(self, block: dict[str, Any], depth: int) -> list[str]:
        if not block.get("has_children") or depth >= _MAX_DEPTH:
            return []
        if block.get("type") in ("child_page", "child_database"):
            return []
        children = list(self._children_of(str(block["id"])))
        return self._render_blocks(children, depth + 1)

    def _render_block(self, block: dict[str, Any], depth: int) -> list[str]:
        kind = str(block.get("type") or "")
        data = block.get(kind) or {}
        text = rich_text(data.get("rich_text")) if isinstance(data, dict) else ""
        match kind:
            case "paragraph":
                return (
                    [text] + self._children_markdown(block, depth)
                    if text
                    else self._children_markdown(block, depth)
                )
            case "heading_1" | "heading_2" | "heading_3":
                level = int(kind[-1]) + 1
                head = [f"{'#' * level} {text}"] if text else []
                return head + self._children_markdown(block, depth)
            case "quote":
                lines = ["> " + line for line in text.splitlines()] or []
                return ["\n".join(lines)] + self._children_markdown(block, depth) if lines else []
            case "callout":
                return ([text] if text else []) + self._children_markdown(block, depth)
            case "toggle":
                return ([f"**{text}**"] if text else []) + self._children_markdown(block, depth)
            case "code":
                language = str(data.get("language") or "")
                return [f"```{language}\n{text}\n```"]
            case "equation":
                expression = str(data.get("expression") or "")
                return [f"$$ {expression} $$"] if expression else []
            case "divider":
                return ["---"]
            case "table":
                return self._render_table(block)
            case "child_page":
                title = str(data.get("title") or "Untitled")
                return [f"Sub-page: {title}"]
            case "child_database":
                title = str(data.get("title") or "Untitled")
                return [f"Database: {title}"]
            case "bookmark" | "embed" | "link_preview":
                url = str(data.get("url") or "")
                caption = rich_text(data.get("caption"))
                label = caption or url
                return [f"[{label}]({url})"] if url else []
            case "image" | "file" | "pdf" | "video" | "audio":
                caption = rich_text(data.get("caption"))
                name = str(data.get("name") or "")
                label = caption or name
                return [f"[{kind}: {label}]"] if label else []
            case "link_to_page":
                return []
            case "column_list" | "column" | "synced_block":
                return self._children_markdown(block, depth)
            case "table_of_contents" | "breadcrumb" | "unsupported" | "template":
                return []
        # unknown block types: keep any text they carry rather than dropping content
        return ([text] if text else []) + self._children_markdown(block, depth)

    def _render_table(self, block: dict[str, Any]) -> list[str]:
        rows: list[list[str]] = []
        for row in self._children_of(str(block["id"])):
            cells = (row.get("table_row") or {}).get("cells") or []
            rows.append([rich_text(cell).replace("|", "\\|").replace("\n", " ") for cell in cells])
        if not rows:
            return []
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        has_header = bool((block.get("table") or {}).get("has_column_header"))
        header = rows[0] if has_header else [""] * width
        body = rows[1:] if has_header else rows
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in range(width)) + " |",
        ]
        lines.extend("| " + " | ".join(r) + " |" for r in body)
        return ["\n".join(lines)]
