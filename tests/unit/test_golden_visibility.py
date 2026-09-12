"""Evaluation expectations follow the same whole-section visibility as actual documents."""

from scripts.corpus_v2.make_golden import effective_label, facts_for_document, load


def test_open_fact_inside_restricted_section_cannot_be_an_open_partial():
    fact = {"id": "open-declaration", "section": 3, "label": "all"}
    document = {"default_label": "all", "restricted": {"3": "finance"}, "facts": [fact["id"]]}
    assert effective_label(fact, document) == "finance"
    assert not [f for f in facts_for_document(document, {fact["id"]: fact}) if f["label"] == "all"]
    assert fact["label"] == "all"  # registry values/declarations are not silently rewritten


def test_procurement_golden_uses_actual_section_scope():
    facts, docs = load()
    by_id = {f["id"]: f for f in facts}
    visible = facts_for_document(docs["POL-018-v1.2"], by_id)
    assert {f["label"] for f in visible} == {"finance"}
    assert effective_label(by_id["F2-050"], docs["POL-018-v1.2"]) == "finance"
