"""Real concurrent quota admission and login continuity; no real paid providers."""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.billing.context import BillingActor
from app.billing.errors import BudgetExceededError, BudgetUnavailableError
from app.billing.service import reserve, settle, summary


@pytest.fixture
def budget_config(app_env, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("BUDGET_ENABLED", "true")
    monkeypatch.setenv("BUDGET_IP_SECRET", "test-only-billing-secret-value-32-chars")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def account(budget_config):
    from app.db.base import get_sessionmaker
    from app.db.models import Tenant, User

    async with get_sessionmaker()() as db:
        tenant = Tenant(name="Private billing fixture", kind="personal")
        db.add(tenant)
        await db.flush()
        user = User(tenant_id=tenant.id, email="quota@example.com", password_hash="unused")
        db.add(user)
        await db.commit()
        return user.id


@pytest.fixture
async def budget_browser(budget_config, account, make_tenant, monkeypatch):
    import httpx
    from starlette.requests import Request

    from app.accounts.passwords import hash_password
    from app.billing.context import client_digest
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import User
    from app.main import create_app

    public = await make_tenant()
    monkeypatch.setenv("ACCOUNTS_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_TENANT_ID", str(public["id"]))
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "https://ui.test")
    monkeypatch.setenv("AUTH_PUBLIC_URL", "https://ui.test")
    get_settings.cache_clear()
    async with get_sessionmaker()() as db:
        user = await db.get(User, account)
        user.password_hash = await hash_password("correct horse sunset lentils 9373")
        await db.commit()
    peer = ("203.0.113.10", 4567)
    digest = client_digest(Request({"type": "http", "client": peer, "headers": []}))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(), client=peer),
        base_url="https://api.test",
    ) as client:
        yield client, BillingActor(digest), public


async def test_http_guest_login_logout_preserves_budget(budget_browser):
    from app.billing.context import current_billing_actor, operator_billing

    client, guest, _ = budget_browser
    initial = await client.get("/v1/budget")
    assert initial.status_code == 200, initial.text
    assert Decimal(initial.json()["remaining_usd"]) == Decimal("0.50")
    ticket = await reserve(guest, Decimal("0.20"), "fixture", "fixture")
    await settle(ticket, Decimal("0.20"))
    for _ in range(2):
        session = (await client.get("/v1/auth/session")).json()
        response = await client.post(
            "/v1/auth/login",
            headers={"Origin": "https://ui.test", "X-CSRF-Token": session["csrf_token"]},
            json={"email": "quota@example.com", "password": "correct horse sunset lentils 9373"},
        )
        assert response.status_code == 200, response.text
        state = await client.get("/v1/budget")
        assert state.status_code == 200, state.text
        assert Decimal(state.json()["remaining_usd"]) == Decimal("0.30")
        logout = await client.post(
            "/v1/auth/logout",
            headers={"Origin": "https://ui.test", "X-CSRF-Token": response.json()["csrf_token"]},
            json={},
        )
        assert logout.status_code == 204
        assert Decimal((await client.get("/v1/budget")).json()["remaining_usd"]) == Decimal("0.30")
    assert current_billing_actor.get() is None
    assert operator_billing.get() is False


async def test_public_key_cannot_escape_ip_budget_and_operator_scope_does_not_leak(
    budget_browser, make_tenant
):
    client, guest, public = budget_browser
    operator = await make_tenant()
    ticket = await reserve(guest, Decimal("0.50"), "fixture", "fixture")
    await settle(ticket, Decimal("0.50"))
    integration = await client.get("/v1/budget", headers=operator["headers"])
    assert integration.json() == {"enabled": False, "reason": "operator_integration"}
    for headers in ({}, public["headers"]):
        visitor = await client.get("/v1/budget", headers=headers)
        assert visitor.status_code == 200
        assert visitor.json()["enabled"] is True
        assert Decimal(visitor.json()["remaining_usd"]) == 0


async def test_budget_public_key_is_metered_even_when_accounts_are_disabled(
    budget_browser, monkeypatch
):
    from app.config import get_settings

    client, _, public = budget_browser
    monkeypatch.setenv("ACCOUNTS_ENABLED", "false")
    get_settings.cache_clear()
    result = await client.get("/v1/budget", headers=public["headers"])
    assert result.status_code == 200
    assert result.json()["enabled"] is True


