"""One provider attempt, many accounting scopes; login links existing guest attempts."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SpendReservation(Base):
    __tablename__ = "spend_reservations"
    __table_args__ = (
        CheckConstraint("reserved_usd >= 0", name="reserved_nonnegative"),
        CheckConstraint("actual_usd IS NULL OR actual_usd >= 0", name="actual_nonnegative"),
        Index("ix_spend_reservations_guest", "day", "ip_digest", "payer_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    day: Mapped[date]
    ip_digest: Mapped[str]
    payer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    operation: Mapped[str]
    model: Mapped[str]
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    settled_at: Mapped[datetime | None]


class SpendAllocation(Base):
    __tablename__ = "spend_allocations"
    __table_args__ = (Index("ix_spend_allocations_scope_day", "scope", "day"),)

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spend_reservations.id", ondelete="RESTRICT"), primary_key=True
    )
    scope: Mapped[str] = mapped_column(primary_key=True)
    day: Mapped[date]
