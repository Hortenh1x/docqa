"""GET /v1/roles — the access roles a query may assert, and what each one can see.

The UI builds its role switcher from this list; nothing about roles is hard-coded on
the client. Roles come from settings (ACCESS_ROLES); descriptions are cosmetic.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import CurrentTenant
from app.config import get_settings
from app.core.rate_limit import rate_limit

router = APIRouter(prefix="/v1", tags=["access"], dependencies=[Depends(rate_limit("default"))])

_DESCRIPTIONS = {
    "employee": "Any employee — content open to all staff.",
    "manager": "People managers — adds manager-only guidance.",
    "hr": "People & Culture — adds HR procedures and case handling.",
    "finance": "Finance team — adds financial thresholds and approvals.",
    "leadership": "Leadership team — sees everything.",
}


class RoleOut(BaseModel):
    role: str
    labels: list[str]
    description: str
    default: bool


@router.get(
    "/roles",
    response_model=list[RoleOut],
    description=(
        "Access roles accepted by POST /v1/query (`role`), in privilege order, with the "
        "content labels each role can read. The default role applies when a query names none."
    ),
)
async def list_roles(tenant: CurrentTenant) -> list[RoleOut]:
    settings = get_settings()
    return [
        RoleOut(
            role=role,
            labels=list(labels),
            description=_DESCRIPTIONS.get(role, f"Sees: {', '.join(labels)}."),
            default=role == settings.access_default_role,
        )
        for role, labels in settings.access_roles.items()
    ]
