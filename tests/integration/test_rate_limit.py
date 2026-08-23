import pytest

from app.config import get_settings


@pytest.fixture
def tiny_limits(monkeypatch, app_env):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_DEFAULT_PER_MINUTE", "3")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_over_limit_yields_429_with_retry_after(client, tenant, tiny_limits):
    for expected_remaining in (2, 1, 0):
        response = await client.get("/v1/collections", headers=tenant["headers"])
        assert response.status_code == 200
        assert response.headers["x-ratelimit-limit"] == "3"
        assert response.headers["x-ratelimit-remaining"] == str(expected_remaining)

    blocked = await client.get("/v1/collections", headers=tenant["headers"])
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "rate_limited"
    assert "request_id" in body
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-ratelimit-remaining"] == "0"


async def test_buckets_are_per_api_key(client, make_tenant, tiny_limits):
    alice, bob = await make_tenant(), await make_tenant()

    for _ in range(3):
        assert (await client.get("/v1/collections", headers=alice["headers"])).status_code == 200
    assert (await client.get("/v1/collections", headers=alice["headers"])).status_code == 429

    # a different key has its own bucket
    assert (await client.get("/v1/collections", headers=bob["headers"])).status_code == 200


async def test_disabled_limiter_is_a_noop(client, tenant):
    # app_env sets RATE_LIMIT_ENABLED=false — burst freely
    for _ in range(10):
        assert (await client.get("/v1/collections", headers=tenant["headers"])).status_code == 200


# --- daily query quota (demo cost cap) ---


@pytest.fixture
def tiny_daily_quota(monkeypatch, app_env):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_QUERY_PER_MINUTE", "100")  # keep the bucket out of the way
    monkeypatch.setenv("RATE_LIMIT_QUERY_PER_DAY", "2")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _empty_collection(client, headers) -> str:
    created = await client.post("/v1/collections", json={"name": "Quota"}, headers=headers)
    assert created.status_code == 201
    return created.json()["id"]


async def _ask(client, headers, collection_id):
    return await client.post(
        "/v1/query",
        json={"collection_id": collection_id, "question": "anything", "stream": False},
        headers=headers,
    )


async def test_daily_query_quota_yields_429(client, tenant, tiny_daily_quota):
    collection_id = await _empty_collection(client, tenant["headers"])

    for expected_remaining in (1, 0):
        response = await _ask(client, tenant["headers"], collection_id)
        # empty collection -> $0 refusal; still a query, still charged against the day
        assert response.status_code == 200
        assert response.headers["x-quota-daily-limit"] == "2"
        assert response.headers["x-quota-daily-remaining"] == str(expected_remaining)

    blocked = await _ask(client, tenant["headers"], collection_id)
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "daily_quota_exceeded"
    assert "request_id" in body
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-quota-daily-remaining"] == "0"

    # non-query classes are not charged and never quota-blocked
    listing = await client.get("/v1/collections", headers=tenant["headers"])
    assert listing.status_code == 200
    assert "x-quota-daily-limit" not in listing.headers


async def test_daily_quota_scopes_by_forwarded_client(
    client, tenant, tiny_daily_quota, monkeypatch
):
    # the public demo shares ONE api key across visitors — the quota must split by
    # client address taken from X-Forwarded-For (trusted proxy overwrites it)
    monkeypatch.setenv("RATE_LIMIT_TRUST_FORWARDED_FOR", "true")
    get_settings.cache_clear()
    collection_id = await _empty_collection(client, tenant["headers"])

    alice = {**tenant["headers"], "X-Forwarded-For": "203.0.113.7"}
    bob = {**tenant["headers"], "X-Forwarded-For": "203.0.113.8, 10.0.0.1"}

    for _ in range(2):
        assert (await _ask(client, alice, collection_id)).status_code == 200
    assert (await _ask(client, alice, collection_id)).status_code == 429

    # a different visitor behind the same shared key has an untouched budget
    assert (await _ask(client, bob, collection_id)).status_code == 200
