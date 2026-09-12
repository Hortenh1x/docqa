"""Real RSA signatures with local HTTP transports; Google never receives test data."""

import json
import time
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def claims(**overrides):
    now = int(time.time())
    return {
        "iss": "https://accounts.google.com",
        "aud": "test-client",
        "sub": "stable-subject",
        "iat": now,
        "exp": now + 300,
        "nonce": "expected-nonce",
        "email": "Alice@example.com",
        "email_verified": True,
        **overrides,
    }


def jwk(key, kid="key-1"):
    return {
        **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
    }


async def exchange(signing_key, payload=None, *, token_key=None, response_status=200):
    from app.accounts.google_provider import GoogleProvider
    from app.config import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://unused",
        redis_url="redis://unused",
        google_client_id="test-client",
        google_client_secret="server-secret",
    )
    token = jwt.encode(
        payload or claims(), token_key or signing_key, algorithm="RS256", headers={"kid": "key-1"}
    )
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.scheme == "https"
        if request.url.path == "/token":
            body = parse_qs(request.content.decode())
            assert body["code_verifier"] == ["pkce-verifier"]
            assert body["client_secret"] == ["server-secret"]
            assert body["grant_type"] == ["authorization_code"]
            return httpx.Response(
                response_status, json={"id_token": token, "access_token": "discard"}
            )
        assert str(request.url) == "https://www.googleapis.com/oauth2/v3/certs"
        return httpx.Response(
            200,
            json={"keys": [jwk(signing_key)]},
            headers={"cache-control": "public, max-age=3600"},
        )

    provider = GoogleProvider(httpx.MockTransport(handle))
    result = await provider.exchange("one-time-code", "pkce-verifier", "expected-nonce", settings)
    return result, provider, settings, requests


async def test_signed_google_token_returns_only_verified_identity(signing_key):
    identity, _, _, requests = await exchange(signing_key)
    assert identity.issuer == "https://accounts.google.com"
    assert identity.subject == "stable-subject"
    assert identity.email == "alice@example.com"
    assert not hasattr(identity, "id_token")
    assert len(requests) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://accounts.google.com.attacker.test"},
        {"aud": "other-client"},
        {"aud": ["test-client", "other-client"]},
        {"nonce": "wrong"},
        {"exp": 1},
        {"iat": 4102444800},
        {"email_verified": False},
        {"email_verified": "true"},
        {"email": "invalid"},
        {"sub": ""},
        {"azp": "another-client"},
        {"exp": True},
        {"iat": "1"},
    ],
)
async def test_invalid_signed_claims_fail_closed(signing_key, overrides):
    from app.accounts.google_provider import GoogleProviderError

    with pytest.raises(GoogleProviderError):
        await exchange(signing_key, claims(**overrides))


async def test_invalid_signature_fails_closed(signing_key):
    from app.accounts.google_provider import GoogleProviderError

    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(GoogleProviderError):
        await exchange(signing_key, token_key=wrong_key)


async def test_google_legacy_exact_issuer_is_canonicalized(signing_key):
    identity, _, _, _ = await exchange(signing_key, claims(iss="accounts.google.com"))
    assert identity.issuer == "https://accounts.google.com"


async def test_provider_failure_hides_token_details(signing_key):
    from app.accounts.google_provider import GoogleProviderError

    with pytest.raises(GoogleProviderError) as caught:
        await exchange(signing_key, response_status=400)
    assert "server-secret" not in str(caught.value)
    assert "one-time-code" not in str(caught.value)


async def test_jwks_is_cached_with_bounded_rotation_refresh(signing_key):
    from app.accounts.google_provider import GoogleProviderError

    _, provider, settings, requests = await exchange(signing_key)
    await provider.exchange("another-code", "pkce-verifier", "expected-nonce", settings)
    assert len([r for r in requests if r.url.path.endswith("certs")]) == 1
    # Unknown kids cannot force an unbounded key fetch for every callback.
    with pytest.raises(GoogleProviderError):
        await provider._key("unknown", httpx.AsyncClient(transport=provider.transport))
    assert len([r for r in requests if r.url.path.endswith("certs")]) == 1


async def test_google_jwks_refreshes_for_new_key_after_rotation_interval(signing_key, monkeypatch):
    from app.accounts.google_provider import GoogleProvider
    from app.config import Settings

    rotated_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    current = {"key": signing_key, "kid": "old"}
    fetches = []

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={
                    "id_token": jwt.encode(
                        claims(), current["key"], algorithm="RS256", headers={"kid": current["kid"]}
                    )
                },
            )
        fetches.append(True)
        return httpx.Response(
            200,
            json={"keys": [jwk(current["key"], current["kid"])]},
            headers={"cache-control": "max-age=999999999"},
        )

    provider = GoogleProvider(httpx.MockTransport(handler))
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://unused",
        redis_url="redis://unused",
        google_client_id="test-client",
        google_client_secret="secret",
    )
    await provider.exchange("code", "verifier", "expected-nonce", settings)
    assert provider._expires_at - provider._fetched_at <= 3600
    current.update(key=rotated_key, kid="new")
    monkeypatch.setattr(provider, "_fetched_at", provider._fetched_at - 31)
    result = await provider.exchange("code", "verifier", "expected-nonce", settings)
    assert result.subject == "stable-subject" and fetches == [True, True]


@pytest.mark.parametrize("fault", ["algorithm", "timeout", "oversize", "redirect", "malformed"])
async def test_provider_rejects_untrusted_or_unbounded_response(fault):
    from app.accounts.google_provider import GoogleProvider, GoogleProviderError
    from app.config import Settings

    calls = []

    def handler(request):
        calls.append(request)
        if fault == "timeout":
            raise httpx.ReadTimeout("private provider detail")
        if fault == "redirect":
            return httpx.Response(302, headers={"location": "https://evil.test"})
        if fault == "oversize":
            return httpx.Response(200, content=b"x" * 65537)
        if fault == "malformed":
            return httpx.Response(200, json=["wrong shape"])
        return httpx.Response(
            200,
            json={
                "id_token": jwt.encode(
                    claims(), "x" * 32, algorithm="HS256", headers={"kid": "key-1"}
                )
            },
        )

    provider = GoogleProvider(httpx.MockTransport(handler))
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://unused",
        redis_url="redis://unused",
        google_client_id="test-client",
        google_client_secret="secret",
    )
    with pytest.raises(GoogleProviderError):
        await provider.exchange("code", "verifier", "expected-nonce", settings)
    assert len(calls) == 1
