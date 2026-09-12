"""Browser account endpoints. Mutations require an exact Origin and X-CSRF-Token."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.accounts import service
from app.accounts.errors import AccountUnavailableError
from app.accounts.limits import check_attempts
from app.accounts.mail import Mailer, get_mailer
from app.accounts.passwords import confirm_password
from app.accounts.sessions import (
    COOKIE_NAME,
    check_csrf,
    create_authenticated_session,
    create_session,
    load_session,
)
from app.api.deps import DbSession
from app.config import get_settings
from app.db.models import AccountSession

router = APIRouter(prefix="/v1/auth", tags=["accounts"])


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    email_verified: bool
    tenant_id: uuid.UUID


class SessionOut(BaseModel):
    user: UserOut | None
    csrf_token: str | None
    registration_available: bool
    google_available: bool = False


async def mutation_session(request: Request, db: DbSession) -> AccountSession:
    if not get_settings().accounts_enabled:
        raise AccountUnavailableError("Browser accounts are not enabled.")
    loaded = await load_session(request, db)
    session = loaded[0] if loaded else None
    check_csrf(request, session)
    assert session is not None
    return session


MutationSession = Annotated[AccountSession, Depends(mutation_session)]
Mail = Annotated[Mailer, Depends(get_mailer)]


class EmailPayload(BaseModel):
    email: EmailStr = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class Credentials(EmailPayload):
    password: str = Field(min_length=1, repr=False)


class RegistrationCredentials(Credentials):
    password_confirmation: str = Field(repr=False)


class TokenPayload(BaseModel):
    token: str = Field(min_length=32, repr=False)


class PasswordTokenPayload(TokenPayload):
    password: str = Field(min_length=1, repr=False)
    password_confirmation: str = Field(repr=False)


NEUTRAL_MESSAGE = {
    "message": "If the address is eligible, an email with the next step has been sent."
}


@router.post("/register", status_code=202)
async def register(
    payload: RegistrationCredentials,
    request: Request,
    session: MutationSession,
    db: DbSession,
    mail: Mail,
) -> dict[str, str]:
    await check_attempts(request, "register", payload.email)
    confirm_password(payload.password, payload.password_confirmation)
    await service.register(db, payload.email, payload.password, mail)
    return NEUTRAL_MESSAGE


@router.post("/login", response_model=SessionOut)
async def login(
    payload: Credentials,
    request: Request,
    response: Response,
    session: MutationSession,
    db: DbSession,
) -> SessionOut:
    await check_attempts(request, "login", payload.email)
    user = await service.authenticate(db, payload.email, payload.password)
    # Import existing guest attempts before rotating the browser session. If the
    # budget store fails, the client keeps its still-valid anonymous cookie.
    if get_settings().budget_enabled:
        from app.billing.context import BillingActor, client_digest
        from app.billing.service import summary

        await summary(BillingActor(client_digest(request), user.id))
    current = await create_authenticated_session(db, request, response, user, session)
    return SessionOut(
        user=UserOut.model_validate(user),
        csrf_token=current.csrf_token,
        registration_available=get_settings().registration_available,
        google_available=get_settings().google_available,
    )


@router.post("/verify")
async def verify(
    payload: PasswordTokenPayload,
    request: Request,
    response: Response,
    session: MutationSession,
    db: DbSession,
) -> dict[str, str]:
    await check_attempts(request, "verify")
    confirm_password(payload.password, payload.password_confirmation)
    user = await service.verify_email(db, payload.token, payload.password)
    if session.user_id == user.id:
        response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
    return {"message": "Email verified. Sign in with your chosen password."}


@router.post("/resend", status_code=202)
async def resend(
    payload: EmailPayload, request: Request, session: MutationSession, db: DbSession, mail: Mail
) -> dict[str, str]:
    await check_attempts(request, "resend", payload.email)
    await service.request_link(db, payload.email, "verify", mail)
    return NEUTRAL_MESSAGE


@router.post("/forgot-password", status_code=202)
async def forgot_password(
    payload: EmailPayload, request: Request, session: MutationSession, db: DbSession, mail: Mail
) -> dict[str, str]:
    await check_attempts(request, "forgot-password", payload.email)
    await service.request_link(db, payload.email, "reset", mail)
    return NEUTRAL_MESSAGE


@router.post("/reset")
async def reset(
    payload: PasswordTokenPayload,
    request: Request,
    session: MutationSession,
    db: DbSession,
) -> dict[str, str]:
    await check_attempts(request, "reset")
    confirm_password(payload.password, payload.password_confirmation)
    await service.reset_password(db, payload.token, payload.password)
    return {"message": "Password reset. Sign in with your new password."}


@router.get("/session", response_model=SessionOut)
async def session_status(request: Request, response: Response, db: DbSession) -> SessionOut:
    loaded = await load_session(request, db)
    if not get_settings().accounts_enabled:
        return SessionOut(user=None, csrf_token=None, registration_available=False)
    if loaded is None:
        await check_attempts(request, "session")
        session, user = await create_session(db, response), None
    else:
        session, user = loaded
    return SessionOut(
        user=UserOut.model_validate(user) if user else None,
        csrf_token=session.csrf_token,
        registration_available=get_settings().registration_available,
        google_available=get_settings().google_available,
    )


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, session: MutationSession) -> None:
    session.revoked_at = datetime.now(UTC)
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
