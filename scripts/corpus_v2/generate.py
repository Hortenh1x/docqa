"""Generate corpus/large/docs/*.md from the manifest and the fact registry.

One LLM call per document with the document's own fact slice; the validator runs on the
result and its findings are fed back for up to ``--retries`` regenerations. Resumable:
documents that already exist are skipped unless ``--force``. German mirrors are rendered
after their English sources (they translate the generated English text).

Usage:
  uv run python -m scripts.corpus_v2.generate [--limit N] [--only PREFIX] [--concurrency 4]
"""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path
from typing import Any

import yaml

from scripts.corpus_v2.llm import complete, make_llm
from scripts.corpus_v2.spec import FORBIDDEN_TOPICS
from scripts.corpus_v2.validate import validate_document

ROOT = Path("corpus/large")
DOCS = ROOT / "docs"

LABEL_NAMES_EN = {
    "managers": "Managers",
    "hr": "People & Culture",
    "finance": "Finance",
    "leadership": "Leadership",
}
LABEL_NAMES_DE = {
    "managers": "Führungskräfte",
    "hr": "People & Culture",
    "finance": "Finanzen",
    "leadership": "Geschäftsführung",
}


def marker(label: str, lang: str) -> str:
    if lang == "de":
        return f"Zugriff: nur {LABEL_NAMES_DE[label]}"
    return f"Access: {LABEL_NAMES_EN[label]} only"


def load() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    facts = {f["id"]: f for f in yaml.safe_load((ROOT / "facts.yaml").read_text(encoding="utf-8"))}
    docs = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    return facts, docs


def front_matter(doc: dict[str, Any]) -> str:
    lines = ["---", f"doc_id: {doc['doc_id']}", f"title: {doc['title']}"]
    if doc["version"]:
        lines.append(f'version: "{doc["version"]}"')
    lines.append(f"effective_date: {doc['effective_date']}")
    if doc["supersedes"]:
        lines.append(f'supersedes: "{doc["supersedes"]}"')
    lines.append(f"owner: {doc['owner']}")
    lines.append(
        "classification: " + ("confidential" if doc["default_label"] != "all" else "internal")
    )
    if doc["default_label"] != "all":
        lines.append(f"access: {LABEL_NAMES_EN[doc['default_label']]} only")
    lines.append("---")
    return "\n".join(lines)


def section_heading(n: int, title: str) -> str:
    return f"## {n}. {title}"


def build_prompt(
    doc: dict[str, Any], facts: dict[str, dict[str, Any]], mirror_text: str | None
) -> str:
    lang = doc["lang"]
    lines: list[str] = []
    if mirror_text:
        lines.append(
            "Translate the English document below into German, keeping its structure exactly "
            "(same front matter with the doc_id given below, same headings translated, same "
            "sections, same facts). Use the German value strings listed under FACTS. Output "
            "ONLY the German markdown, no commentary, no code fences.\n"
        )
    else:
        lines.append(
            "Write the document specified below as Markdown. Output ONLY the markdown document "
            "(front matter first), no commentary, no code fences.\n"
        )
    lines.append("FRONT MATTER (copy exactly, then leave one blank line):")
    lines.append(front_matter(doc))
    lines.append("")
    lines.append(f"TITLE LINE: # {doc['title']}")
    if doc["default_label"] != "all":
        lines.append(
            f"Right after the title line, as its own paragraph, the exact line: {marker(doc['default_label'], lang)}"  # noqa: E501
        )
    lines.append("")
    lines.append(
        "SECTION HEADINGS (exactly these, in this order, numbered like this"
        + (", translated into German" if lang == "de" else "")
        + "):"
    )
    restricted = {int(k): v for k, v in doc["restricted"].items()}
    for i, title in enumerate(doc["sections"], start=1):
        line = section_heading(i, title)
        if i in restricted:
            line += f"   ← the first paragraph of this section must be exactly the line: {marker(restricted[i], lang)}"  # noqa: E501
        lines.append(line)
    lo, hi = doc["words"]
    lines.append("")
    lines.append(f"LENGTH: {lo}–{hi} words.")
    lines.append("")
    doc_facts = [facts[fid] for fid in doc["facts"]]
    if doc_facts:
        lines.append(
            "FACTS TO STATE — each in the section given, in a natural sentence; the wording may vary, "  # noqa: E501
            "the value string must appear EXACTLY as written (same digits, symbols and unit words):"
        )
        tables: dict[str, list[dict[str, Any]]] = {}
        for f in doc_facts:
            value = f["text_en"] if lang == "en" else f["text_de"]
            if f.get("table"):
                tables.setdefault(f["table"], []).append(f)
                continue
            statement = f["statement"].replace("{value}", value)
            lines.append(f'- §{f["section"]}: {statement}   [value: "{value}"]')
        for rows in tables.values():
            section = rows[0]["section"]
            lines.append(
                f"- §{section}: a markdown table (header row + one row per item, values exactly as "
                "given) — "
                + "; ".join(
                    f"{r['row_label']}: {(r['text_en'] if lang == 'en' else r['text_de'])}"
                    for r in rows
                )
                + ". The table is the only place these values appear — do not restate them in prose."  # noqa: E501
            )
    else:
        lines.append("FACTS TO STATE: none — this document contains no figures at all.")
    if doc["mentions"]:
        lines.append("")
        lines.append(
            "REFERENCES WITHOUT VALUES (mention the other document by id, never its number):"
        )
        for m in doc["mentions"]:
            lines.append(f"- {m['note']}")
    if doc["notes"]:
        lines.append("")
        lines.append("NOTES:")
        for n in doc["notes"]:
            lines.append(f"- {n}")
    if doc.get("date_context"):
        lines.append(f"- The notes are dated {doc['date_context']}.")
    lines.append("")
    lines.append("NUMBER RULES (strict — the document is rejected otherwise):")
    lines.append(
        "- The only digits allowed in the body are: the fact values above, the section numbers in "
        "headings and cross references (§3), document ids (POL-004, FIN-RATES-2026), version numbers "  # noqa: E501
        "and dates from the front matter, and plain years."
    )
    lines.append(
        "- No other amounts, counts, percentages, deadlines, durations, times, phone numbers, postal "  # noqa: E501
        "codes or step counts. Write 'a few days' or 'promptly' rather than inventing a figure; "
        "spelled-out numbers ('two weeks') that define a rule are not allowed either."
    )
    lines.append(
        "- No derived or computed figures either (no 'half of the rate is …', no worked examples "
        "with amounts, no dates other than plain years and the front-matter date); example "
        "scenarios describe situations in words only."
    )
    lines.append("- Never quote figures from other documents — refer to them by id.")
    lines.append("- Never mention: " + ", ".join(FORBIDDEN_TOPICS) + ".")
    if lang == "de":
        lines.append("- Write German prose throughout (Sie-Form for policies, natural German).")
    if mirror_text:
        lines.append("")
        lines.append("ENGLISH SOURCE DOCUMENT:")
        lines.append(mirror_text)
    return "\n".join(lines)


