import uuid
from typing import cast

from fastapi import Request
from sqlalchemy import and_, false, true
from sqlalchemy.sql.elements import ColumnElement

from app.accounts.actor import Actor, collection_scope
from app.core.errors import GuestSessionRequiredError
from app.db.models import Collection, Conversation


def guest_session_id(request: Request, actor: Actor) -> uuid.UUID | None:
    if actor.kind != "guest" or actor.api_key_id is not None:
        return None
    session = getattr(request.state, "account_session", None)
    if session is None or session.user_id is not None:
        return None
    return cast(uuid.UUID, session.id)


def require_conversation_identity(request: Request, actor: Actor) -> uuid.UUID | None:
    if actor.kind == "guest":
        session_id = guest_session_id(request, actor)
        if session_id is None:
            raise GuestSessionRequiredError(
                "Open a browser session before creating or reading guest conversations."
            )
        return session_id
    if actor.kind == "api_key" and actor.api_key_id is None:
        raise GuestSessionRequiredError("Conversation identity is unavailable.")
    return None


def conversation_owner_scope(
    actor: Actor, owner_guest_session_id: uuid.UUID | None
) -> ColumnElement[bool]:
    if actor.kind == "account" and actor.user_id is not None:
        return Conversation.owner_user_id == actor.user_id
    if actor.kind == "guest" and owner_guest_session_id is not None:
        return Conversation.owner_guest_session_id == owner_guest_session_id
    if actor.kind == "api_key":
        return Conversation.tenant_id == actor.tenant_id
    return false()


def conversation_resource_scope(
    actor: Actor, owner_guest_session_id: uuid.UUID | None
) -> ColumnElement[bool]:
    return and_(
        Conversation.collection_id == Collection.id,
        Conversation.tenant_id == Collection.tenant_id,
        collection_scope(actor),
        Collection.is_public.is_(False) if actor.kind == "api_key" else true(),
        conversation_owner_scope(actor, owner_guest_session_id),
    )
