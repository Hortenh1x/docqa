"""Caller identity and SQL collection scopes. A demo key never establishes ownership."""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import and_, false, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.config import get_settings
from app.db.models import Collection, Tenant


@dataclass(frozen=True)
class Actor:
    kind: Literal["account", "guest", "api_key"]
    user_id: uuid.UUID | None
    tenant_id: uuid.UUID


def collection_scope(actor: Actor) -> ColumnElement[bool]:
    settings = get_settings()
    if actor.kind == "api_key":
        return Collection.tenant_id == actor.tenant_id
    public = (
        and_(
            Collection.is_public.is_(True),
            Collection.read_only.is_(True),
            Collection.tenant_id == settings.public_tenant_id,
            Collection.tenant_id.in_(
                select(Tenant.id).where(Tenant.kind == "service", Tenant.is_active.is_(True))
            ),
        )
        if settings.public_tenant_id is not None
        else false()
    )
    if actor.kind == "guest":
        return public
    return or_(Collection.tenant_id == actor.tenant_id, public)