async def test_guest_idempotency_is_separate_between_ips(budget_browser, monkeypatch):
    import uuid

    from app.api.v1 import query as query_module
    from app.config import get_settings
    from app.db.base import get_sessionmaker
    from app.db.models import Collection
    from app.generation.service import DoneEvent, MetaEvent

    client, _, public = budget_browser
    monkeypatch.setenv("RATE_LIMIT_TRUST_FORWARDED_FOR", "true")
    get_settings.cache_clear()
    async with get_sessionmaker()() as db:
        row = Collection(
            tenant_id=public["id"],
            name="Public",
            slug="public",
            is_public=True,
            read_only=True,
            embedding_model=get_settings().embedding_model_id,
        )
        db.add(row)
        await db.commit()
        cid = str(row.id)

    async def pipeline(*args):
        yield MetaEvent(uuid.uuid4(), {})
        yield DoneEvent("Public fixture", False, None, 1, 0, 0, Decimal(0), 1, "stub")

    monkeypatch.setattr(query_module, "run_query", pipeline)
    ids = []
    for address in ("203.0.113.1", "203.0.113.2", "203.0.113.1"):
        response = await client.post(
            "/v1/query",
            headers={"X-Forwarded-For": address, "Idempotency-Key": "same-key"},
            json={"collection_id": cid, "question": "Public fixture?", "stream": False},
        )
        assert response.status_code == 200, response.text
        ids.append(response.json()["query_id"])
    assert ids[0] != ids[1]
    assert ids[0] == ids[2]


async def test_quota_error_preserves_retry_and_reset_in_json_and_sse(budget_browser, monkeypatch):
    import uuid

    from app.access.roles import resolve_principal
    from app.api.v1.query import _collect_json, _sse_stream
    from app.billing.errors import BudgetExceededError
    from app.config import get_settings
    from app.generation import service

    async def denied(*args, **kwargs):
        raise BudgetExceededError("No budget", headers={"Retry-After": "123"}, reset_at="later")

    monkeypatch.setattr(service, "retrieve", denied)
    settings = get_settings()

    def events():
        return service.run_query(
            uuid.uuid4(), uuid.uuid4(), "Question", settings, resolve_principal(settings, None), 0
        )

    with pytest.raises(BudgetExceededError) as error:
        await _collect_json(events())
    assert error.value.headers == {"Retry-After": "123"}
    assert error.value.extra["reset_at"] == "later"
    wire = "".join([frame async for frame in _sse_stream(events())])
    assert '"reset_at": "later"' in wire
    assert '"retry_after_s": 123' in wire


async def test_guest_twenty_cents_survives_login_and_repeated_login(account):
    guest = BillingActor("ip-a")
    ticket = await reserve(guest, Decimal("0.20"), "query", "fixture")
    await settle(ticket, Decimal("0.20"))
    owner = BillingActor("ip-a", account)
    for _ in range(3):
        result = await summary(owner)
        assert Decimal(result["remaining_usd"]) == Decimal("0.30")
    assert Decimal((await summary(BillingActor("ip-b", account)))["remaining_usd"]) == Decimal(
        "0.30"
    )


async def test_inflight_guest_reservation_is_shared_and_settles_after_login(account):
    ticket = await reserve(BillingActor("ip-a"), Decimal("0.40"), "query", "fixture")
    owner = BillingActor("ip-a", account)
    assert Decimal((await summary(owner))["remaining_usd"]) == Decimal("0.10")
    await settle(ticket, Decimal("0.20"))
    assert Decimal((await summary(owner))["remaining_usd"]) == Decimal("0.30")
    assert Decimal((await summary(BillingActor("ip-a")))["remaining_usd"]) == Decimal("0.30")


async def test_concurrent_reservations_never_admit_more_than_daily_limit(budget_config):
    actor = BillingActor("same-ip")
    results = await asyncio.gather(
        *(reserve(actor, Decimal("0.10"), "query", "fixture") for _ in range(12)),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in results) == 5
    assert sum(isinstance(r, BudgetExceededError) for r in results) == 7
    assert Decimal((await summary(actor))["remaining_usd"]) == 0


async def test_account_and_ip_limits_both_persist_without_double_counting(account):
    actor = BillingActor("ip-a", account)
    ticket = await reserve(actor, Decimal("0.40"), "query", "fixture")
    await settle(ticket, Decimal("0.40"))
    assert Decimal((await summary(actor))["spent_usd"]) == Decimal("0.40")
    with pytest.raises(BudgetExceededError):
        await reserve(BillingActor("ip-a"), Decimal("0.20"), "query", "fixture")
    with pytest.raises(BudgetExceededError):
        await reserve(BillingActor("ip-b", account), Decimal("0.20"), "query", "fixture")


