"""Safe, bounded inputs for resolving follow-up references.

Only user questions and currently authorized source metadata leave this module. Historical
answers, passage content, quote text and access labels are deliberately absent from the types.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.roles import Principal
from app.accounts.actor import Actor
from app.config import Settings
from app.conversations.scope import (
    conversation_resource_scope,
    require_conversation_identity,
)
from app.core.errors import (
    ConversationArchivedError,
    ConversationReadOnlyError,
    InvalidConversationParentError,
    NotFoundError,
)
from app.db.models import (
    Chunk,
    Collection,
    Conversation,
    Document,
    DocumentStatus,
    Query,
    QueryCitation,
)
from app.ingestion.chunking import TokenCounter


@dataclass(frozen=True)
class SafeTurn:
    query_id: uuid.UUID
    question: str

    def prompt_payload(self) -> dict[str, str]:
        return {"question": self.question}


@dataclass(frozen=True)
class SafeReference:
    document_id: uuid.UUID
    chunk_id: int
    filename: str
    section: str | None

    def prompt_payload(self) -> dict[str, str | int | None]:
        return {
            "document_id": str(self.document_id),
            "chunk_id": self.chunk_id,
            "filename": self.filename,
            "section": self.section,
        }


@dataclass(frozen=True)
class SafeContextWindow:
    turns: tuple[SafeTurn, ...]
    references: tuple[SafeReference, ...]
    reset: bool = False

    def prompt_payload(self) -> dict[str, Any]:
        return {
            "reset": self.reset,
            "previous_user_questions": [turn.prompt_payload() for turn in self.turns],
            "authorized_references": [ref.prompt_payload() for ref in self.references],
        }


@dataclass(frozen=True)
class ConversationContext:
    conversation_id: uuid.UUID
    parent_query_id: uuid.UUID | None
    source_generation: int
    access_fingerprint: str
    reset: bool
    turns: tuple[SafeTurn, ...]
    references: tuple[SafeReference, ...]

    @property
    def turns_used(self) -> int:
        return len(self.turns)

    def prompt_payload(self) -> dict[str, Any]:
        return SafeContextWindow(self.turns, self.references, self.reset).prompt_payload()


def access_fingerprint(principal: Principal) -> str:
    canonical = json.dumps(
        [principal.role, sorted(set(principal.labels))],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _token_count(window: SafeContextWindow, counter: TokenCounter) -> int:
    serialized = json.dumps(
        window.prompt_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return counter.count(serialized)


def fit_safe_context(
    turns: list[SafeTurn],
    references: list[SafeReference],
    *,
    token_budget: int,
    max_references: int,
) -> SafeContextWindow:
    """Keep the newest complete questions, then references in caller priority order."""

    counter = TokenCounter()
    selected_turns: list[SafeTurn] = []
    for turn in reversed(turns):
        candidate = [turn, *selected_turns]
        if _token_count(SafeContextWindow(tuple(candidate), ()), counter) <= token_budget:
            selected_turns = candidate
        else:
            break

    selected_references: list[SafeReference] = []
    seen: set[int] = set()
    for reference in references:
        if reference.chunk_id in seen or len(selected_references) >= max_references:
            continue
        reference_candidate = [*selected_references, reference]
        window = SafeContextWindow(tuple(selected_turns), tuple(reference_candidate))
        if _token_count(window, counter) > token_budget:
            continue
        seen.add(reference.chunk_id)
        selected_references = reference_candidate
    return SafeContextWindow(tuple(selected_turns), tuple(selected_references))


_CONTEXT_OUTCOMES = ("answered", "refused", "clarification")


async def _owned_parent(
    db: AsyncSession,
    actor: Actor,
    guest_id: uuid.UUID | None,
    parent_query_id: uuid.UUID,
    target: Conversation,
) -> Query | None:
    result = await db.scalar(
        select(Query)
        .join(Conversation, Query.conversation_id == Conversation.id)
        .join(Collection, Conversation.collection_id == Collection.id)
        .where(
            Query.id == parent_query_id,
            Query.conversation_id == target.id,
            Query.collection_id == target.collection_id,
            Query.tenant_id == target.tenant_id,
            Query.tenant_id == Conversation.tenant_id,
            Query.collection_id == Conversation.collection_id,
            conversation_resource_scope(actor, guest_id),
        )
    )
    return result


async def load_conversation_context(
    db: AsyncSession,
    request: Request,
    actor: Actor,
    collection_id: uuid.UUID,
    conversation_id: uuid.UUID,
    parent_query_id: uuid.UUID | None,
    principal: Principal,
    settings: Settings,
) -> ConversationContext:
    """Validate one conversation head and return only bounded, reauthorized metadata.

    The caller owns the short-lived session. This function finishes all reads before any
    provider work begins; the returned immutable value contains no ORM objects.
    """

    guest_id = require_conversation_identity(request, actor)
    conversation = await db.scalar(
        select(Conversation)
        .join(Collection, Conversation.collection_id == Collection.id)
        .where(
            Conversation.id == conversation_id,
            Conversation.collection_id == collection_id,
            Conversation.tenant_id == Collection.tenant_id,
            conversation_resource_scope(actor, guest_id),
        )
    )
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    if conversation.kind == "legacy":
        raise ConversationReadOnlyError("Previous questions cannot accept new queries.")
    if conversation.archived_at is not None:
        raise ConversationArchivedError("Unarchive the conversation before continuing it.")

    # Read the generation immediately before walking the chain. Under PostgreSQL READ
    # COMMITTED this statement sees source changes committed after the ownership lookup.
    source_generation = await db.scalar(
        select(Collection.source_generation).where(
            Collection.id == conversation.collection_id,
            Collection.tenant_id == conversation.tenant_id,
        )
    )
    if source_generation is None:
        raise NotFoundError("Collection not found.")
    fingerprint = access_fingerprint(principal)
    if parent_query_id is None:
        return ConversationContext(
            conversation_id=conversation.id,
            parent_query_id=None,
            source_generation=source_generation,
            access_fingerprint=fingerprint,
            reset=False,
            turns=(),
            references=(),
        )

    parent = await _owned_parent(db, actor, guest_id, parent_query_id, conversation)
    if parent is None:
        raise NotFoundError("Parent query not found.")
    if parent.outcome not in _CONTEXT_OUTCOMES:
        raise InvalidConversationParentError(
            "The parent must be a completed query in the same conversation."
        )

    newest_first = [parent]
    current = parent
    for _ in range(settings.conversation_context_max_turns - 1):
        if current.context_reset or current.parent_query_id is None:
            break
        ancestor = await db.scalar(
            select(Query).where(
                Query.id == current.parent_query_id,
                Query.conversation_id == conversation.id,
                Query.collection_id == conversation.collection_id,
                Query.tenant_id == conversation.tenant_id,
                Query.outcome.in_(_CONTEXT_OUTCOMES),
            )
        )
        if ancestor is None:
            break
        newest_first.append(ancestor)
        current = ancestor

    if any(
        query.source_generation != source_generation or query.access_fingerprint != fingerprint
        for query in newest_first
    ):
        return ConversationContext(
            conversation_id=conversation.id,
            parent_query_id=parent.id,
            source_generation=source_generation,
            access_fingerprint=fingerprint,
            reset=True,
            turns=(),
            references=(),
        )

    chronological = [SafeTurn(query.id, query.question) for query in reversed(newest_first)]
    turn_window = fit_safe_context(
        chronological,
        [],
        token_budget=settings.conversation_context_token_budget,
        max_references=settings.conversation_context_max_references,
    )
    if not turn_window.turns:
        return ConversationContext(
            conversation_id=conversation.id,
            parent_query_id=parent.id,
            source_generation=source_generation,
            access_fingerprint=fingerprint,
            reset=True,
            turns=(),
            references=(),
        )

    selected_ids = [turn.query_id for turn in turn_window.turns]
    citation_rows = (
        await db.execute(
            select(
                QueryCitation,
                Query.answer,
                Chunk.id,
                Document.id,
                Document.filename,
                Chunk.section_path,
            )
            .join(Query, Query.id == QueryCitation.query_id)
            .join(Chunk, Chunk.id == QueryCitation.chunk_id)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                QueryCitation.query_id.in_(selected_ids),
                Query.conversation_id == conversation.id,
                Query.collection_id == conversation.collection_id,
                Query.tenant_id == conversation.tenant_id,
                Document.collection_id == conversation.collection_id,
                Document.status == DocumentStatus.READY,
                Chunk.access_label.in_(principal.labels),
            )
        )
    ).all()
    recency = {query.id: index for index, query in enumerate(newest_first)}

    def citation_priority(row: Any) -> tuple[bool, int, int]:
        citation, answer, *_ = row
        cited = citation.quotes is not None or (bool(answer) and f"[{citation.rank}]" in answer)
        return (not cited, recency.get(citation.query_id, len(recency)), citation.rank)

    references = [
        SafeReference(
            document_id=document_id,
            chunk_id=chunk_id,
            filename=filename,
            section=section,
        )
        for _, _, chunk_id, document_id, filename, section in sorted(
            citation_rows, key=citation_priority
        )
    ]
    fitted = fit_safe_context(
        list(turn_window.turns),
        references,
        token_budget=settings.conversation_context_token_budget,
        max_references=settings.conversation_context_max_references,
    )
    return ConversationContext(
        conversation_id=conversation.id,
        parent_query_id=parent.id,
        source_generation=source_generation,
        access_fingerprint=fingerprint,
        reset=False,
        turns=fitted.turns,
        references=fitted.references,
    )
