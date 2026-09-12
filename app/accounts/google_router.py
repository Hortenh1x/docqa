"""Server-only Google OIDC flow. Browser redirects carry only allowlisted outcome codes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from app.accounts import google_accounts, google_state
from app.accounts.errors import AccountUnavailableError
from app.accounts.google_provider import GoogleProvider, GoogleProviderError, get_google_provider
from app.accounts.google_state import GoogleAuthError, GoogleErrorCode
from app.accounts.limits import check_attempts
from app.accounts.router import MutationSession
from app.api.deps import DbSession
from app.config import get_settings
from app.core.errors import DomainError

router = APIRouter(prefix="/v1/auth/google", tags=["accounts"])
Provider = Annotated[GoogleProvider, Depends(get_google_provider)]


class StartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["login", "link"] = "login"


class StartOut(BaseModel):
    authorization_url: str


@router.post("/start", response_model=StartOut)
async def start(
    payload: StartPayload,
    request: Request,
    response: Response,
    session: MutationSession,
    db: DbSession,
) -> StartOut:
    if not get_settings().google_available:
        raise AccountUnavailableError("Google sign-in is not configured.")
    await check_attempts(request, "google-start")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return StartOut(
        authorization_url=await google_state.begin(db, request, session, payload.intent)
    )


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(
        get_settings().auth_public_url.rstrip("/") + path,
        status_code=303,
        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/callback", response_model=None)
async def callback(request: Request, db: DbSession, provider: Provider) -> RedirectResponse:
    reason: GoogleErrorCode = "failed"
    if not get_settings().google_available:
        return _redirect("/account?google_error=unavailable")
    try:
        state = await google_state.consume(db, request, request.query_params.get("state", ""))
        code = request.query_params.get("code", "")
        if request.query_params.get("error") or not 1 <= len(code) <= 4096:
            raise GoogleAuthError()
        identity = await provider.exchange(code, state.verifier, state.nonce, get_settings())
        response = _redirect("/account?google=linked" if state.link_user_id else "/")
        await google_accounts.complete(db, request, response, state, identity)
        return response
    except GoogleAuthError as exc:
        reason = exc.reason
    except (GoogleProviderError, DomainError, SQLAlchemyError, OSError, TimeoutError):
        # Never expose token response bodies, provider errors, account records or cookies.
        pass
    await db.rollback()
    return _redirect(f"/account?google_error={reason}")
