"""Storage capacity for the authenticated account's own original documents."""

from fastapi import APIRouter, Depends, Request

from app.accounts.errors import AuthenticationError
from app.api.deps import CurrentTenant, DbSession
from app.core.rate_limit import rate_limit
from app.storage.usage import StorageUsage, storage_usage

router = APIRouter(prefix="/v1", tags=["usage"], dependencies=[Depends(rate_limit("default"))])


@router.get("/storage")
async def get_storage_usage(tenant: CurrentTenant, db: DbSession, request: Request) -> StorageUsage:
    if request.state.actor.kind != "account":
        raise AuthenticationError("Sign in to view your document storage.")
    return await storage_usage(db, tenant.id)
