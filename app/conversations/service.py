import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import Request
from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.actor import Actor
from app.accounts.errors import InvalidSessionError
from app.conversations.scope import (
    conversation_resource_scope,
    require_conversation_identity,
)
from app.core.errors import (
    ConversationReadOnlyError,
    InvalidCursorError,
    NotFoundError,
)
from app.db.models import AccountSession, Collection, Conversation, Query


@dataclass(frozen=True)
class ConversationCursor:
    updated_at: datetime
    conversation_id: uuid.UUID


def encode_cursor(updated_at: datetime, conversation_id: uuid.UUID) -> str:
    payload = json.dumps([updated_at.isoformat(), str(conversation_id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> ConversationCursor:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError
        updated_at = datetime.fromisoformat(payload[0])
        if updated_at.tzinfo is None:
            raise ValueError
        return ConversationCursor(updated_at.astimezone(UTC), uuid.UUID(payload[1]))
    except (
        binascii.Error,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise InvalidCursorError("The conversation cursor is malformed.") from exc


async def fetch_conversation(
    db: AsyncSession,
    request: Request,
    actor: Actor,
    conversation_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Conversation:
    guest_id = require_conversation_identity(request, actor)
    statement = (
        select(Conversation)
        .join(Collection, Conversation.collection_id == Collection.id)
        .where(
            Conversation.id == conversation_id,
            conversation_resource_scope(actor, guest_id),
        )
    )
    if lock:
        statement = statement.with_for_update(of=Conversation)
    conversation = await db.scalar(statement)
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation


async def create_conversation(
    db: AsyncSession,
    request: Request,
    actor: Actor,
    collection: Collection,
    title: str,
) -> Conversation:
    guest_id = require_conversation_identity(request, actor)
    if actor.kind == "api_key" and (collection.is_public or actor.api_key_id is None):
        raise NotFoundError("Collection not found.")
    if guest_id is not None:
        # Serialize creation with sign-in/logout. If creation wins, sign-in's claim
        # sees the row; if rotation wins, this request cannot orphan a conversation
        # under the revoked anonymous session.
        current_guest = await db.scalar(
            select(AccountSession)
            .where(
                AccountSession.id == guest_id,
                AccountSession.user_id.is_(None),
                AccountSession.revoked_at.is_(None),
                AccountSession.expires_at > datetime.now(UTC),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current_guest is None:
            raise InvalidSessionError()
    conversation = Conversation(
        tenant_id=collection.tenant_id,
        collection_id=collection.id,
        title=title,
        owner_user_id=actor.user_id if actor.kind == "account" else None,
        owner_guest_session_id=guest_id,
        created_by_api_key_id=actor.api_key_id if actor.kind == "api_key" else None,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_conversations(
    db: AsyncSession,
    request: Request,
    actor: Actor,
    collection: Collection,
    archived: Literal["false", "true", "all"],
    limit: int,
    before: str | None,
) -> tuple[list[Conversation], bool, dict[uuid.UUID, Query]]:
    guest_id = require_conversation_identity(request, actor)
    if actor.kind == "api_key" and collection.is_public:
        raise NotFoundError("Collection not found.")
    conditions = [
        Conversation.collection_id == collection.id,
        Conversation.tenant_id == collection.tenant_id,
        conversation_resource_scope(actor, guest_id),
    ]
    if archived == "false":
        conditions.append(Conversation.archived_at.is_(None))
    elif archived == "true":
        conditions.append(Conversation.archived_at.is_not(None))
    if before:
        cursor = decode_cursor(before)
        conditions.append(
            tuple_(Conversation.updated_at, Conversation.id)
            < (cursor.updated_at, cursor.conversation_id)
        )
    rows = list(
        await db.scalars(
            select(Conversation)
            .join(Collection, Conversation.collection_id == Collection.id)
            .where(*conditions)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    previews: dict[uuid.UUID, Query] = {}
    if rows:
        ranked = (
            select(
                Query.id,
                Query.conversation_id,
                func.row_number()
                .over(
                    partition_by=Query.conversation_id,
                    order_by=(Query.created_at.desc(), Query.id.desc()),
                )
                .label("position"),
            )
            .where(
                Query.conversation_id.in_([row.id for row in rows]),
                Query.collection_id == collection.id,
                Query.tenant_id == collection.tenant_id,
            )
            .subquery()
        )
        preview_rows = await db.scalars(
            select(Query)
            .join(ranked, Query.id == ranked.c.id)
            .where(
                ranked.c.position == 1,
                Query.collection_id == collection.id,
                Query.tenant_id == collection.tenant_id,
            )
        )
        previews = {
            query.conversation_id: query
            for query in preview_rows
            if query.conversation_id is not None
        }
    return rows, has_more, previews


async def update_conversation(
    db: AsyncSession,
    request: Request,
    actor: Actor,
    conversation_id: uuid.UUID,
    *,
    title: str | None,
    archived: bool | None,
) -> Conversation:
    conversation = await fetch_conversation(db, request, actor, conversation_id, lock=True)
    if conversation.kind == "legacy" and (title is not None or archived is not True):
        raise ConversationReadOnlyError("Previous questions are read-only.")
    changed = False
    if title is not None and title != conversation.title:
        conversation.title = title
        changed = True
    if archived is not None:
        is_archived = conversation.archived_at is not None
        if archived != is_archived:
            conversation.archived_at = datetime.now(UTC) if archived else None
            changed = True
    if changed:
        conversation.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(conversation)
    return conversation


async def list_conversation_queries(
    db: AsyncSession,
    request: Request,
    actor: Actor,
    conversation_id: uuid.UUID,
    limit: int,
    before: uuid.UUID | None,
) -> tuple[list[Query], bool]:
    conversation = await fetch_conversation(db, request, actor, conversation_id)
    scope = [
        Query.conversation_id == conversation.id,
        Query.collection_id == conversation.collection_id,
        Query.tenant_id == conversation.tenant_id,
    ]
    if before is not None:
        anchor = (
            await db.execute(select(Query.created_at, Query.id).where(Query.id == before, *scope))
        ).first()
        if anchor is None:
            raise NotFoundError("Conversation query cursor not found.")
        scope.append(tuple_(Query.created_at, Query.id) < tuple_(anchor[0], anchor[1]))
    rows = list(
        await db.scalars(
            select(Query)
            .where(*scope)
            .order_by(Query.created_at.desc(), Query.id.desc())
            .limit(limit + 1)
        )
    )
    return rows[:limit], len(rows) > limit


async def claim_guest_conversations(
    db: AsyncSession, previous_session_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    previous = await db.scalar(
        select(AccountSession)
        .where(AccountSession.id == previous_session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if previous is None or previous.user_id is not None or previous.revoked_at is not None:
        return 0
    conversation_ids = list(
        (
            await db.execute(
                update(Conversation)
                .where(
                    Conversation.owner_guest_session_id == previous.id,
                    Conversation.owner_user_id.is_(None),
                    Conversation.created_by_api_key_id.is_(None),
                )
                .values(owner_user_id=user_id, owner_guest_session_id=None)
                .returning(Conversation.id)
            )
        ).scalars()
    )
    if conversation_ids:
        await db.execute(
            update(Query).where(Query.conversation_id.in_(conversation_ids)).values(user_id=user_id)
        )
    return len(conversation_ids)
