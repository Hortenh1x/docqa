"""The corpus v2 spec: deterministic, consistent, and every number traceable to one fact."""

from collections import Counter

from scripts.corpus_v2.spec import build


def test_build_is_deterministic():
    facts_a, docs_a = build()
    facts_b, docs_b = build()
    assert [(f.id, f.text_en, f.doc) for f in facts_a] == [
        (f.id, f.text_en, f.doc) for f in facts_b
    ]
    assert [d.doc_id for d in docs_a] == [d.doc_id for d in docs_b]


def test_doc_ids_unique_and_every_fact_placed():
    facts, docs = build()
    ids = [d.doc_id for d in docs]
    assert len(ids) == len(set(ids))
    placed = {fid for d in docs for fid in d.facts}
    unplaced = [f.id for f in facts if f.id not in placed]
    assert unplaced == []


def test_generated_values_are_unique_per_unit():
    facts, _ = build()
    # pinned v1 values may legitimately repeat (the same company-wide number in two documents);
    # every other (kind, unit, text) must be unique so a figure traces to one fact
    counts = Counter((f.kind, f.unit, f.text_en) for f in facts)
    repeated = {k: n for k, n in counts.items() if n > 1}
    allowed = {
        ("count", "days", "27 days"),  # vacation (POL-001) and the German handbook
        ("count", "days", "25 days"),  # an old vacation value and the French handbook
        ("percent", "", "50%"),  # partial-day rule, one per yearly rate sheet
        ("money", "", "€2,000"),  # an old equipment budget and the pinned hardship advance
    }
    assert set(repeated) <= allowed, repeated


def test_restricted_sections_are_declared_on_their_documents():
    facts, docs = build()
    by_id = {f.id: f for f in facts}
    for d in docs:
        for fid in d.facts:
            f = by_id[fid]
            if f.label != "all":
                assert d.default_label == f.label or d.restricted.get(f.section) == f.label, (
                    d.doc_id,
                    fid,
                )


def test_mirrors_copy_their_source_facts():
    _, docs = build()
    by_id = {d.doc_id: d for d in docs}
    for d in docs:
        if d.mirror_of:
            assert d.facts == by_id[d.mirror_of].facts
            assert d.lang == "de"
