import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint("kind IN ('service', 'personal')", name="kind"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(server_default=text("'service'"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
