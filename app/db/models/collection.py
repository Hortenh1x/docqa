import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("tenant_id", "slug"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str]
    slug: Mapped[str]
    # e.g. 'bge-m3' or 'text-embedding-3-small@1024' — guards against mixing embedding models
    embedding_model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