async def test_account_keeps_existing_spend_when_importing_another_ip(account):
    previous = await reserve(BillingActor("ip-old", account), Decimal("0.10"), "query", "fixture")
    await settle(previous, Decimal("0.10"))
    guest = await reserve(BillingActor("ip-new"), Decimal("0.20"), "query", "fixture")
    await settle(guest, Decimal("0.20"))
    assert Decimal((await summary(BillingActor("ip-new", account)))["remaining_usd"]) == Decimal(
        "0.20"
    )


async def test_unknown_usage_retains_reservation_and_settlement_is_idempotent(budget_config):
    actor = BillingActor("ip-a")
    ticket = await reserve(actor, Decimal("0.40"), "query", "fixture")
    await settle(ticket, None)
    assert Decimal((await summary(actor))["reserved_usd"]) == Decimal("0.40")
    await settle(ticket, Decimal("0.20"))
    await settle(ticket, Decimal("0.20"))
    with pytest.raises(BudgetUnavailableError):
        await settle(ticket, Decimal("0.10"))


async def test_utc_rollover_does_not_move_old_reservations_to_new_day(account, monkeypatch):
    import app.billing.service as service

    today = date(2026, 9, 10)
    monkeypatch.setattr(service, "_day", lambda: today)
    ticket = await reserve(BillingActor("ip-a"), Decimal("0.50"), "query", "fixture")
    await summary(BillingActor("ip-a", account))
    monkeypatch.setattr(service, "_day", lambda: today + timedelta(days=1))
    await settle(ticket, Decimal("0.40"))
    assert Decimal((await summary(BillingActor("ip-a", account)))["remaining_usd"]) == Decimal(
        "0.50"
    )


async def test_import_race_with_settlement_does_not_copy_a_stale_debit(account):
    actor = BillingActor("ip-a", account)
    ticket = await reserve(BillingActor("ip-a"), Decimal("0.50"), "query", "fixture")
    await asyncio.gather(summary(actor), settle(ticket, Decimal("0.20")))
    assert Decimal((await summary(actor))["remaining_usd"]) == Decimal("0.30")


async def test_llm_denied_before_transport_and_real_usage_releases_reserve(budget_config):
    import httpx

    from app.billing.context import current_billing_actor
    from app.generation.llm.openai_compat import OpenAICompatLLM

    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(
            200,
            text='data: {"usage":{"prompt_tokens":10,"completion_tokens":20}}\n\ndata: [DONE]\n\n',
        )

    actor = BillingActor("llm-ip")
    token = current_billing_actor.set(actor)
    try:
        llm = OpenAICompatLLM(
            "https://api.deepseek.com",
            "fixture",
            "deepseek-flash",
            0,
            100,
            transport=httpx.MockTransport(handler),
        )
        assert [event async for event in llm.stream("System", "Question")]
        assert len(called) == 1
        state = await summary(actor)
        assert Decimal(state["spent_usd"]) == Decimal("0.00002700")
        assert Decimal(state["reserved_usd"]) == 0
        await reserve(actor, Decimal("0.4999"), "fixture", "fixture")
        with pytest.raises(BudgetExceededError):
            _ = [event async for event in llm.stream("System", "Question")]
        assert len(called) == 1
    finally:
        current_billing_actor.reset(token)


async def test_provider_unknown_usage_and_client_close_keep_reservation(budget_config):
    import httpx

    from app.billing.context import current_billing_actor
    from app.generation.llm.openai_compat import OpenAICompatLLM

    actor = BillingActor("disconnect-ip")
    token = current_billing_actor.set(actor)
    try:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200, text='data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n'
            )
        )
        llm = OpenAICompatLLM(
            "https://api.deepseek.com", "fixture", "deepseek-flash", 0, 100, transport=transport
        )
        stream = llm.stream("System", "Question")
        await anext(stream)
        await stream.aclose()
        state = await summary(actor)
        assert Decimal(state["reserved_usd"]) > 0
        assert Decimal(state["spent_usd"]) == 0
    finally:
        current_billing_actor.reset(token)


async def test_paid_provider_without_identity_fails_before_network(budget_config):
    import httpx

    from app.generation.llm.openai_compat import OpenAICompatLLM

    called = []
    transport = httpx.MockTransport(lambda request: called.append(request))
    llm = OpenAICompatLLM(
        "https://api.deepseek.com", "fixture", "deepseek-flash", 0, 100, transport=transport
    )
    with pytest.raises(BudgetUnavailableError):
        _ = [event async for event in llm.stream("System", "Question")]
    assert not called
