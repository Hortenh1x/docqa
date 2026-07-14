import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base
from app.db.models.tenant import Tenant


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    # first 8 characters of the secret part: lookup + safe display ("dqa_live_k7Jd93Lm…")
    prefix: Mapped[str] = mapped_column(index=True)
    # sha256 of the full key; keys are high-entropy, so bcrypt is unnecessary
    key_hash: Mapped[str]
    name: Mapped[str] = mapped_column(server_default=text("'default'"))
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    tenant: Mapped[Tenant] = relationship()
