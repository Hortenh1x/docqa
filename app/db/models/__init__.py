"""All ORM models. Import side effect: registers every table on Base.metadata (Alembic)."""

from app.db.models.api_key import ApiKey
from app.db.models.base import Base
from app.db.models.chunk import Chunk
from app.db.models.collection import Collection
from app.db.models.document import Document, DocumentStatus
from app.db.models.tenant import Tenant

__all__ = ["ApiKey", "Base", "Chunk", "Collection", "Document", "DocumentStatus", "Tenant"]
