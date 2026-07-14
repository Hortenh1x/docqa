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
