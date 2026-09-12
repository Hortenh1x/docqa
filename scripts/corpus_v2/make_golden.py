"""Derive eval/golden_v2.yaml from the fact registry and the manifest.

Every fact yields questions whose answer is its value; the expected sources are known
from the manifest, so recall labels need no human review. The LLM only paraphrases —
it sees one fact at a time (plus its hints), never the rest of the registry, and every
question is checked not to contain the value it asks about.

Categories (see plans/docqa-corpus-v2-plan.md): direct, table, multi_doc, version,
version_history, buried, distractor_country, stale_faq, as_of_date, german, access
(refuse/unlock pairs), partial, no_answer.

Usage: uv run python -m scripts.corpus_v2.make_golden [--out eval/golden_v2.yaml] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

import yaml

from scripts.corpus_v2.llm import complete, make_llm
from scripts.corpus_v2.spec import COUNTRIES, FORBIDDEN_TOPICS

ROOT = Path("corpus/large")

ROLE_FOR_LABEL = {
    "managers": "manager",
    "hr": "hr",
    "finance": "finance",
    "leadership": "leadership",
}
SIBLING_ROLE = {"managers": "employee", "hr": "finance", "finance": "hr", "leadership": "finance"}

ABSENT_TOPICS = [
    "dental insurance",
    "company pension plan",
    "employee discount programme",
    "parking reimbursement",
    "language courses",
    "night shift allowance",
    "long-service awards",
    "volunteering days",
    "birthday leave",
    "jury duty leave",
    "moving-day leave",
    "hazard pay",
    "company phone plan",
    "eye test reimbursement",
    "ergonomic desk assessment",
    "student loan support",
    "housing allowance",
    "on-call bonus payment",
    "meal vouchers",
    "commuter shuttle",
]
ABSENT_TERMS = {
    "dental insurance": ["dental"],
    "company pension plan": ["pension"],
    "employee discount programme": ["discount"],
    "parking reimbursement": ["parking reimburs"],
    "language courses": ["language course"],
    "night shift allowance": ["night shift"],
    "long-service awards": ["long-service", "long service award"],
    "volunteering days": ["volunteer"],
    "birthday leave": ["birthday"],
    "jury duty leave": ["jury"],
    "moving-day leave": ["moving day", "moving-day"],
    "hazard pay": ["hazard pay"],
    "company phone plan": ["phone plan"],
    "eye test reimbursement": ["eye test"],
    "ergonomic desk assessment": ["ergonomic"],
    "student loan support": ["student loan"],
    "housing allowance": ["housing allowance"],
    "on-call bonus payment": ["on-call bonus"],
    "meal vouchers": ["meal voucher"],
    "commuter shuttle": ["shuttle"],
}

SYSTEM = (
    "You write evaluation questions for a document Q&A system used by employees of a fictional "
    "company (Kranich Software GmbH). Output ONLY valid JSON. Questions must be natural, the way an "
    "employee would ask, and must NEVER contain the answer value or any digits."
)


def load() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    facts = yaml.safe_load((ROOT / "facts.yaml").read_text(encoding="utf-8"))
    docs = {
        d["doc_id"]: d for d in yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    }
    return facts, docs


def effective_label(fact: dict[str, Any], document: dict[str, Any]) -> str:
    """A section marker covers every fact in that section, including open declarations."""
    restricted = document.get("restricted", {})
    return str(
        restricted.get(
            str(fact["section"]),
            restricted.get(fact["section"], document.get("default_label", "all")),
        )
    )


def facts_for_document(
    document: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {**by_id[fid], "label": effective_label(by_id[fid], document)} for fid in document["facts"]
    ]


def doc_for_fact(
    fact: dict[str, Any], docs: dict[str, dict[str, Any]], lang: str = "en"
) -> str | None:
    """The doc id (filename stem) holding this fact: the current version of its base."""
    candidates = [
        d
        for d in docs.values()
        if fact["id"] in d["facts"] and d["lang"] == lang and d["family"] != "FAQ"
    ]
    if not candidates:
        return None
    current = [d for d in candidates if not d.get("superseded_by")]
    pick = (current or candidates)[-1]
    return pick["doc_id"]


def category_of(fact: dict[str, Any], docs: dict[str, dict[str, Any]]) -> str:
    fam = fact.get("family") or ""
    if fact["label"] != "all":
        return "access"
    if fam.startswith("meeting:"):
        return "as_of_date"
    if fam.startswith("version:") and not fact["current"]:
        return "version_history"
    if fam.startswith("year:") and not fact["current"]:
        return "version"
    if fam.startswith("country:"):
        return "distractor_country"
    if fact.get("table"):
        return "table"
    if fam.startswith("version:"):
        return "version"
    if fact.get("buried"):
        return "buried"
    return "direct"


def answer_of(fact: dict[str, Any], lang: str = "en") -> str:
    if lang == "de":
        # the registry's statements are English; lead with the German value the answer must contain
        return f"{fact['text_de']} — " + fact["statement"].replace("{value}", fact["text_en"])
    return fact["statement"].replace("{value}", fact["text_en"])


async def paraphrase(
    llm: Any, items: list[dict[str, Any]], lang: str = "en"
) -> dict[str, list[str]]:
    """items: [{id, statement, hints, extra}] → {id: [q1, q2]}"""
    lines = []
    for it in items:
        lines.append(
            json.dumps(
                {
                    "id": it["id"],
                    "fact": it["statement"],
                    "topic_hints": it["hints"],
                    "instructions": it.get("extra", ""),
                },
                ensure_ascii=False,
            )
        )
    language = "German (Sie-Form)" if lang == "de" else "English"
    user = (
        f"For each fact below write TWO {language} questions an employee might ask whose answer is exactly "
        "that fact: the first straightforward, the second paraphrased with different vocabulary (no "
        "shared keywords with the fact beyond the topic itself). Follow each item's instructions. "
        "Never include the value, no digits at all. Return a JSON object mapping id → [q1, q2].\n\n"
        + "\n".join(lines)
    )
    raw = await complete(llm, SYSTEM, user)
    start, end = raw.find("{"), raw.rfind("}")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    out: dict[str, list[str]] = {}
    for k, v in data.items():
        if isinstance(v, list):
            out[k] = [" ".join(str(q).split()) for q in v if isinstance(q, str) and str(q).strip()]
    return out


def _clean_questions(questions: list[str], value: str) -> list[str]:
    """Drop questions that give the answer away: the value text, or its digits (a version
    number such as "2.0" in a history question is fine — "24" for a 24-day allowance is not)."""
    ok = []
    digits = re.sub(r"[^\d]", "", value)
    for q in questions:
        if value.lower() in q.lower():
            continue
        if digits and digits in re.sub(r"[^\d]", "", q):
            continue
        ok.append(q)
    return ok


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("eval/golden_v2.yaml"))
    parser.add_argument("--limit", type=int, default=0, help="facts to process (pilot)")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    facts_all, docs = load()
    by_id = {f["id"]: f for f in facts_all}
    stale_by_key = {f["key"]: f for f in facts_all if f.get("stale_in")}
    facts = facts_all[: args.limit] if args.limit else facts_all
    llm = make_llm(args.model, temperature=0.7, max_tokens=4000)
    semaphore = asyncio.Semaphore(args.concurrency)
    entries: list[dict[str, Any]] = []
    counter = {"n": 0}

    def next_id(prefix: str) -> str:
        counter["n"] += 1
        return f"{prefix}{counter['n']:04d}"

    # ---- fact questions (EN)
    items = []
    for f in facts:
        doc_id = doc_for_fact(f, docs)
        if doc_id is None:
            continue
        f = {**f, "label": effective_label(f, docs[doc_id])}
        cat = category_of(f, docs)
        extra = ""
        if cat == "distractor_country":
            extra = f"Name the country ({COUNTRIES[f['variant']]}) explicitly in both questions."
        elif cat == "version_history":
            extra = (
                f"Both questions ask what the OLD version {f['variant']} of the policy said "
                "(e.g. 'what did the previous vacation policy allow'), not the current rule."
            )
        elif (f.get("family") or "").startswith("year:") and not f["current"]:
            extra = f"Name the year {f['variant']} and the country explicitly."
        elif (f.get("family") or "").startswith("year:"):
            extra = "Ask about the CURRENT per-diem and name the country explicitly."
        elif cat == "as_of_date":
            d = docs[doc_id]
            extra = f"The fact was decided in meeting notes dated {d['effective_date']}; " + (
                "ask what the LATEST decision is."
                if f["current"]
                else f"ask explicitly what was decided in the meeting of {d['effective_date']}."
            )
        elif (f.get("family") or "").startswith(
            ("quarter:", "board:", "okr:", "postmortem:", "team:")
        ):
            extra = (
                f"Mention the specific context ({f['hints'][0]}) so the question is unambiguous."
            )
        items.append(
            {
                "id": f["id"],
                "statement": answer_of(f),
                "hints": f["hints"],
                "extra": extra,
                "fact": f,
                "doc_id": doc_id,
                "cat": cat,
            }
        )

    async def run_batch(batch: list[dict[str, Any]], lang: str) -> dict[str, list[str]]:
        async with semaphore:
            return await paraphrase(llm, batch, lang)

    batches = [items[i : i + 8] for i in range(0, len(items), 8)]
    print(f"paraphrasing {len(items)} facts in {len(batches)} batches…")
    results = await asyncio.gather(*(run_batch(b, "en") for b in batches))
    questions = {k: v for r in results for k, v in r.items()}

    for it in items:
        f, cat, doc_id = it["fact"], it["cat"], it["doc_id"]
        qs = _clean_questions(questions.get(f["id"], []), f["text_en"])[:2]
        if not qs:
            print(f"  no usable question for {f['id']} ({f['key']})")
            continue
        for q in qs:
            if cat == "access":
                label = f["label"]
                entries.append(
                    {
                        "id": next_id("a"),
                        "category": "access",
                        "role": SIBLING_ROLE[label],
                        "question": q,
                        "expected_refusal": True,
                        "hidden_sources": [{"doc": doc_id, "section": str(f["section"])}],
                        "expected_hidden_labels": [label],
                        "hidden_values": [f["text_en"]],
                        "notes": f"{f['id']} {f['key']} under a role without '{label}'",
                    }
                )
                entries.append(
                    {
                        "id": next_id("a"),
                        "category": "access",
                        "role": ROLE_FOR_LABEL[label],
                        "question": q,
                        "expected_answer": answer_of(f),
                        "expected_sources": [{"doc": doc_id, "section": str(f["section"])}],
                        "notes": f"{f['id']} {f['key']} unlocked",
                    }
                )
                continue
            entry = {
                "id": next_id(
                    {
                        "direct": "d",
                        "table": "t",
                        "version": "v",
                        "version_history": "h",
                        "buried": "b",
                        "distractor_country": "c",
                        "as_of_date": "m",
                    }[cat]
                ),
                "category": cat,
                "question": q,
                "expected_answer": answer_of(f),
                "expected_sources": [{"doc": doc_id, "section": str(f["section"])}],
                "notes": f"{f['id']} {f['key']}",
            }
            entries.append(entry)
        # stale FAQ trap: a present-tense question whose current answer lives in the policy
        # while an older FAQ still states the previous value
        stale_old = stale_by_key.get(f["key"]) if f["current"] else None
        if stale_old is not None and len(qs) > 1:
            entries.append(
                {
                    "id": next_id("s"),
                    "category": "stale_faq",
                    "question": qs[1],
                    "expected_answer": answer_of(f),
                    "expected_sources": [{"doc": doc_id, "section": str(f["section"])}],
                    "notes": (
                        f"{stale_old['stale_in'][0]} still states the old value "
                        f"{stale_old['text_en']}; the current policy wins"
                    ),
                }
            )

    # ---- multi_doc: mentions (question from the referring document's angle)
    mention_items = []
    for d in docs.values():
        if d["lang"] != "en" or d.get("superseded_by"):
            continue
        for m in d["mentions"]:
            f = by_id.get(m["fact"])
            if not f or f["label"] != "all":
                continue
            target = doc_for_fact(f, docs)
            if not target or effective_label(f, docs[target]) != "all":
                continue
            mention_items.append(
                {
                    "id": f"{d['doc_id']}|{f['id']}",
                    "statement": answer_of(f),
                    "hints": f["hints"],
                    "extra": (
                        f"The employee is reading '{d['title']}' ({d['doc_id']}), which says this detail is "
                        f"defined in another document; phrase the question from that angle, e.g. mention "
                        f"'{d['title'].lower()}' or the situation it covers."
                    ),
                    "fact": f,
                    "source": d["doc_id"],
                    "target": target,
                }
            )
    m_batches = [mention_items[i : i + 8] for i in range(0, len(mention_items), 8)]
    m_results = await asyncio.gather(*(run_batch(b, "en") for b in m_batches))
    m_questions = {k: v for r in m_results for k, v in r.items()}
    for it in mention_items:
        qs = _clean_questions(m_questions.get(it["id"], []), it["fact"]["text_en"])[:2]
        for q in qs:
            entries.append(
                {
                    "id": next_id("x"),
                    "category": "multi_doc",
                    "question": q,
                    "expected_answer": answer_of(it["fact"]),
                    "expected_sources": [
                        {"doc": it["target"], "section": str(it["fact"]["section"])},
                        {"doc": it["source"], "section": None},
                    ],
                    "notes": f"{it['fact']['id']} via {it['source']}",
                }
            )

    # ---- partial: an open fact + a restricted fact in the same document
    partial_items = []
    for d in docs.values():
        if d["lang"] != "en" or d.get("superseded_by"):
            continue
        fs = facts_for_document(d, by_id)
        open_facts = [f for f in fs if f["label"] == "all"]
        closed = [f for f in fs if f["label"] != "all"]
        if open_facts and closed and d["default_label"] == "all":
            o, c = open_facts[0], closed[0]
            partial_items.append(
                {
                    "id": f"{o['id']}+{c['id']}",
                    "statement": answer_of(o) + " " + answer_of(c),
                    "hints": o["hints"] + c["hints"],
                    "extra": "Ask ONE question that needs BOTH facts to be answered in full.",
                    "open": o,
                    "closed": c,
                    "doc": d["doc_id"],
                }
            )
    p_results = await asyncio.gather(
        *(run_batch(partial_items[i : i + 8], "en") for i in range(0, len(partial_items), 8))
    )
    p_questions = {k: v for r in p_results for k, v in r.items()}
    for it in partial_items:
        qs = _clean_questions(p_questions.get(it["id"], []), it["closed"]["text_en"])
        qs = _clean_questions(qs, it["open"]["text_en"])[:2]
        for q in qs:
            entries.append(
                {
                    "id": next_id("p"),
                    "category": "partial",
                    "role": "employee",
                    "question": q,
                    "expected_answer": answer_of(it["open"])
                    + " (the restricted part is not available at this access level)",
                    "expected_sources": [{"doc": it["doc"], "section": str(it["open"]["section"])}],
                    "hidden_sources": [{"doc": it["doc"], "section": str(it["closed"]["section"])}],
                    "expected_hidden_labels": [it["closed"]["label"]],
                    "hidden_values": [it["closed"]["text_en"]],
                    "notes": f"partial: {it['open']['id']} open + {it['closed']['id']} {it['closed']['label']}",
                }
            )
            entries.append(
                {
                    "id": next_id("p"),
                    "category": "partial",
                    "role": ROLE_FOR_LABEL[it["closed"]["label"]],
                    "question": q,
                    "expected_answer": answer_of(it["open"]) + " " + answer_of(it["closed"]),
                    "expected_sources": [
                        {"doc": it["doc"], "section": str(it["open"]["section"])},
                        {"doc": it["doc"], "section": str(it["closed"]["section"])},
                    ],
                    "notes": f"partial unlocked: {it['open']['id']} + {it['closed']['id']}",
                }
            )

    # ---- german: facts of DE mirrors, asked in German
    de_items = []
    for d in docs.values():
        if d["lang"] != "de" or d["family"] != "DE":
            continue
        for fid in d["facts"]:
            f = by_id[fid]
            if effective_label(f, d) != "all" or not f["current"]:
                continue
            de_items.append(
                {
                    "id": f"{d['doc_id']}|{f['id']}",
                    "statement": answer_of(f, "de"),
                    "hints": f["hints"],
                    "extra": "",
                    "fact": f,
                    "doc": d["doc_id"],
                }
            )
    de_items = de_items[:40]
    de_results = await asyncio.gather(
        *(run_batch(de_items[i : i + 8], "de") for i in range(0, len(de_items), 8))
    )
    de_questions = {k: v for r in de_results for k, v in r.items()}
    for it in de_items:
        qs = _clean_questions(de_questions.get(it["id"], []), it["fact"]["text_de"])[:2]
        for q in qs:
            entries.append(
                {
                    "id": next_id("g"),
                    "category": "german",
                    "question": q,
                    "expected_answer": answer_of(it["fact"], "de"),
                    "expected_sources": [{"doc": it["doc"], "section": str(it["fact"]["section"])}],
                    "notes": f"{it['fact']['id']} German mirror",
                }
            )

    # ---- no_answer: forbidden and absent topics (grep-verified against the corpus sources)
    corpus_text = " ".join(
        p.read_text(encoding="utf-8").lower() for p in (ROOT / "docs").glob("*.md")
    )
    topics = [(t, [t.lower()]) for t in FORBIDDEN_TOPICS] + [
        (t, ABSENT_TERMS[t]) for t in ABSENT_TOPICS
    ]
    na_items = [
        {
            "id": t,
            "statement": f"(there is NO information about: {t})",
            "hints": [t],
            "extra": "Write questions that ASSUME the company has a rule about this topic; they must be "
            "unanswerable from the corpus because the topic does not exist there.",
            "terms": terms,
        }
        for t, terms in topics
        if not any(term in corpus_text for term in terms)
    ]
    na_casual = [
        {**it, "extra": it["extra"] + " Casual, first-person phrasing."} for it in na_items
    ]
    na_formal = [
        {**it, "extra": it["extra"] + " Formal phrasing, as if asking HR or Finance in writing."}
        for it in na_items
    ]
    na_results = await asyncio.gather(
        *(
            run_batch(batch[i : i + 8], "en")
            for batch in (na_casual, na_formal)
            for i in range(0, len(batch), 8)
        )
    )
    na_questions: dict[str, list[str]] = {}
    for r in na_results:
        for k, v in r.items():
            na_questions.setdefault(k, []).extend(v)
    for it in na_items:
        for q in na_questions.get(it["id"], [])[:4]:
            if re.search(r"\d", q):
                continue
            entries.append(
                {
                    "id": next_id("n"),
                    "category": "no_answer",
                    "question": q,
                    "expected_refusal": True,
                    "notes": f"absent topic: {it['id']}",
                }
            )

    # dedupe questions
    seen: set[tuple[str, str]] = set()
    unique = []
    for e in entries:
        key = (e["category"], e.get("role", ""), e["question"].casefold())
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    from collections import Counter

    counts = Counter(e["category"] for e in unique)
    header = (
        "# Corpus v2 golden set — generated by scripts/corpus_v2/make_golden.py from corpus/large/facts.yaml.\n"
        f"# {len(unique)} entries: "
        + ", ".join(f"{k}({v})" for k, v in sorted(counts.items()))
        + "\n"
        "# Run: uv run python -m eval.run_eval --collection <kranich id> --golden eval/golden_v2.yaml \\\n"
        "#        --results eval/results_v2.md --role leadership [--with-answers --judge --api-key <key>]\n"
    )
    args.out.write_text(
        header + yaml.safe_dump(unique, allow_unicode=True, sort_keys=False, width=110),
        encoding="utf-8",
    )
    print(f"wrote {args.out}: {len(unique)} entries {dict(counts)}")


if __name__ == "__main__":
    from app.db.base import dispose_engine

    async def _run() -> None:
        try:
            await main()
        finally:
            await dispose_engine()

    asyncio.run(_run())
