"""Serialize short file-reference mutations per tenant across API and admin jobs.

Upload stores bytes while holding this lock, before committing its reference. Removal
commits DB deletion first, then takes the same lock to check references and unlink.
A crash may leave an orphan file, but cannot destroy a committed surviving reference.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import Tenant


async def lock_tenant_files(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    tenant = await db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
    if tenant is None:
        raise NotFoundError("Tenant not found.")
