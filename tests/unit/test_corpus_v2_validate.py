"""The corpus v2 validator: the rules that keep generated documents faithful to the registry."""

from scripts.corpus_v2.validate import validate_document

FACTS = {
    "F2-001": {
        "id": "F2-001",
        "key": "card.limit",
        "text_en": "€1,500",
        "text_de": "1.500 €",
        "doc": "POL-017",
        "section": 2,
        "label": "finance",
        "statement": "The limit is {value}.",
    },
    "F2-002": {
        "id": "F2-002",
        "key": "growth",
        "text_en": "5%",
        "text_de": "5 %",
        "doc": "FIN-UPD",
        "section": 2,
        "label": "finance",
        "statement": "Revenue grew {value}.",
    },
    "F2-003": {
        "id": "F2-003",
        "key": "budget",
        "text_en": "3.5%",
        "text_de": "3,5 %",
        "doc": "EXEC-COMP",
        "section": 2,
        "label": "leadership",
        "statement": "The budget is {value}.",
    },
}
ALL_FACTS = list(FACTS.values())
DOC = {
    "doc_id": "POL-017-v2.0",
    "lang": "en",
    "default_label": "all",
    "sections": ["Purpose", "Limits"],
    "restricted": {"2": "finance"},
    "facts": ["F2-001"],
    "mentions": [{"fact": "F2-002", "ref": "FIN-UPD", "note": ""}],
    "words": [10, 400],
}
DOCS = {"POL-017-v2.0": DOC}


def _doc(body: str, doc_id: str = "POL-017-v2.0") -> str:
    head = f"---\ndoc_id: {doc_id}\ntitle: Corporate Card Policy\n---\n\n"
    return head + f"# Corporate Card Policy\n\n{body}\n"


GOOD = """## 1. Purpose

Cards make small purchases easy. Our quarterly figures live in FIN-UPD.

## 2. Limits

Access: Finance only

The single-transaction limit is €1,500; larger purchases go through Finance.
"""


def test_good_document_passes():
    assert validate_document(DOC, _doc(GOOD), FACTS, ALL_FACTS, DOCS) == []


def test_missing_front_matter():
    errors = validate_document(DOC, "# Title\n\n## 1. Purpose\n", FACTS, ALL_FACTS, DOCS)
    assert errors == ["Missing YAML front matter at the top (--- … ---)."]


def test_marker_must_open_the_restricted_section():
    body = GOOD.replace("Access: Finance only\n\n", "")
    errors = validate_document(DOC, _doc(body), FACTS, ALL_FACTS, DOCS)
    assert any("must start with the standalone line: Access: Finance only" in e for e in errors)


def test_value_in_the_wrong_section_is_flagged():
    body = GOOD.replace("is €1,500;", "is generous;").replace(
        "Cards make", "The limit is €1,500. Cards make"
    )
    errors = validate_document(DOC, _doc(body), FACTS, ALL_FACTS, DOCS)
    assert any("must be stated in section 2" in e for e in errors)


def test_foreign_value_is_a_leak():
    body = GOOD.replace("larger purchases", "revenue grew 5% and larger purchases")
    errors = validate_document(DOC, _doc(body), FACTS, ALL_FACTS, DOCS)
    assert any('remove "5%"' in e for e in errors)


def test_decimal_prefix_is_not_a_leak():
    # "3.5%" contains "5%" — separators must not create false leaks (and 3.5% is a leak of its own)
    body = GOOD.replace("larger purchases", "3.5% of purchases")
    errors = validate_document(DOC, _doc(body), FACTS, ALL_FACTS, DOCS)
    assert any('remove "3.5%"' in e for e in errors)
    assert not any('remove "5%"' in e for e in errors)


def test_stray_digits_are_flagged_but_whitelist_is_not():
    body = GOOD.replace(
        "Cards make", "Since 2023 (see §2 of POL-004 v3.0, 2025-02-01) cards make"
    ).replace("larger purchases", "purchases above 40 items")
    errors = validate_document(DOC, _doc(body), FACTS, ALL_FACTS, DOCS)
    stray = [e for e in errors if e.startswith("digits that are not allowed")]
    assert stray and "40" in stray[0]
    assert "2023" not in stray[0] and "3.0" not in stray[0] and "2025" not in stray[0]


def test_missing_reference_and_forbidden_topic():
    body = GOOD.replace("live in FIN-UPD", "are elsewhere").replace(
        "Cards make", "No sabbatical here. Cards make"
    )
    errors = validate_document(DOC, _doc(body), FACTS, ALL_FACTS, DOCS)
    assert any("must refer to document FIN-UPD" in e for e in errors)
    assert any("forbidden topics mentioned: sabbatical" in e for e in errors)


def test_document_level_marker_and_front_matter_access():
    doc = {**DOC, "default_label": "finance", "restricted": {}}
    text = _doc(GOOD.replace("Access: Finance only\n\n", ""))
    errors = validate_document(doc, text, FACTS, ALL_FACTS, DOCS)
    assert any("front matter must contain the 'access:' line" in e for e in errors)
    assert any(
        "paragraph right after the title must be exactly: Access: Finance only" in e for e in errors
    )


def test_own_value_with_a_unit_suffix_is_not_a_leak():
    facts = {
        **FACTS,
        "F2-004": {
            "id": "F2-004",
            "key": "internet",
            "text_en": "€25 per month",
            "text_de": "25 € pro Monat",
            "doc": "POL-012",
            "section": 2,
            "label": "all",
            "statement": "{value}",
        },
        "F2-005": {
            "id": "F2-005",
            "key": "events",
            "text_en": "€25",
            "text_de": "25 €",
            "doc": "OPS-EVENTS",
            "section": 2,
            "label": "all",
            "statement": "{value}",
        },
    }
    doc = {**DOC, "facts": ["F2-001", "F2-004"], "restricted": {"2": "finance"}}
    body = GOOD.replace("The single-transaction limit", "The allowance is €25 per month. The limit")
    errors = validate_document(doc, _doc(body), facts, list(facts.values()), DOCS)
    assert errors == []


def test_title_digits_and_ordinals_are_not_stray():
    doc = {**DOC, "title": "Board Memo 1 — 2025"}
    body = GOOD.replace("Cards make", "Priority 2 issues and the p95 target matter. Cards make")
    text = _doc(body).replace("# Corporate Card Policy", "# Board Memo 1 — 2025")
    errors = validate_document(doc, text, FACTS, ALL_FACTS, DOCS)
    assert not any(e.startswith("digits that are not allowed") for e in errors)


def test_german_dative_inflection_is_accepted():
    facts = {
        "F2-009": {
            "id": "F2-009",
            "key": "dsar",
            "text_en": "20 calendar days",
            "text_de": "20 Kalendertage",
            "doc": "POL-010",
            "section": 1,
            "label": "all",
            "statement": "{value}",
        }
    }
    doc = {
        "doc_id": "POL-010-DE",
        "lang": "de",
        "default_label": "all",
        "sections": ["Zweck"],
        "restricted": {},
        "facts": ["F2-009"],
        "mentions": [],
        "words": [5, 400],
        "title": "Datenschutz",
    }
    text = (
        "---\ndoc_id: POL-010-DE\n---\n\n# Datenschutz\n\n## 1. Zweck\n\n"
        "Antworten innerhalb von 20 Kalendertagen.\n"
    )
    assert validate_document(doc, text, facts, list(facts.values()), {}) == []
