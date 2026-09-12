"""Google account/session boundaries against real PostgreSQL, with signed local OIDC."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select, update

from tests.unit.test_google_provider import claims, jwk

COOKIE = "__Host-docqa_session"


@pytest.fixture
async def google_browser(app_env, monkeypatch):
    from app.config import get_settings
    from app.main import create_app

    for name, value in {
        "ACCOUNTS_ENABLED": "true",
        "BUDGET_ENABLED": "false",
        "AUTH_ALLOWED_ORIGINS": "https://ui.test",
        "AUTH_PUBLIC_URL": "https://ui.test",
        "GOOGLE_CLIENT_ID": "test-client",
        "GOOGLE_CLIENT_SECRET": "server-secret",
        "GOOGLE_REDIRECT_URI": "https://api.test/v1/auth/google/callback",
        "SMTP_HOST": "",
        "SMTP_FROM": "",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    application = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="https://api.test"
    ) as client:
        yield SimpleNamespace(client=client, application=application)
    get_settings.cache_clear()


async def start(browser, intent="login"):
    session = await browser.client.get("/v1/auth/session")
    assert session.status_code == 200, session.text
    response = await browser.client.post(
        "/v1/auth/google/start",
        json={"intent": intent},
        headers={"Origin": "https://ui.test", "X-CSRF-Token": session.json()["csrf_token"]},
    )
    assert response.status_code == 200, response.text
    return parse_qs(urlparse(response.json()["authorization_url"]).query)


async def finish(browser, params, **query):
    return await browser.client.get(
        "/v1/auth/google/callback", params={"state": params["state"][0], "code": "code", **query}
    )


async def test_google_start_is_available_and_uses_minimal_scopes(google_browser):
    from app.accounts.sessions import token_hash
    from app.db.base import get_sessionmaker
    from app.db.models import GoogleAuthState

    params = await start(google_browser)
    assert params["scope"] == ["openid email"]
    assert params["code_challenge_method"] == ["S256"]
    assert "access_type" not in params and "client_secret" not in params
    async with get_sessionmaker()() as db:
        state = await db.get(GoogleAuthState, token_hash(params["state"][0]))
        assert state is not None
        assert state.nonce == params["nonce"][0]
        assert 500 < (state.expires_at - datetime.now(UTC)).total_seconds() <= 600
        assert state.used_at is None and len(state.code_verifier) >= 43


async def test_start_requires_exact_origin_and_csrf(google_browser):
    client = google_browser.client
    session = (await client.get("/v1/auth/session")).json()
    for headers in ({}, {"Origin": "https://evil.test", "X-CSRF-Token": session["csrf_token"]}):
        response = await client.post("/v1/auth/google/start", headers=headers, json={})
        assert response.status_code == 403


async def test_disabled_google_does_not_start(google_browser, monkeypatch):
    from app.config import get_settings

    client = google_browser.client
    session = (await client.get("/v1/auth/session")).json()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    get_settings.cache_clear()
    response = await client.post(
        "/v1/auth/google/start",
        json={},
        headers={
            "Origin": "https://ui.test",
            "X-CSRF-Token": session["csrf_token"],
        },
    )
    assert response.status_code == 503


async def configure_provider(
    browser, params, *, email="alice@example.com", subject="stable-subject", status=200, hook=None
):
    from app.accounts.google_provider import GoogleProvider, get_google_provider
    from app.accounts.sessions import token_hash
    from app.db.base import get_sessionmaker
    from app.db.models import GoogleAuthState

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    requests = []

    async def handle(request):
        requests.append(request)
        if request.url.path == "/token":
            # The authorization state is committed before contacting the provider.
            async with get_sessionmaker()() as db:
                state = await db.get(GoogleAuthState, token_hash(params["state"][0]))
                assert state.used_at is not None
            if hook:
                await hook()
            token = jwt.encode(
                claims(nonce=params["nonce"][0], email=email, sub=subject),
                key,
                algorithm="RS256",
                headers={"kid": "key-1"},
            )
            return httpx.Response(status, json={"id_token": token})
        return httpx.Response(200, json={"keys": [jwk(key)]})

    browser.application.dependency_overrides[get_google_provider] = lambda: GoogleProvider(
        httpx.MockTransport(handle)
    )
    return requests


async def create_account(email="alice@example.com", verified=True):
    from app.accounts.passwords import hash_password
    from app.db.base import get_sessionmaker
    from app.db.models import Tenant, User

    async with get_sessionmaker()() as db:
        tenant = Tenant(name="Existing personal", kind="personal")
        db.add(tenant)
        await db.flush()
        user = User(
            tenant_id=tenant.id,
            email=email,
            email_verified=verified,
            password_hash=await hash_password("password1"),
        )
        db.add(user)
        await db.commit()
        return user


async def email_login(browser, email="alice@example.com"):
    response = (await browser.client.get("/v1/auth/session")).json()
    login = await browser.client.post(
        "/v1/auth/login",
        json={"email": email, "password": "password1"},
        headers={"Origin": "https://ui.test", "X-CSRF-Token": response["csrf_token"]},
    )
    assert login.status_code == 200, login.text


async def test_new_google_user_has_verified_private_tenant_and_rotated_cookie(google_browser):
    from app.db.base import get_sessionmaker
    from app.db.models import Collection, GoogleIdentity, Tenant, User

    params = await start(google_browser)
    old = google_browser.client.cookies.get(COOKIE)
    await configure_provider(google_browser, params)
    response = await finish(google_browser, params)
    assert response.status_code == 303 and response.headers["location"] == "https://ui.test/"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert google_browser.client.cookies.get(COOKIE) != old
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User))
        assert user.email_verified and user.email == "alice@example.com"
        assert user.password_hash.startswith("$argon2id$")
        assert (await db.get(Tenant, user.tenant_id)).kind == "personal"
        assert (await db.scalar(select(Collection))).name == "My documents"
        assert (await db.scalar(select(GoogleIdentity))).user_id == user.id


async def test_existing_email_never_automatically_merges(google_browser):
    from app.db.base import get_sessionmaker
    from app.db.models import GoogleIdentity, User

    existing = await create_account()
    params = await start(google_browser)
    old = google_browser.client.cookies.get(COOKIE)
    await configure_provider(google_browser, params)
    response = await finish(google_browser, params)
    assert response.headers["location"] == "https://ui.test/account?google_error=email_exists"
    assert google_browser.client.cookies.get(COOKIE) == old
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 1
        assert await db.scalar(select(GoogleIdentity)) is None
        assert (await db.get(User, existing.id)).tenant_id == existing.tenant_id


async def test_explicit_link_and_returning_subject_preserve_original_account(google_browser):
    existing = await create_account()
    await email_login(google_browser)
    params = await start(google_browser, "link")
    await configure_provider(google_browser, params)
    linked = await finish(google_browser, params)
    assert linked.headers["location"] == "https://ui.test/account?google=linked"
    google_browser.client.cookies.clear()
    params = await start(google_browser)
    await configure_provider(google_browser, params, email="changed@example.com")
    assert (await finish(google_browser, params)).headers["location"] == "https://ui.test/"
    current = (await google_browser.client.get("/v1/auth/session")).json()["user"]
    assert current["id"] == str(existing.id)
    assert current["email"] == existing.email and current["tenant_id"] == str(existing.tenant_id)


@pytest.mark.parametrize("fault", ["wrong_browser", "expired", "revoked", "replay", "provider"])
async def test_state_and_provider_failures_preserve_previous_cookie(google_browser, fault):
    from app.accounts.sessions import token_hash
    from app.db.base import get_sessionmaker
    from app.db.models import AccountSession, GoogleAuthState

    params = await start(google_browser)
    requests = await configure_provider(
        google_browser, params, status=500 if fault == "provider" else 200
    )
    if fault == "wrong_browser":
        google_browser.client.cookies.clear()
        await google_browser.client.get("/v1/auth/session")
    elif fault in {"expired", "revoked"}:
        async with get_sessionmaker()() as db:
            state = await db.get(GoogleAuthState, token_hash(params["state"][0]))
            if fault == "expired":
                state.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                await db.execute(
                    update(AccountSession)
                    .where(AccountSession.id == state.session_id)
                    .values(revoked_at=datetime.now(UTC))
                )
            await db.commit()
    elif fault == "replay":
        assert (await finish(google_browser, params)).headers["location"] == "https://ui.test/"
        requests.clear()
    old = google_browser.client.cookies.get(COOKIE)
    response = await finish(google_browser, params)
    assert response.headers["location"] == "https://ui.test/account?google_error=failed"
    assert "set-cookie" not in response.headers
    assert google_browser.client.cookies.get(COOKIE) == old
    if fault != "provider":
        assert not requests


async def test_revocation_during_token_exchange_cannot_authenticate(google_browser):
    from app.db.base import get_sessionmaker
    from app.db.models import AccountSession, User

    params = await start(google_browser)

    async def revoke():
        async with get_sessionmaker()() as db:
            await db.execute(update(AccountSession).values(revoked_at=datetime.now(UTC)))
            await db.commit()

    await configure_provider(google_browser, params, hook=revoke)
    response = await finish(google_browser, params)
    assert response.headers["location"] == "https://ui.test/account?google_error=failed"
    assert "set-cookie" not in response.headers
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(User)) is None


async def test_google_login_imports_guest_spend_and_pending_settlement(google_browser, monkeypatch):
    from starlette.requests import Request

    from app.billing.context import BillingActor, client_digest
    from app.billing.service import reserve, settle, summary
    from app.config import get_settings

    monkeypatch.setenv("BUDGET_ENABLED", "true")
    monkeypatch.setenv("BUDGET_IP_SECRET", "test-only-secret-value-at-least-32-characters")
    get_settings.cache_clear()
    guest = BillingActor(
        client_digest(Request({"type": "http", "client": ("127.0.0.1", 123), "headers": []}))
    )
    reservation = await reserve(guest, Decimal("0.20"), "fixture", "fixture")
    params = await start(google_browser)
    await configure_provider(google_browser, params)
    response = await asyncio.wait_for(finish(google_browser, params), timeout=10)
    assert response.headers["location"] == "https://ui.test/"
    user = (await google_browser.client.get("/v1/auth/session")).json()["user"]
    import uuid

    actor = BillingActor(guest.ip_digest, uuid.UUID(user["id"]))
    assert Decimal((await summary(actor))["remaining_usd"]) == Decimal("0.30")
    await settle(reservation, Decimal("0.15"))
    assert Decimal((await summary(actor))["remaining_usd"]) == Decimal("0.35")
    assert Decimal((await summary(actor))["remaining_usd"]) == Decimal("0.35")


@pytest.mark.parametrize("verified", [False, True])
async def test_link_requires_verified_signed_in_account(google_browser, verified):
    client = google_browser.client
    if not verified:
        await create_account(verified=False)
        await email_login(google_browser)
    session = (await client.get("/v1/auth/session")).json()
    response = await client.post(
        "/v1/auth/google/start",
        json={"intent": "link"},
        headers={
            "Origin": "https://ui.test",
            "X-CSRF-Token": session["csrf_token"],
        },
    )
    assert response.status_code == 400


@pytest.mark.parametrize("collision", ["email", "subject", "account_identity"])
async def test_explicit_link_rejects_conflicts(google_browser, collision):
    from app.accounts.google_provider import ISSUER
    from app.db.base import get_sessionmaker
    from app.db.models import GoogleIdentity

    user = await create_account()
    if collision == "subject":
        other = await create_account("other@example.com")
        async with get_sessionmaker()() as db:
            db.add(GoogleIdentity(issuer=ISSUER, subject="stable-subject", user_id=other.id))
            await db.commit()
    elif collision == "account_identity":
        async with get_sessionmaker()() as db:
            db.add(GoogleIdentity(issuer=ISSUER, subject="another-subject", user_id=user.id))
            await db.commit()
    await email_login(google_browser)
    params = await start(google_browser, "link")
    await configure_provider(
        google_browser, params, email="other@example.com" if collision == "email" else user.email
    )
    old = google_browser.client.cookies.get(COOKIE)
    response = await finish(google_browser, params)
    assert response.headers["location"] == "https://ui.test/account?google_error=link_failed"
    assert google_browser.client.cookies.get(COOKIE) == old
    async with get_sessionmaker()() as db:
        assert not await db.scalar(
            select(GoogleIdentity).where(
                GoogleIdentity.user_id == user.id, GoogleIdentity.subject == "stable-subject"
            )
        )


async def test_provider_failure_consumes_state_even_when_browser_retries(google_browser):
    params = await start(google_browser)
    requests = await configure_provider(google_browser, params, status=500)
    assert (
        (await finish(google_browser, params)).headers["location"].endswith("google_error=failed")
    )
    assert len(requests) == 1
    assert (
        (await finish(google_browser, params)).headers["location"].endswith("google_error=failed")
    )
    assert len(requests) == 1


async def test_quota_failure_preserves_cookie_and_does_not_create_authenticated_session(
    google_browser, monkeypatch
):
    from app.billing import service
    from app.billing.errors import BudgetUnavailableError
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import AccountSession

    monkeypatch.setenv("BUDGET_ENABLED", "true")
    monkeypatch.setenv("BUDGET_IP_SECRET", "test-only-secret-value-at-least-32-characters")
    get_settings.cache_clear()

    async def unavailable(actor):
        raise BudgetUnavailableError()

    monkeypatch.setattr(service, "summary", unavailable)
    params = await start(google_browser)
    old = google_browser.client.cookies.get(COOKIE)
    await configure_provider(google_browser, params)
    response = await finish(google_browser, params)
    assert response.headers["location"].endswith("google_error=failed")
    assert "set-cookie" not in response.headers
    assert google_browser.client.cookies.get(COOKIE) == old
    async with get_sessionmaker()() as db:
        assert not await db.scalar(
            select(AccountSession).where(AccountSession.user_id.is_not(None))
        )


async def test_concurrent_new_google_logins_create_one_account(google_browser):
    from app.accounts.google_provider import ISSUER, GoogleIdentityClaims, get_google_provider
    from app.db.base import get_sessionmaker
    from app.db.models import Collection, GoogleIdentity, Tenant, User

    # Transport/signature validation is covered separately; force overlapping valid exchanges here.
    barrier = asyncio.Barrier(2)

    class ConcurrentProvider:
        async def exchange(self, *args):
            await barrier.wait()
            return GoogleIdentityClaims(ISSUER, "concurrent-subject", "alice@example.com")

    google_browser.application.dependency_overrides[get_google_provider] = ConcurrentProvider
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=google_browser.application), base_url="https://api.test"
    ) as second:
        other = SimpleNamespace(client=second, application=google_browser.application)
        first_params, second_params = await start(google_browser), await start(other)
        responses = await asyncio.wait_for(
            asyncio.gather(finish(google_browser, first_params), finish(other, second_params)),
            timeout=10,
        )
    assert all(response.headers["location"] == "https://ui.test/" for response in responses)
    async with get_sessionmaker()() as db:
        for model in (GoogleIdentity, User, Tenant, Collection):
            assert await db.scalar(select(func.count()).select_from(model)) == 1


async def test_concurrent_state_replay_contacts_provider_once(google_browser):
    from app.accounts.google_provider import ISSUER, GoogleIdentityClaims, get_google_provider

    calls = []

    class LocalProvider:
        async def exchange(self, *args):
            calls.append(True)
            await asyncio.sleep(0.05)
            return GoogleIdentityClaims(ISSUER, "subject", "alice@example.com")

    google_browser.application.dependency_overrides[get_google_provider] = LocalProvider
    params = await start(google_browser)
    responses = await asyncio.gather(finish(google_browser, params), finish(google_browser, params))
    assert sorted(response.headers["location"] for response in responses) == [
        "https://ui.test/",
        "https://ui.test/account?google_error=failed",
    ]
    assert calls == [True]


async def test_revoke_while_budget_import_waits_cannot_rotate_session(google_browser, monkeypatch):
    from app.billing import service
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import AccountSession

    monkeypatch.setenv("BUDGET_ENABLED", "true")
    monkeypatch.setenv("BUDGET_IP_SECRET", "test-only-secret-value-at-least-32-characters")
    get_settings.cache_clear()

    async def revoke(actor):
        async with get_sessionmaker()() as db:
            await db.execute(update(AccountSession).values(revoked_at=datetime.now(UTC)))
            await db.commit()
        return {}

    monkeypatch.setattr(service, "summary", revoke)
    params = await start(google_browser)
    await configure_provider(google_browser, params)
    response = await finish(google_browser, params)
    assert response.headers["location"].endswith("google_error=failed")
    assert "set-cookie" not in response.headers


async def test_deactivated_account_cannot_use_linked_google_identity(google_browser):
    from app.accounts.google_provider import ISSUER
    from app.db.base import get_sessionmaker
    from app.db.models import GoogleIdentity, User

    user = await create_account()
    async with get_sessionmaker()() as db:
        db.add(GoogleIdentity(issuer=ISSUER, subject="stable-subject", user_id=user.id))
        await db.execute(update(User).where(User.id == user.id).values(is_active=False))
        await db.commit()
    params = await start(google_browser)
    await configure_provider(google_browser, params)
    response = await finish(google_browser, params)
    assert response.headers["location"].endswith("google_error=failed")
    assert "set-cookie" not in response.headers
