"""Suggested questions for a collection.

When a collection's ingestion settles, the answering LLM drafts candidate questions
from a sample of the corpus; candidates are ranked by their best vector-cosine score
against the collection's own chunks and the top ``suggested_questions_count`` land on
the collection row as ``[{"question", "min_role"}]``.

Design points:
- More candidates than kept (count + 2): retrieval scoring keeps the most grounded,
  so a hallucinated candidate ranks last and falls off instead of reaching the UI.
- The prompt pins the output language to the excerpts' language — a German corpus
  gets German questions.
- The LLM call is retried once on an empty/garbled completion (DeepSeek sporadically
  burns the whole budget on hidden reasoning — see CLAUDE.md).
- Access levels: the sample includes one restricted excerpt per label present, every
  candidate is scored under every role, and ``min_role`` is the least-privileged role
  whose retrieval passes the refusal gate — the UI shows a lock on questions the
  current role cannot answer. When the collection has restricted content, at least one
  kept question is a locked one (the demo path). Questions never quote values: a
  candidate containing a digit or a currency sign is dropped, so a question drafted
  from a restricted excerpt cannot leak the figure it asks about.
"""

import json
import re
import uuid
from collections.abc import Callable, Sequence
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Chunk, Document, DocumentStatus
from app.embeddings import get_embedding_provider
from app.generation.llm import TextDelta, get_llm_provider
from app.ingestion.access import LABEL_ALL
from app.ingestion.chunking import TokenCounter

SAMPLE_TOKEN_CAP = 3200
SAMPLE_MAX_DOCS = 12
MAX_QUESTION_CHARS = 200
EXTRA_CANDIDATES = 2
# a role "can answer" a question when its best score is within this margin of the best
# score any role reaches — the refusal threshold alone is too lenient a test (it is tuned
# to pass ~all answerable questions, so an open chunk on a nearby topic passes it too)
MIN_ROLE_MARGIN = 0.03

_LEAKY_RE = re.compile(r"\d|[€$£]")

SUGGESTIONS_SYSTEM = """You write suggested questions for a document Q&A corpus.
Rules:
1. Output ONLY a JSON array of question strings. No prose, no code fences.
2. Every question must be answerable strictly from the excerpts you are given.
3. Write in the dominant language of the excerpts.
4. Keep each question under 90 characters; make them concrete and diverse —
   different documents and topics, no near-duplicates.
5. Never quote figures, amounts, dates, thresholds or names in a question — ask
   about them instead ("What is the card limit?", not "Is the card limit 1500?").
6. Each question is about ONE excerpt and asks for something that excerpt actually
   states — a rule, a deadline, an owner, a procedure. No hypothetical situations,
   no combining two excerpts, nothing the excerpt merely alludes to.
7. Excerpts marked "(Access: …)" are restricted to that group; include one question
   about such an excerpt when there is one."""


class SuggestedQuestion(TypedDict):
    question: str
    # least-privileged role whose retrieval can answer the question (see app/access)
    min_role: str


def build_suggestions_prompt(excerpts: list[str], n_candidates: int) -> str:
    joined = "\n\n".join(excerpts)
    return (
        f"Corpus excerpts:\n\n{joined}\n\nWrite {n_candidates} candidate questions as a JSON array."
    )


def parse_questions(raw: str) -> list[str]:
    """A JSON array of strings out of an LLM completion; fences/prose around it tolerated."""
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    questions: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        question = " ".join(item.split())
        if not question or len(question) > MAX_QUESTION_CHARS:
            continue
        key = question.casefold()
        if key in seen:
            continue
        seen.add(key)
        questions.append(question)
    return questions


def drop_leaky(questions: Sequence[str]) -> list[str]:
    """No digits, no currency: a question must never carry the value it asks about."""
    return [q for q in questions if not _LEAKY_RE.search(q)]


def sample_excerpts(session: Session, collection_id: uuid.UUID) -> list[str]:
    """First chunk of each ready document (heading-dense, language-representative), plus
    one chunk per restricted label so the LLM can draft a locked question."""
    counter = TokenCounter()
    excerpts: list[str] = []
    total = 0

    def add(excerpt: str, *, force: bool = False) -> bool:
        nonlocal total
        tokens = counter.count(excerpt)
        if excerpts and not force and total + tokens > SAMPLE_TOKEN_CAP:
            return False
        excerpts.append(excerpt)
        total += tokens
        return True

    ready = (
        select(Chunk, Document.filename)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.collection_id == collection_id,
            Document.status == DocumentStatus.READY,
        )
    )
    # restricted excerpts first: they are the point of the access demo and must not be
    # squeezed out by the token cap
    labels = session.execute(
        select(Chunk.access_label)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.collection_id == collection_id,
            Document.status == DocumentStatus.READY,
            Chunk.access_label != LABEL_ALL,
        )
        .distinct()
    ).scalars()
    for label in sorted(labels):
        row = session.execute(
            ready.where(Chunk.access_label == label).order_by(Chunk.token_count.desc()).limit(1)
        ).first()
        if row is not None:
            chunk, filename = row
            add(f"### {filename} (Access: {label})\n{chunk.content}", force=True)

    rows = session.execute(
        ready.where(Chunk.chunk_index == 0).order_by(Document.filename).limit(SAMPLE_MAX_DOCS)
    ).all()
    for chunk, filename in rows:
        if not add(f"### {filename}\n{chunk.content}"):
            break
    return excerpts