SYSTEM = (
    "You are a meticulous technical writer producing an internal document corpus for a fictional "
    "company. You follow structural instructions exactly and never invent numbers.\n\n"
)


def clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    if not text.startswith("---"):
        idx = text.find("\n---")
        if idx != -1:
            text = text[idx + 1 :]
    return text.strip() + "\n"


async def generate_one(
    doc: dict[str, Any],
    facts: dict[str, dict[str, Any]],
    all_facts: list[dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
    llm: Any,
    retries: int,
    semaphore: asyncio.Semaphore,
    style: str,
) -> bool:
    path = DOCS / f"{doc['doc_id']}.md"
    mirror_text = None
    if doc.get("mirror_of"):
        source = DOCS / f"{doc['mirror_of']}.md"
        if not source.exists():
            print(f"  {doc['doc_id']}: source {doc['mirror_of']} missing, skipped")
            return False
        mirror_text = source.read_text(encoding="utf-8")
    prompt = build_prompt(doc, facts, mirror_text)
    feedback = ""
    async with semaphore:
        for attempt in range(retries + 1):
            text = clean(await complete(llm, SYSTEM + style, prompt + feedback))
            errors = validate_document(doc, text, facts, all_facts, docs_by_id)
            if not errors:
                path.write_text(text, encoding="utf-8")
                print(f"  {doc['doc_id']} ok" + (f" (attempt {attempt + 1})" if attempt else ""))
                return True
            feedback = (
                "\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED. Fix ALL of the following and output the "
                "complete document again:\n- " + "\n- ".join(errors[:12])
            )
            print(
                f"  {doc['doc_id']} attempt {attempt + 1} rejected: {errors[0]}"
                + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else "")
            )
    (ROOT / "rejected").mkdir(exist_ok=True)
    (ROOT / "rejected" / f"{doc['doc_id']}.md").write_text(text, encoding="utf-8")
    (ROOT / "rejected" / f"{doc['doc_id']}.errors.txt").write_text(
        "\n".join(errors), encoding="utf-8"
    )
    return False


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default="", help="doc id prefix filter (comma-separated)")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    facts, docs = load()
    all_facts = list(facts.values())
    docs_by_id = {d["doc_id"]: d for d in docs}
    style = (ROOT / "style.md").read_text(encoding="utf-8")
    DOCS.mkdir(parents=True, exist_ok=True)
    llm = make_llm(args.model, max_tokens=8000)

    selected = docs
    if args.only:
        prefixes = tuple(p.strip() for p in args.only.split(","))
        selected = [d for d in docs if d["doc_id"].startswith(prefixes)]
    if not args.force:
        selected = [d for d in selected if not (DOCS / f"{d['doc_id']}.md").exists()]
    if args.limit:
        selected = selected[: args.limit]
    sources = [d for d in selected if not d.get("mirror_of")]
    mirrors = [d for d in selected if d.get("mirror_of")]
    print(
        f"generating {len(sources)} documents + {len(mirrors)} mirrors with {args.model or 'deepseek-chat'}…"  # noqa: E501
    )

    semaphore = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(
        *(
            generate_one(d, facts, all_facts, docs_by_id, llm, args.retries, semaphore, style)
            for d in sources
        )
    )
    results += await asyncio.gather(
        *(
            generate_one(d, facts, all_facts, docs_by_id, llm, args.retries, semaphore, style)
            for d in mirrors
        )
    )
    ok = sum(1 for r in results if r)
    print(f"done: {ok}/{len(results)} accepted; rejected ones are in {ROOT / 'rejected'}")


if __name__ == "__main__":
    from app.db.base import dispose_engine

    async def _run() -> None:
        try:
            await main()
        finally:
            await dispose_engine()

    asyncio.run(_run())
