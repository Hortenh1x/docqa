"""Validate generated documents against the manifest and the fact registry.

Per document: front matter, headings, access markers, every assigned fact value in its
section, no value of any *other* fact, no digits outside the whitelist, no forbidden
topic, length. ``validate_document`` returns a list of human-readable findings (empty =
accepted) — the generator feeds them back to the LLM; the CLI runs the whole corpus.

Usage: uv run python -m scripts.corpus_v2.validate [--docs corpus/large/docs]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

from scripts.corpus_v2.spec import FORBIDDEN_TOPICS

ROOT = Path("corpus/large")

_MARKERS_EN = {
    "managers": "Access: Managers only",
    "hr": "Access: People & Culture only",
    "finance": "Access: Finance only",
    "leadership": "Access: Leadership only",
}
_MARKERS_DE = {
    "managers": "Zugriff: nur Führungskräfte",
    "hr": "Zugriff: nur People & Culture",
    "finance": "Zugriff: nur Finanzen",
    "leadership": "Zugriff: nur Geschäftsführung",
}

_ALLOWED_NUMBER_PATTERNS = [
    r"^##\s*\d+\.",  # handled per line, not here
]
_WHITELIST_RE = re.compile(
    r"§\s?\d+(?:\.\d+)?"  # section refs
    r"|\b[A-Z]{2,5}(?:-[A-Z0-9]+)*-\d[\dA-Z-]*(?:-v\d+(?:\.\d+)?)?\b"  # doc ids incl. -v2.3
    r"|\bv\d+\.\d+\b|\bversion \d+\.\d+\b|\bVersion \d+\.\d+\b"  # versions
    r"|\b\d{4}-\d{2}-\d{2}\b|\b20\d\d-\d\d\b"  # ISO dates, year-month
    r"|\b(?:1 January|January 1|31 December|December 31|1\. Januar|31\. Dezember)\b"  # year boundaries  # noqa: E501
    r"|\b(?:20[1-2]\d)\b"  # years
    r"|\b\d{1,2}:\d{2}\b"  # times (meeting notes)
    r"|\bQ[1-4]\b|\b1Password\b|\bP[1-4]\b"  # quarters, the tool, priorities
    r"|\b(?:[Pp]riority|[Ss]everity|[Ll]evel|[Tt]ier|[Ss]tep|[Pp]hase)[ -][1-5]\b|\b1:1s?\b"
    r"|\bp\d{2}(?:\.\d)?\b|\b\d{2}(?:th|st|nd|rd) percentile\b"  # p95, 99th percentile
    r"|^#{1,3}\s*\d+(?:\.\d+)*\.?\s",  # numbered headings
    re.M,
)
_NUMBER_RE = re.compile(r"\d[\d.,]*")


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, text[m.end() :]


def _sections(body: str) -> list[tuple[int, str, str]]:
    """(number, heading text, section text) for every '## N. Title' heading."""
    out: list[tuple[int, str, str]] = []
    matches = list(re.finditer(r"^##\s*(\d+)\.\s*(.+?)\s*$", body, re.M))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append((int(m.group(1)), m.group(2).strip(), body[m.end() : end]))
    return out


def _first_paragraph(section_text: str) -> str:
    for block in section_text.split("\n\n"):
        if block.strip():
            return block.strip()
    return ""


def _value_regex(value: str, lang: str = "en") -> re.Pattern[str]:
    # separators count as "inside a number": "5%" must not match inside "3.5%", nor "500" in "1,500"
    core = re.escape(value)
    if lang == "de" and value.endswith("e"):
        core += "n?"  # dative plural: "20 Kalendertagen", "36 Monaten", "3 Jahren"
    return re.compile(r"(?<![\w€$.,])" + core + r"(?![\w%]|[.,]\d)")


def validate_document(
    doc: dict[str, Any],
    text: str,
    facts: dict[str, dict[str, Any]],
    all_facts: list[dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    lang = doc["lang"]
    meta, body = _split_front_matter(text)
    if not meta:
        return ["Missing YAML front matter at the top (--- … ---)."]
    if meta.get("doc_id") != doc["doc_id"]:
        errors.append(f"front matter doc_id must be {doc['doc_id']}")
    if doc["default_label"] != "all" and not meta.get("access"):
        errors.append("front matter must contain the 'access:' line for a restricted document")

    # title + document-level marker
    title_m = re.search(r"^#\s+(.+?)\s*$", body, re.M)
    if not title_m:
        errors.append("missing '# Title' line")
    elif doc["default_label"] != "all":
        after = body[title_m.end() :]
        marker = (_MARKERS_EN if lang == "en" else _MARKERS_DE)[doc["default_label"]]
        if _first_paragraph(after) != marker:
            errors.append(f"the paragraph right after the title must be exactly: {marker}")

    # headings
    sections = _sections(body)
    numbers = [n for n, _, _ in sections]
    expected = list(range(1, len(doc["sections"]) + 1))
    if numbers != expected:
        errors.append(f"section headings must be numbered {expected} in order; found {numbers}")
    if lang == "en":
        for n, heading, _ in sections:
            if n <= len(doc["sections"]) and heading != doc["sections"][n - 1]:
                errors.append(
                    f"heading {n} must be exactly '{doc['sections'][n - 1]}' (found '{heading}')"
                )
    by_number = {n: txt for n, _, txt in sections}

    # section markers
    restricted = {int(k): v for k, v in doc["restricted"].items()}
    for n, label in restricted.items():
        marker = (_MARKERS_EN if lang == "en" else _MARKERS_DE)[label]
        if n in by_number and _first_paragraph(by_number[n]) != marker:
            errors.append(f"section {n} must start with the standalone line: {marker}")

    # facts present, in the right section
    assigned_texts: set[str] = set()
    for fid in doc["facts"]:
        f = facts[fid]
        value = f["text_en"] if lang == "en" else f["text_de"]
        assigned_texts.add(value)
        haystack = body if len(doc["sections"]) == 1 else by_number.get(f["section"], "")
        if not _value_regex(value, lang).search(haystack):
            where = "the document" if len(doc["sections"]) == 1 else f"section {f['section']}"
            if _value_regex(value, lang).search(body):
                errors.append(f'the value "{value}" must be stated in {where}, not elsewhere')
            else:
                errors.append(f'missing fact in {where}: the exact value "{value}" must appear')

    # the document's own values and title are not "other numbers": scrub them before the
    # leak and stray-digit checks ("€25 per month" here must not read as OPS-EVENTS' "€25")
    scrubbed = body
    for value in sorted(assigned_texts, key=len, reverse=True):
        scrubbed = _value_regex(value, lang).sub(" ", scrubbed)
    scrubbed = scrubbed.replace(doc.get("title", "\0"), " ")

    # references to other documents
    for m in doc["mentions"]:
        ref = m["ref"]
        if not re.search(re.escape(ref) + r"(?:-v[\d.]+)?\b", body):
            errors.append(
                f"must refer to document {ref} by id (reference without quoting its value)"
            )

    # leaks: values of facts that do not belong here
    for f in all_facts:
        value = f["text_en"] if lang == "en" else f["text_de"]
        if value in assigned_texts:
            continue
        if _value_regex(value, lang).search(scrubbed):
            errors.append(f'remove "{value}": it is a figure from another document ({f["doc"]})')
            if len(errors) > 30:
                break

    # digits outside the whitelist
    scrubbed = _WHITELIST_RE.sub(" ", scrubbed)
    stray = sorted(
        {m.group(0).strip(".,") for m in _NUMBER_RE.finditer(scrubbed) if m.group(0).strip(".,")}
    )
    if stray:
        errors.append(
            "digits that are not allowed (remove or rephrase without numbers): "
            + ", ".join(stray[:12])
        )

    # forbidden topics
    lowered = body.lower()
    hits = [t for t in FORBIDDEN_TOPICS if t.lower() in lowered]
    if hits:
        errors.append("forbidden topics mentioned: " + ", ".join(hits))

    # length
    words = len(re.findall(r"\S+", body))
    lo, hi = doc["words"]
    if words < lo * 0.75:
        errors.append(f"too short: {words} words, need at least {lo}")
    if words > hi * 1.3:
        errors.append(f"too long: {words} words, at most {hi}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    facts = {f["id"]: f for f in yaml.safe_load((ROOT / "facts.yaml").read_text(encoding="utf-8"))}
    docs = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    docs_by_id = {d["doc_id"]: d for d in docs}
    all_facts = list(facts.values())
    missing, failed, ok = [], 0, 0
    for doc in docs:
        path = args.docs / f"{doc['doc_id']}.md"
        if not path.exists():
            missing.append(doc["doc_id"])
            continue
        errors = validate_document(
            doc, path.read_text(encoding="utf-8"), facts, all_facts, docs_by_id
        )
        if errors:
            failed += 1
            print(f"FAIL {doc['doc_id']}: " + " | ".join(errors[:4]))
        else:
            ok += 1
    # forbidden topics across the corpus (belt and braces)
    print(
        f"\n{ok} ok, {failed} failed, {len(missing)} missing"
        + (f" ({', '.join(missing[:8])}…)" if missing else "")
    )
    if failed or missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
