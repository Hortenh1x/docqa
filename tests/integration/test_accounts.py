"""Real-DB account lifecycle and browser isolation; delivery/providers stay local."""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def account_client(app_env, monkeypatch):
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("ACCOUNTS_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "https://ui.test")
    monkeypatch.setenv("AUTH_PUBLIC_URL", "https://ui.test")
    get_settings.cache_clear()
    application = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as client:
        yield client, application
    get_settings.cache_clear()


async def test_anonymous_session_cookie_and_csrf_contract(account_client):
    client, _ = account_client
    response = await client.get("/v1/auth/session")
    assert response.status_code == 200
    assert response.json()["user"] is None
    assert len(response.json()["csrf_token"]) >= 32
    assert response.json()["registration_available"] is False
    cookie = response.headers["set-cookie"]
    assert "__Host-docqa_session=" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Domain=" not in cookie
    assert response.headers["cache-control"] == "private, no-store"


async def test_auth_mutations_require_origin_and_csrf(account_client):
    client, _ = account_client
    session = (await client.get("/v1/auth/session")).json()
    for headers in [
        {},
        {"Origin": "https://evil.test", "X-CSRF-Token": session["csrf_token"]},
        {"Origin": "https://ui.test", "X-CSRF-Token": "wrong"},
    ]:
        response = await client.post("/v1/auth/logout", headers=headers, json={})
        assert response.status_code == 403
        assert response.json()["code"] == "csrf_failed"


PASSWORD = "fjord sunset velvet lantern 9276"


@pytest.fixture
def capture_mail(account_client, monkeypatch):
    from app.accounts.mail import get_mailer
    from app.config import get_settings

    class CaptureMail:
        def __init__(self):
            self.messages = []

        async def send(self, recipient, subject, body):
            self.messages.append((recipient, subject, body))

        def token(self):
            link = next(
                word for word in self.messages[-1][2].split() if word.startswith("https://")
            )
            return parse_qs(urlparse(link).fragment)["token"][0]

    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_FROM", "accounts@example.com")
    get_settings.cache_clear()
    mail = CaptureMail()
    _, application = account_client
    application.dependency_overrides[get_mailer] = lambda: mail
    return mail


async def csrf(client):
    response = await client.get("/v1/auth/session")
    assert response.status_code == 200, response.text
    return {"Origin": "https://ui.test", "X-CSRF-Token": response.json()["csrf_token"]}


async def register_login(client, mail, email="alice@example.com", verified=True):
    headers = await csrf(client)
    response = await client.post(
        "/v1/auth/register",
        headers=headers,
        json={"email": email, "password": PASSWORD, "password_confirmation": PASSWORD},
    )
    assert response.status_code == 202, response.text
    if verified:
        response = await client.post(
            "/v1/auth/verify",
            headers=headers,
            json={"token": mail.token(), "password": PASSWORD, "password_confirmation": PASSWORD},
        )
        assert response.status_code == 200, response.text
    response = await client.post(
        "/v1/auth/login", headers=headers, json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json(), {
        "Origin": "https://ui.test",
        "X-CSRF-Token": response.json()["csrf_token"],
    }


async def test_registration_verification_login_and_cookie_rotation(account_client, capture_mail):
    from sqlalchemy import select

    from app.db.base import get_sessionmaker
    from app.db.models import AccountSession, AccountToken, Tenant, User

    client, _ = account_client
    before_headers = await csrf(client)
    before_cookie = client.cookies.get("__Host-docqa_session")
    payload, headers = await register_login(client, capture_mail, verified=False)
    assert payload["user"]["email_verified"] is False
    assert client.cookies.get("__Host-docqa_session") != before_cookie
    assert headers != before_headers
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
        tenant = await db.get(Tenant, user.tenant_id)
        assert tenant.kind == "personal"
        sessions = (await db.scalars(select(AccountSession))).all()
        assert all(s.token_hash != client.cookies.get("__Host-docqa_session") for s in sessions)
        token = await db.scalar(select(AccountToken))
        assert token.token_hash != capture_mail.token()
    verified = await client.post(
        "/v1/auth/verify",
        headers=headers,
        json={
            "token": capture_mail.token(),
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert verified.status_code == 200
    # Even the caller's unverified login is revoked; verification does not log in.
    assert "Max-Age=0" in verified.headers.get("set-cookie", "")
    assert (await client.get("/v1/auth/session")).json()["user"] is None
    headers = await csrf(client)
    repeat = await client.post(
        "/v1/auth/verify",
        headers=headers,
        json={
            "token": capture_mail.token(),
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert repeat.status_code == 400
    login = await client.post(
        "/v1/auth/login", headers=headers, json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    assert (await client.get("/v1/auth/session")).json()["user"]["email_verified"] is True


async def test_no_delivery_configuration_is_explicitly_unavailable(account_client):
    client, _ = account_client
    headers = await csrf(client)
    response = await client.post(
        "/v1/auth/register",
        headers=headers,
        json={"email": "a@example.com", "password": PASSWORD, "password_confirmation": PASSWORD},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "account_service_unavailable"


async def test_registration_and_recovery_do_not_enumerate_accounts(account_client, capture_mail):
    client, _ = account_client
    _, headers = await register_login(client, capture_mail)
    responses = []
    for email in ("alice@example.com", "missing@example.com"):
        responses.append(
            await client.post(
                "/v1/auth/register",
                headers=headers,
                json={"email": email, "password": PASSWORD, "password_confirmation": PASSWORD},
            )
        )
    assert responses[0].status_code == responses[1].status_code == 202
    assert responses[0].json() == responses[1].json()
    responses = []
    for email in ("alice@example.com", "unknown@example.com"):
        responses.append(
            await client.post("/v1/auth/forgot-password", headers=headers, json={"email": email})
        )
    assert responses[0].status_code == responses[1].status_code == 202
    assert responses[0].json() == responses[1].json()


async def test_reset_is_single_use_and_revokes_existing_sessions(account_client, capture_mail):
    client, application = account_client
    _, headers = await register_login(client, capture_mail)
    old_cookie = client.cookies.get("__Host-docqa_session")
    response = await client.post(
        "/v1/auth/forgot-password", headers=headers, json={"email": "alice@example.com"}
    )
    assert response.status_code == 202
    reset_token = capture_mail.token()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as recovery:
        reset_headers = await csrf(recovery)
        response = await recovery.post(
            "/v1/auth/reset",
            headers=reset_headers,
            json={
                "token": reset_token,
                "password": "moss river quiet notebook 7535",
                "password_confirmation": "moss river quiet notebook 7535",
            },
        )
        assert response.status_code == 200, response.text
        assert (await client.get("/v1/auth/session")).status_code == 401
        repeat = await recovery.post(
            "/v1/auth/reset",
            headers=reset_headers,
            json={"token": reset_token, "password": PASSWORD, "password_confirmation": PASSWORD},
        )
        assert repeat.status_code == 400
        bad = await recovery.post(
            "/v1/auth/login",
            headers=reset_headers,
            json={"email": "alice@example.com", "password": PASSWORD},
        )
        assert bad.status_code == 401
        good = await recovery.post(
            "/v1/auth/login",
            headers=reset_headers,
            json={"email": "alice@example.com", "password": "moss river quiet notebook 7535"},
        )
        assert good.status_code == 200
        assert recovery.cookies.get("__Host-docqa_session") != old_cookie


async def test_invalid_expired_disabled_and_logged_out_sessions_never_fall_back(
    account_client, capture_mail, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import AccountSession

    client, _ = account_client
    _, headers = await register_login(client, capture_mail)
    original = client.cookies.get("__Host-docqa_session")
    assert (await client.post("/v1/auth/logout", headers=headers, json={})).status_code == 204
    client.cookies.set("__Host-docqa_session", original, domain="api.test", path="/")
    assert (await client.get("/v1/collections")).status_code == 401
    client.cookies.clear()
    await register_login(client, capture_mail, email="bob@example.com")
    async with get_sessionmaker()() as db:
        await db.execute(
            update(AccountSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()
    assert (await client.get("/v1/collections")).status_code == 401
    monkeypatch.setenv("ACCOUNTS_ENABLED", "false")
    get_settings.cache_clear()
    assert (await client.get("/v1/collections")).status_code == 401


async def test_password_validation_and_durable_attempt_limit(
    account_client, capture_mail, monkeypatch
):
    from app.config import get_settings

    client, _ = account_client
    headers = await csrf(client)
    for password in ("short", "aaaaaaaaaaaaaaaaa", "known breached long password"):
        response = await client.post(
            "/v1/auth/register",
            headers=headers,
            json={
                "email": "alice@example.com",
                "password": password,
                "password_confirmation": password,
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "weak_password"
    monkeypatch.setenv("AUTH_ATTEMPT_ACCOUNT_LIMIT", "2")
    get_settings.cache_clear()
    for expected in (401, 401, 429):
        response = await client.post(
            "/v1/auth/login",
            headers=headers,
            json={"email": "unknown@example.com", "password": PASSWORD},
        )
        assert response.status_code == expected


async def test_private_collections_and_full_document_isolation(
    account_client, capture_mail, make_tenant, monkeypatch
):
    import uuid

    from app.config import get_settings
    from app.core.security import generate_api_key
    from app.db.base import get_sessionmaker
    from app.db.models import ApiKey, Collection

    client, application = account_client
    public_tenant = await make_tenant()
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(public_tenant["id"]))
    monkeypatch.setenv("SUGGESTED_QUESTIONS_ENABLED", "false")
    get_settings.cache_clear()
    async with get_sessionmaker()() as db:
        published = Collection(
            tenant_id=public_tenant["id"],
            name="Public",
            slug="public",
            embedding_model=get_settings().embedding_model_id,
            is_public=True,
            read_only=True,
        )
        unpublished = Collection(
            tenant_id=public_tenant["id"],
            name="Hidden demo",
            slug="hidden",
            embedding_model=get_settings().embedding_model_id,
            read_only=True,
        )
        db.add_all([published, unpublished])
        await db.commit()
        public_id, hidden_id = str(published.id), str(unpublished.id)

    account, headers = await register_login(client, capture_mail)
    collections = await client.get("/v1/collections")
    assert collections.status_code == 200, collections.text
    private = next(c for c in collections.json() if c["owned"])
    assert private["is_public"] is False and private["writable"] is True
    assert {c["id"] for c in collections.json()} == {private["id"], public_id}
    collection_id = private["id"]
    missing_csrf = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("note.md", b"# Secret\n\nAlice secret.")},
    )
    assert missing_csrf.status_code == 403
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        headers=headers,
        files={
            "file": (
                "note.md",
                b"# Personal\n\nAccess: leadership only\n\nAlice private lanterns are purple.",
            )
        },
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["id"]
    assert (await client.get(f"/v1/documents/{document_id}/file")).status_code == 200
    query = await client.post(
        "/v1/query",
        headers=headers,
        json={
            "collection_id": collection_id,
            "question": "What color are Alice private lanterns?",
            "role": "employee",
            "stream": False,
        },
    )
    assert query.status_code == 200, query.text
    assert query.json()["access"]["role"] == "owner"

    async with get_sessionmaker()() as db:
        key, prefix, hashed = generate_api_key()
        db.add(
            ApiKey(
                tenant_id=uuid.UUID(account["user"]["tenant_id"]), prefix=prefix, key_hash=hashed
            )
        )
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as other:
        _, other_headers = await register_login(other, capture_mail, email="bob@example.com")
        for method, url, payload in [
            ("GET", f"/v1/collections/{collection_id}/documents", None),
            ("GET", f"/v1/collections/{collection_id}/ingest-status", None),
            ("GET", f"/v1/documents/{document_id}", None),
            ("GET", f"/v1/documents/{document_id}/file", None),
            ("DELETE", f"/v1/documents/{document_id}", None),
            (
                "POST",
                "/v1/query",
                {"collection_id": collection_id, "question": "secret", "stream": False},
            ),
        ]:
            response = await other.request(method, url, headers=other_headers, json=payload)
            assert response.status_code == 404, response.text
        foreign_upload = await other.post(
            f"/v1/collections/{collection_id}/documents",
            headers=other_headers,
            files={"file": ("b.md", b"# B\n\nother")},
        )
        assert foreign_upload.status_code == 404
        assert (await other.get(f"/v1/collections/{hidden_id}/documents")).status_code == 404
        other.cookies.clear()
        # Personal tenants cannot be authenticated by any service API key.
        assert (
            await other.get("/v1/collections", headers={"Authorization": f"Bearer {key}"})
        ).status_code == 401
        guest_collections = await other.get("/v1/collections", headers=public_tenant["headers"])
        assert [c["id"] for c in guest_collections.json()] == [public_id]
        assert (
            await other.get(f"/v1/documents/{document_id}", headers=public_tenant["headers"])
        ).status_code == 404
        guest_headers = await csrf(other)
        guest_upload = await other.post(
            f"/v1/collections/{public_id}/documents",
            headers={**public_tenant["headers"], **guest_headers},
            files={"file": ("b.md", b"# B\n\nother")},
        )
        assert guest_upload.status_code in (401, 403)
        assert (
            await other.post("/v1/collections", headers=guest_headers, json={"name": "hack"})
        ).status_code == 401
    deleted = await client.delete(f"/v1/documents/{document_id}", headers=headers)
    assert deleted.status_code == 204


async def test_unverified_account_cannot_upload(account_client, capture_mail):
    client, _ = account_client
    _, headers = await register_login(client, capture_mail, verified=False)
    response = await client.get("/v1/collections")
    assert response.status_code == 200
    collection_id = response.json()[0]["id"]
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        headers=headers,
        files={"file": ("secret.md", b"# Secret\n\nNobody sees this.")},
    )
    assert upload.status_code == 403
    assert upload.json()["code"] == "email_verification_required"


async def test_invalid_cookie_is_rejected_then_cleared_for_explicit_reauthentication(
    account_client,
):
    client, _ = account_client
    client.cookies.set("__Host-docqa_session", "x" * 43, domain="api.test", path="/")
    invalid = await client.get("/v1/auth/session")
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "invalid_session"
    assert "Max-Age=0" in invalid.headers.get("set-cookie", "")
    fresh = await client.get("/v1/auth/session")
    assert fresh.status_code == 200
    assert fresh.json()["user"] is None


async def test_recovery_delivery_outage_does_not_enumerate_accounts(account_client, capture_mail):
    from app.accounts.errors import AccountUnavailableError

    client, _ = account_client
    _, headers = await register_login(client, capture_mail)

    async def fail_delivery(*args):
        raise AccountUnavailableError("Email delivery is temporarily unavailable.")

    capture_mail.send = fail_delivery
    for email in ("alice@example.com", "unknown@example.com"):
        response = await client.post(
            "/v1/auth/forgot-password", headers=headers, json={"email": email}
        )
        assert response.status_code == 503


async def test_expired_verification_and_resend_invalidates_older_link(account_client, capture_mail):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.db.base import get_sessionmaker
    from app.db.models import AccountToken

    client, _ = account_client
    _, headers = await register_login(client, capture_mail, verified=False)
    old = capture_mail.token()
    response = await client.post(
        "/v1/auth/resend", headers=headers, json={"email": "alice@example.com"}
    )
    assert response.status_code == 202
    new = capture_mail.token()
    assert new != old
    assert (
        await client.post(
            "/v1/auth/verify",
            headers=headers,
            json={"token": old, "password": PASSWORD, "password_confirmation": PASSWORD},
        )
    ).status_code == 400
    async with get_sessionmaker()() as db:
        await db.execute(
            update(AccountToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()
    assert (
        await client.post(
            "/v1/auth/verify",
            headers=headers,
            json={"token": new, "password": PASSWORD, "password_confirmation": PASSWORD},
        )
    ).status_code == 400


@pytest.mark.parametrize("error_kind", ["database", "connection", "timeout"])
async def test_auth_attempt_store_outage_fails_closed(
    account_client, capture_mail, monkeypatch, error_kind
):
    from sqlalchemy.exc import OperationalError

    from app.accounts import limits

    client, _ = account_client
    headers = await csrf(client)

    errors = {
        "database": OperationalError("redacted", {}, Exception("offline")),
        "connection": OSError("offline"),
        "timeout": TimeoutError("offline"),
    }

    def fail_db(*args, **kwargs):
        raise errors[error_kind]

    monkeypatch.setattr(limits, "create_async_engine", fail_db)
    response = await client.post(
        "/v1/auth/register",
        headers=headers,
        json={"email": "new@example.com", "password": PASSWORD, "password_confirmation": PASSWORD},
    )
    assert response.status_code == 503
    assert capture_mail.messages == []


async def test_migration_defaults_and_constraint_names(app_env, make_tenant):
    from sqlalchemy import text

    from app.db.base import get_sessionmaker

    tenant = await make_tenant()
    async with get_sessionmaker()() as db:
        kind = await db.scalar(text("SELECT kind FROM tenants WHERE id=:id"), {"id": tenant["id"]})
        assert kind == "service"
        constraints = set(
            await db.scalars(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid IN "
                    "('tenants'::regclass, 'collections'::regclass, 'account_tokens'::regclass)"
                )
            )
        )
        assert "ck_tenants_kind" in constraints
        assert "ck_collections_public_read_only" in constraints
        assert "ck_account_tokens_kind" in constraints


@pytest.mark.parametrize("owner_action", ["register", "resend"])
async def test_email_owner_replaces_preregistered_credentials_and_revokes_all_links(
    account_client, capture_mail, owner_action
):
    attacker, application = account_client
    _, attacker_headers = await register_login(attacker, capture_mail, verified=False)
    old_verification = capture_mail.token()
    response = await attacker.post(
        "/v1/auth/forgot-password", headers=attacker_headers, json={"email": "alice@example.com"}
    )
    assert response.status_code == 202
    old_reset = capture_mail.token()
    owner_password = "meadow copper winter orchard 8327"
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as owner:
        owner_headers = await csrf(owner)
        payload = {"email": "alice@example.com"}
        if owner_action == "register":
            payload["password"] = owner_password
            payload["password_confirmation"] = owner_password
        response = await owner.post(f"/v1/auth/{owner_action}", headers=owner_headers, json=payload)
        assert response.status_code == 202
        proof = capture_mail.token()
        response = await owner.post(
            "/v1/auth/verify",
            headers=owner_headers,
            json={
                "token": proof,
                "password": owner_password,
                "password_confirmation": owner_password,
            },
        )
        assert response.status_code == 200
        assert (await attacker.get("/v1/auth/session")).status_code == 401
        attacker_headers = await csrf(attacker)
        bad_login = await attacker.post(
            "/v1/auth/login",
            headers=attacker_headers,
            json={"email": "alice@example.com", "password": PASSWORD},
        )
        assert bad_login.status_code == 401
        for endpoint, token in (
            ("verify", old_verification),
            ("verify", proof),
            ("reset", old_reset),
        ):
            response = await attacker.post(
                f"/v1/auth/{endpoint}",
                headers=attacker_headers,
                json={"token": token, "password": PASSWORD, "password_confirmation": PASSWORD},
            )
            assert response.status_code == 400
        owner_login = await owner.post(
            "/v1/auth/login",
            headers=owner_headers,
            json={"email": "alice@example.com", "password": owner_password},
        )
        assert owner_login.status_code == 200
        assert owner_login.json()["user"]["email_verified"] is True


@pytest.mark.parametrize("password", [None, "short", "known breached long password"])
async def test_verification_requires_a_safe_explicit_password(
    account_client, capture_mail, password
):
    client, _ = account_client
    headers = await csrf(client)
    response = await client.post(
        "/v1/auth/register",
        headers=headers,
        json={
            "email": "alice@example.com",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert response.status_code == 202
    token = capture_mail.token()
    payload = {"token": token}
    if password is not None:
        payload["password"] = password
        payload["password_confirmation"] = password
    response = await client.post("/v1/auth/verify", headers=headers, json=payload)
    assert response.status_code == 400
    # A rejected password does not consume the email proof.
    response = await client.post(
        "/v1/auth/verify",
        headers=headers,
        json={"token": token, "password": PASSWORD, "password_confirmation": PASSWORD},
    )
    assert response.status_code == 200


async def test_login_rechecks_credentials_cached_before_email_verification(
    account_client, capture_mail
):
    from sqlalchemy import select

    from app.accounts.errors import InvalidCredentialsError
    from app.accounts.service import authenticate
    from app.db.base import get_sessionmaker
    from app.db.models import User

    attacker, application = account_client
    await register_login(attacker, capture_mail, verified=False)
    token = capture_mail.token()
    async with get_sessionmaker()() as pending_request:
        # load_session() has already loaded this user before authenticate() takes
        # its row lock. Another request can complete email proof in that gap.
        cached_user = await pending_request.scalar(
            select(User).where(User.email == "alice@example.com")
        )
        assert cached_user.email_verified is False
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="https://api.test"
        ) as owner:
            owner_headers = await csrf(owner)
            response = await owner.post(
                "/v1/auth/verify",
                headers=owner_headers,
                json={
                    "token": token,
                    "password": "meadow copper winter orchard 8327",
                    "password_confirmation": "meadow copper winter orchard 8327",
                },
            )
            assert response.status_code == 200
        with pytest.raises(InvalidCredentialsError):
            await authenticate(pending_request, "alice@example.com", PASSWORD)


async def test_waiting_email_proof_is_rechecked_without_lock_order_deadlock(
    account_client, capture_mail
):
    import asyncio
    from datetime import UTC, datetime

    from sqlalchemy import select, text, update

    from app.accounts.errors import InvalidTokenError
    from app.accounts.sessions import token_hash
    from app.accounts.tokens import consume_token
    from app.db.base import get_sessionmaker
    from app.db.models import AccountToken, User

    client, _ = account_client
    await register_login(client, capture_mail, verified=False)
    proof = capture_mail.token()

    async def consume_waiting_proof():
        async with get_sessionmaker()() as consumer:
            await consumer.execute(text("SET LOCAL application_name = 'waiting-email-proof-test'"))
            with pytest.raises(InvalidTokenError):
                await consume_token(consumer, proof, "verify")

    async with get_sessionmaker()() as changer:
        user = await changer.scalar(
            select(User).where(User.email == "alice@example.com").with_for_update()
        )
        pending = asyncio.create_task(consume_waiting_proof())
        try:
            async with asyncio.timeout(5):
                while True:
                    async with get_sessionmaker()() as monitor:
                        blocked = await monitor.scalar(
                            text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE application_name='waiting-email-proof-test' "
                                "AND wait_event_type='Lock')"
                            )
                        )
                    if blocked:
                        break
                    await asyncio.sleep(0.01)
            # Proof consumption is waiting for User, and must not already hold a
            # token lock that would deadlock this credential change's invalidation.
            await asyncio.wait_for(
                changer.execute(
                    update(AccountToken)
                    .where(
                        AccountToken.user_id == user.id,
                        AccountToken.token_hash == token_hash(proof),
                    )
                    .values(used_at=datetime.now(UTC))
                ),
                timeout=3,
            )
            await changer.commit()
            await asyncio.wait_for(pending, timeout=3)
        finally:
            await changer.rollback()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_login_password_lock_allows_concurrent_billing_reservation(
    account_client, capture_mail
):
    import asyncio
    import uuid
    from decimal import Decimal

    from app.accounts.service import authenticate
    from app.billing.context import BillingActor
    from app.billing.service import reserve
    from app.db.base import get_sessionmaker

    client, _ = account_client
    await register_login(client, capture_mail)
    async with get_sessionmaker()() as login_request:
        user = await authenticate(login_request, "alice@example.com", PASSWORD)
        # Login next enters billing summary. A concurrent reservation may already
        # hold the budget admission lock, and its FK check must remain possible.
        reservation = await asyncio.wait_for(
            reserve(BillingActor("auth-lock-test", user.id), Decimal("0.01"), "lock-test", "stub"),
            timeout=2,
        )
        assert isinstance(reservation, uuid.UUID)


async def test_auth_attempt_counter_survives_exhausted_request_connection_pool(app_env):
    import asyncio
    from contextlib import AsyncExitStack

    from fastapi import Request
    from sqlalchemy import func, select

    from app.accounts.limits import check_attempts
    from app.db.base import get_engine
    from app.db.models import AuthAttempt

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/auth/login",
            "headers": [],
            "client": ("192.0.2.10", 1234),
        }
    )
    engine = get_engine()
    async with AsyncExitStack() as held_requests:
        connections = [await held_requests.enter_async_context(engine.connect()) for _ in range(15)]
        assert engine.pool.checkedout() == 15
        # Every normal request connection is occupied before auth checks its
        # durable counters; acquiring a second pooled connection would deadlock.
        await asyncio.wait_for(check_attempts(request, "login", "pool@example.com"), timeout=2)
        # Both IP and email attempts have committed independently of the held requests.
        assert await connections[0].scalar(select(func.sum(AuthAttempt.count))) == 2


async def test_registration_requires_matching_confirmation_before_creating_user(
    account_client, capture_mail
):
    from sqlalchemy import func, select

    from app.db.base import get_sessionmaker
    from app.db.models import User

    client, _ = account_client
    response = await client.post(
        "/v1/auth/register",
        headers=await csrf(client),
        json={
            "email": "typo@example.com",
            "password": PASSWORD,
            "password_confirmation": "different1",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "password_mismatch"
    assert capture_mail.messages == []
    async with get_sessionmaker()() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(User).where(User.email == "typo@example.com")
            )
            == 0
        )


@pytest.mark.parametrize("endpoint", ["verify", "reset"])
async def test_password_confirmation_mismatch_does_not_consume_proof(
    account_client, capture_mail, endpoint
):
    client, _ = account_client
    headers = await csrf(client)
    payload = {
        "email": "confirmation@example.com",
        "password": PASSWORD,
        "password_confirmation": PASSWORD,
    }
    assert (
        await client.post("/v1/auth/register", headers=headers, json=payload)
    ).status_code == 202
    if endpoint == "reset":
        assert (
            await client.post(
                "/v1/auth/forgot-password", headers=headers, json={"email": payload["email"]}
            )
        ).status_code == 202
    token = capture_mail.token()
    response = await client.post(
        "/v1/auth/" + endpoint,
        headers=headers,
        json={"token": token, "password": "aaaaaaa1", "password_confirmation": "aaaaaaa2"},
    )
    assert response.status_code == 400 and response.json()["code"] == "password_mismatch"
    response = await client.post(
        "/v1/auth/" + endpoint,
        headers=headers,
        json={"token": token, "password": "aaaaaaa1", "password_confirmation": "aaaaaaa1"},
    )
    assert response.status_code == 200, response.text
