"""All ORM models. Import side effect: registers every table on Base.metadata (Alembic)."""

from app.db.models.account import AccountSession, AccountToken, AuthAttempt, User
from app.db.models.api_key import ApiKey
from app.db.models.base import Base
from app.db.models.chunk import Chunk
from app.db.models.collection import Collection
from app.db.models.document import Document, DocumentStatus
from app.db.models.google import GoogleAuthState, GoogleIdentity
from app.db.models.query import Query, QueryCitation
from app.db.models.spend import SpendAllocation, SpendReservation
from app.db.models.tenant import Tenant

__all__ = [
    "GoogleAuthState",
    "GoogleIdentity",
    "SpendAllocation",
    "SpendReservation",
    "AccountSession",
    "AccountToken",
    "AuthAttempt",
    "User",
    "ApiKey",
    "Base",
    "Chunk",
    "Collection",
    "Document",
    "DocumentStatus",
    "Query",
    "QueryCitation",
    "Tenant",
]
