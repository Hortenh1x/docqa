"""Explicit billing identity; propagated to request streams and durable ingestion jobs."""

import hashlib
import hmac
import ipaddress
import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.billing.errors import BudgetUnavailableError
from app.config import get_settings


@dataclass(frozen=True)
class BillingActor:
    ip_digest: str
    user_id: uuid.UUID | None = None


current_billing_actor: ContextVar[BillingActor | None] = ContextVar("billing_actor", default=None)
operator_billing: ContextVar[bool] = ContextVar("operator_billing", default=False)
current_account_id: ContextVar[uuid.UUID | None] = ContextVar("query_account_id", default=None)


def client_digest(request: Request) -> str:
    settings = get_settings()
    address = request.client.host if request.client else "127.0.0.1"
    if settings.rate_limit_trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            address = forwarded.split(",")[0].strip()
    try:
        ip = ipaddress.ip_address(address)
        # IPv6 privacy addresses must not yield a new quota for every host part.
        address = (
            str(ipaddress.ip_network(f"{ip}/64", strict=False)) if ip.version == 6 else str(ip)
        )
    except ValueError:
        # ASGI TestClient uses a name; production peers/forwarded addresses must be IPs.
        if address != "testclient":
            raise BudgetUnavailableError("Cannot determine a valid client address.") from None
    secret = settings.budget_ip_secret
    if not secret:
        raise BudgetUnavailableError("Client quota identity is not configured.")
    return hmac.new(secret.encode(), address.encode(), hashlib.sha256).hexdigest()


def bind_request_actor(request: Request) -> None:
    actor = getattr(request.state, "actor", None)
    current_account_id.set(actor.user_id if actor is not None else None)
    if not get_settings().budget_enabled:
        return
    if actor is not None and actor.kind == "api_key":
        # Private server integrations are not browser visitors. Public keys resolve guest.
        current_billing_actor.set(None)
        operator_billing.set(True)
        return
    operator_billing.set(False)
    user_id = actor.user_id if actor is not None else None
    current_billing_actor.set(BillingActor(ip_digest=client_digest(request), user_id=user_id))


class BillingContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = current_billing_actor.set(None)
        operator_token = operator_billing.set(False)
        account_token = current_account_id.set(None)
        try:
            await self.app(scope, receive, send)
        finally:
            current_billing_actor.reset(token)
            operator_billing.reset(operator_token)
            current_account_id.reset(account_token)
