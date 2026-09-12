"""Serialize brief admission/import transactions; never hold a lock during provider I/O."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import anyio
import structlog
from sqlalchemy import case, func, literal, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.context import BillingActor
from app.billing.errors import BudgetExceededError, BudgetUnavailableError
from app.config import get_settings
from app.db.models.spend import SpendAllocation, SpendReservation

log = structlog.get_logger("docqa.budget")
_ADMISSION_LOCK = 1_060_010_001  # serialization only, not a global monetary cap


@asynccontextmanager
async def _transaction() -> AsyncIterator[AsyncSession]:
    # Celery runs provider coroutines on successive asyncio.run loops. No asyncpg
    # connection may leak into another loop; each brief transaction owns its connection.
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"timeout": 5, "command_timeout": 5},
    )
    try:
        async with AsyncSession(engine) as db, db.begin():
            yield db
    finally:
        await engine.dispose()


def _day() -> date:
    return datetime.now(UTC).date()


def scopes(actor: BillingActor) -> list[str]:
    result = [f"ip:{actor.ip_digest}"]
    if actor.user_id is not None:
        result.append(f"user:{actor.user_id}")
    return result


async def _import_guest(db: AsyncSession, actor: BillingActor, day: date) -> None:
    if actor.user_id is None:
        return
    # Associations, not a copied debit: pending attempts settle for BOTH identities.
    # Repeated login is harmless; account usage on another IP remains in its scope.
    selection = select(
        SpendReservation.id, literal(f"user:{actor.user_id}"), SpendReservation.day
    ).where(
        SpendReservation.day == day,
        SpendReservation.ip_digest == actor.ip_digest,
        SpendReservation.payer_user_id.is_(None),
    )
    await db.execute(
        insert(SpendAllocation)
        .from_select(["reservation_id", "scope", "day"], selection)
        .on_conflict_do_nothing()
    )


async def _totals(
    db: AsyncSession, actor: BillingActor, day: date
) -> dict[str, tuple[Decimal, Decimal]]:
    keys = scopes(actor)
    rows = (
        await db.execute(
            select(
                SpendAllocation.scope,
                func.coalesce(func.sum(SpendReservation.actual_usd), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (SpendReservation.actual_usd.is_(None), SpendReservation.reserved_usd),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .join(SpendReservation, SpendReservation.id == SpendAllocation.reservation_id)
            .where(SpendAllocation.scope.in_(keys), SpendAllocation.day == day)
            .group_by(SpendAllocation.scope)
        )
    ).all()
    totals = {key: (Decimal(0), Decimal(0)) for key in keys}
    totals.update({key: (Decimal(spent), Decimal(reserved)) for key, spent, reserved in rows})
    return totals


async def summary(actor: BillingActor) -> dict[str, Any]:
    try:
        async with _transaction() as db:
            await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _ADMISSION_LOCK})
            day = _day()
            await _import_guest(db, actor, day)
            totals = await _totals(db, actor, day)
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        log.error("budget_database_unavailable")
        raise BudgetUnavailableError() from exc
    limit = get_settings().budget_daily_usd
    key, (spent, reserved) = max(totals.items(), key=lambda item: sum(item[1]))
    reset = datetime.combine(day + timedelta(days=1), time(), tzinfo=UTC)
    return {
        "limit_usd": str(limit),
        "spent_usd": str(spent),
        "reserved_usd": str(reserved),
        "remaining_usd": str(max(Decimal(0), limit - spent - reserved)),
        "reset_at": reset.isoformat(),
        "limited_by": "ip" if key.startswith("ip:") else "account",
    }


async def reserve(actor: BillingActor, amount: Decimal, operation: str, model: str) -> uuid.UUID:
    if not amount.is_finite() or amount < 0:
        raise BudgetUnavailableError("Invalid cost reservation.")
    reservation_id = uuid.uuid4()
    try:
        async with _transaction() as db:
            await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _ADMISSION_LOCK})
            day = _day()
            await _import_guest(db, actor, day)
            totals = await _totals(db, actor, day)
            limit = get_settings().budget_daily_usd
            if any(spent + pending + amount > limit for spent, pending in totals.values()):
                reset = datetime.combine(day + timedelta(days=1), time(), tzinfo=UTC)
                retry = max(1, int((reset - datetime.now(UTC)).total_seconds()))
                raise BudgetExceededError(
                    "Daily AI quota is exhausted or reserved by requests already running.",
                    headers={"Retry-After": str(retry)},
                    reset_at=reset.isoformat(),
                )
            db.add(
                SpendReservation(
                    id=reservation_id,
                    day=day,
                    ip_digest=actor.ip_digest,
                    payer_user_id=actor.user_id,
                    operation=operation,
                    model=model,
                    reserved_usd=amount,
                )
            )
            await db.flush()
            db.add_all(
                SpendAllocation(reservation_id=reservation_id, scope=key, day=day)
                for key in scopes(actor)
            )
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        log.error("budget_admission_unavailable")
        raise BudgetUnavailableError() from exc
    return reservation_id


async def settle(reservation_id: uuid.UUID, actual: Decimal | None) -> None:
    if actual is None:
        return  # Unknown usage retains its full reservation, including after a crash.
    if not actual.is_finite() or actual < 0:
        raise BudgetUnavailableError("Invalid provider cost.")
    # Cancellation must not free money or lose known usage. A DB failure leaves the
    # conservative reservation in place and blocks subsequent overspending.
    with anyio.CancelScope(shield=True):
        try:
            async with _transaction() as db:
                await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _ADMISSION_LOCK})
                row = await db.get(SpendReservation, reservation_id, with_for_update=True)
                if row is None:
                    raise BudgetUnavailableError("Cost reservation is missing.")
                if row.actual_usd is not None:
                    if row.actual_usd != actual:
                        raise BudgetUnavailableError("Provider cost was already finalized.")
                    return
                row.actual_usd = actual
                row.settled_at = datetime.now(UTC)
                overrun = actual > row.reserved_usd
            if overrun:
                log.error("provider_cost_exceeded_reservation", reservation_id=str(reservation_id))
                raise BudgetUnavailableError("Provider cost exceeded the configured estimate.")
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            log.error("budget_settlement_unavailable", reservation_id=str(reservation_id))
            raise BudgetUnavailableError() from exc