async def draft_candidates(
    settings: Settings, excerpts: list[str]
) -> tuple[list[str], list[list[float]]]:
    """LLM candidates + their embeddings. Empty when the model returns garbage twice."""
    n_candidates = settings.suggested_questions_count + EXTRA_CANDIDATES
    user = build_suggestions_prompt(excerpts, n_candidates)
    llm = get_llm_provider(settings)
    questions: list[str] = []
    for _ in range(2):
        parts: list[str] = []
        async for event in llm.stream(SUGGESTIONS_SYSTEM, user):
            if isinstance(event, TextDelta):
                parts.append(event.text)
        questions = drop_leaky(parse_questions("".join(parts)))
        if len(questions) >= settings.suggested_questions_count:
            break
    if not questions:
        return [], []
    embeddings = await get_embedding_provider(settings).embed(questions)
    return questions, embeddings


def choose_min_role(
    scores: dict[str, float], roles_in_order: Sequence[str], threshold: float, default: str
) -> str:
    """The least-privileged role that grounds the question (almost) as well as any role
    does and passes the gate; the default role when none does (the question is then
    merely weakly grounded, not locked)."""
    best = max(scores.values(), default=0.0)
    for role in roles_in_order:
        score = scores.get(role, 0.0)
        if score >= threshold and score >= best - MIN_ROLE_MARGIN:
            return role
    return default


def select_final(
    ranked: Sequence[tuple[str, float, str]],
    keep: int,
    default_role: str,
    has_restricted: bool,
) -> list[SuggestedQuestion]:
    """Top ``keep`` by score, with two guarantees when the candidates allow: at least one
    locked question when the collection has restricted content (the demo path), and at
    least one open question (a visitor with the default role must have something to
    click). A missing kind replaces the lowest-ranked kept candidate."""
    top = list(ranked[:keep])
    rest = list(ranked[keep:])

    def ensure(wanted: Callable[[str], bool], protect: int | None) -> int | None:
        if not top or any(wanted(role) for _, _, role in top):
            return None
        candidate = next((c for c in rest if wanted(c[2])), None)
        if candidate is None:
            return None
        index = len(top) - 1
        if index == protect and index > 0:
            index -= 1
        rest.remove(candidate)
        rest.append(top[index])
        top[index] = candidate
        return index

    swapped = ensure(lambda role: role != default_role, None) if has_restricted else None
    ensure(lambda role: role == default_role, swapped)
    return [{"question": q, "min_role": role} for q, _, role in top]


def rank_questions(
    session: Session,
    collection_id: uuid.UUID,
    questions: list[str],
    embeddings: list[list[float]],
    keep: int,
    settings: Settings,
) -> list[SuggestedQuestion]:
    """Keep the questions retrieval grounds best — their own future gate score — and tag
    each with the least-privileged role that can answer it."""
    roles = list(settings.access_roles)
    ranked: list[tuple[str, float, str]] = []
    for question, embedding in zip(questions, embeddings, strict=True):
        scores = {
            role: _best_score(session, collection_id, embedding, labels)
            for role, labels in settings.access_roles.items()
        }
        min_role = choose_min_role(
            scores, roles, settings.refusal_threshold, settings.access_default_role
        )
        ranked.append((question, max(scores.values(), default=0.0), min_role))
    ranked.sort(key=lambda item: item[1], reverse=True)
    has_restricted = _has_restricted_chunks(session, collection_id, settings)
    return select_final(ranked, keep, settings.access_default_role, has_restricted)


def _has_restricted_chunks(session: Session, collection_id: uuid.UUID, settings: Settings) -> bool:
    row = session.execute(
        select(Chunk.id)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.collection_id == collection_id,
            Document.status == DocumentStatus.READY,
            Chunk.access_label != LABEL_ALL,
        )
        .limit(1)
    ).first()
    return row is not None


def _best_score(
    session: Session, collection_id: uuid.UUID, embedding: list[float], labels: Sequence[str]
) -> float:
    distance = Chunk.embedding.cosine_distance(embedding)
    score = session.execute(
        select((1 - distance).label("score"))
        .select_from(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.collection_id == collection_id,
            Document.status == DocumentStatus.READY,
            Chunk.access_label.in_(list(labels)),
        )
        .order_by(distance)
        .limit(1)
    ).scalar()
    return float(score) if score is not None else 0.0
