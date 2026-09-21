"""Named conversation lifecycle and transcript endpoints."""

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Depends, Request
from fastapi import Query as QueryParam
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.deps import CurrentCollection, CurrentTenant, DbSession
from app.api.v1.history import HistoryPage, build_history_page
from app.conversations.service import (
    create_conversation,
    encode_cursor,
    list_conversation_queries,
    list_conversations,
    update_conversation,
)
from app.core.rate_limit import rate_limit
from app.db.models import Conversation, Query

router = APIRouter(
    prefix="/v1",
    tags=["conversations"],
    dependencies=[Depends(rate_limit("default"))],
)


def _clean_title(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Title cannot be blank.")
    return cleaned


class ConversationCreate(BaseModel):
    title: str = Field(default="New chat", max_length=120)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return _clean_title(value)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    archived: bool | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return _clean_title(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if self.title is None and self.archived is None:
            raise ValueError("Provide title or archived.")
        return self


class ConversationPreview(BaseModel):
    query_id: uuid.UUID
    question: str
    outcome: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID
    title: str
    archived: bool
    legacy: bool
    created_at: datetime
    updated_at: datetime
    preview: ConversationPreview | None


class ConversationPage(BaseModel):
    conversations: list[ConversationOut]
    has_more: bool
    next_cursor: str | None


def _conversation_out(conversation: Conversation, preview: Query | None = None) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        collection_id=conversation.collection_id,
        title=conversation.title,
        archived=conversation.archived_at is not None,
        legacy=conversation.kind == "legacy",
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        preview=(
            ConversationPreview(
                query_id=preview.id,
                question=preview.question,
                outcome=preview.outcome or "legacy_unknown",
                created_at=preview.created_at,
            )
            if preview is not None
            else None
        ),
    )


@router.post(
    "/collections/{collection_id}/conversations",
    status_code=201,
    response_model=ConversationOut,
)
async def create(
    payload: ConversationCreate,
    collection: CurrentCollection,
    db: DbSession,
    request: Request,
) -> ConversationOut:
    conversation = await create_conversation(
        db, request, request.state.actor, collection, payload.title
    )
    return _conversation_out(conversation)


@router.get(
    "/collections/{collection_id}/conversations",
    response_model=ConversationPage,
)
async def list_for_collection(
    collection: CurrentCollection,
    db: DbSession,
    request: Request,
    archived: Literal["false", "true", "all"] = "false",
    limit: Annotated[int, QueryParam(ge=1, le=100)] = 20,
    before: Annotated[str | None, QueryParam()] = None,
) -> ConversationPage:
    rows, has_more, previews = await list_conversations(
        db, request, request.state.actor, collection, archived, limit, before
    )
    return ConversationPage(
        conversations=[_conversation_out(row, previews.get(row.id)) for row in rows],
        has_more=has_more,
        next_cursor=(encode_cursor(rows[-1].updated_at, rows[-1].id) if has_more else None),
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def patch(
    conversation_id: uuid.UUID,
    payload: ConversationPatch,
    tenant: CurrentTenant,
    db: DbSession,
    request: Request,
) -> ConversationOut:
    del tenant
    conversation = await update_conversation(
        db,
        request,
        request.state.actor,
        conversation_id,
        title=payload.title,
        archived=payload.archived,
    )
    return _conversation_out(conversation)


class ConversationHistoryPage(HistoryPage):
    next_cursor: uuid.UUID | None


@router.get(
    "/conversations/{conversation_id}/queries",
    response_model=ConversationHistoryPage,
)
async def transcript(
    conversation_id: uuid.UUID,
    tenant: CurrentTenant,
    db: DbSession,
    request: Request,
    limit: Annotated[int, QueryParam(ge=1, le=100)] = 30,
    before: Annotated[uuid.UUID | None, QueryParam()] = None,
) -> ConversationHistoryPage:
    del tenant
    rows, has_more = await list_conversation_queries(
        db, request, request.state.actor, conversation_id, limit, before
    )
    page = await build_history_page(db, rows, has_more)
    return ConversationHistoryPage(
        queries=page.queries,
        has_more=has_more,
        next_cursor=rows[-1].id if has_more else None,
    )
