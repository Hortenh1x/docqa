"""Durable worker attribution; reconstructed from owned DB rows, never Celery args alone."""

import uuid
from collections.abc import Coroutine
from typing import Any

from sqlalchemy import select

from app.billing.context import BillingActor, current_billing_actor, operator_billing
from app.billing.errors import BudgetUnavailableError
from app.config import get_settings
from app.db.models import Collection, Document, Tenant, User
from app.db.sync import sync_session


def collection_billing(
    collection_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    *,
    data_version: int | None = None,
    expected_revision: int | None = None,
) -> tuple[BillingActor | None, bool]:
    if not get_settings().budget_enabled:
        return None, False
    with sync_session() as db:
        row = db.execute(
            select(Collection, Tenant)
            .join(Tenant, Collection.tenant_id == Tenant.id)
            .where(Collection.id == collection_id, Tenant.is_active.is_(True))
        ).first()
        if row is None:
            raise BudgetUnavailableError("Background collection is unavailable.")
        collection, tenant = row
        if data_version is not None and collection.data_version != data_version:
            raise BudgetUnavailableError("Background corpus version changed.")
        if tenant.kind == "service":
            return None, True  # operator-seeded public corpus, never visitor uploads
        user = db.scalar(select(User).where(User.tenant_id == tenant.id, User.is_active.is_(True)))
        if user is None:
            raise BudgetUnavailableError("Document owner is unavailable.")
        if document_id is None:
            if expected_revision is None or collection.suggestion_revision != expected_revision:
                raise BudgetUnavailableError("Background trigger was superseded or is missing.")
            if (
                collection.suggestion_billing_user_id != user.id
                or not collection.suggestion_billing_ip_digest
            ):
                raise BudgetUnavailableError("Background operation has no saved billing identity.")
            return BillingActor(collection.suggestion_billing_ip_digest, user.id), False
        statement = select(Document).where(
            Document.collection_id == collection.id,
            Document.billing_user_id == user.id,
            Document.billing_ip_digest.isnot(None),
        )
        document = db.scalar(statement.where(Document.id == document_id))
        if document is None or not document.billing_ip_digest:
            raise BudgetUnavailableError("Background operation has no saved billing identity.")
        return BillingActor(document.billing_ip_digest, user.id), False


async def attributed[T](
    coro: Coroutine[Any, Any, T], actor: BillingActor | None, operator: bool
) -> T:
    # Set inside the coroutine: eager Celery executes it on another thread/loop.
    actor_token = current_billing_actor.set(actor)
    operator_token = operator_billing.set(operator)
    try:
        return await coro
    finally:
        current_billing_actor.reset(actor_token)
        operator_billing.reset(operator_token)
