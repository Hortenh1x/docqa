"""Google activation is server-only and independent of SMTP."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def settings(**values):
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://unused",
        redis_url="redis://unused",
        **values,
    )


def test_google_disabled_without_both_credentials():
    assert settings(accounts_enabled=True).google_available is False
    assert (
        settings(google_client_id="client", google_client_secret="secret").google_available is False
    )


def test_google_works_without_smtp_and_keeps_secret_out_of_repr():
    configured = settings(
        accounts_enabled=True, google_client_id="client", google_client_secret="private-secret"
    )
    assert configured.google_available is True
    assert configured.registration_available is False
    assert "private-secret" not in repr(configured)


@pytest.mark.parametrize("value", [{"google_client_id": "id"}, {"google_client_secret": "secret"}])
def test_partial_configuration_fails_fast(value):
    with pytest.raises(ValidationError, match="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"):
        settings(**value)


@pytest.mark.parametrize(
    "uri",
    [
        "http://api.example.com/v1/auth/google/callback",
        "https://user:pass@api.example.com/v1/auth/google/callback",
        "https://api.example.com/other",
        "https://api.example.com/v1/auth/google/callback?redirect=evil",
        "https://api.example.com/v1/auth/google/callback#fragment",
        "javascript:alert(1)",
    ],
)
def test_unsafe_google_redirect_is_rejected(uri):
    with pytest.raises(ValidationError, match="GOOGLE_REDIRECT_URI"):
        settings(google_redirect_uri=uri)


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost:8000/v1/auth/google/callback",
        "https://api.docqa.net/v1/auth/google/callback",
    ],
)
def test_exact_callback_endpoints_are_accepted(uri):
    assert settings(google_redirect_uri=uri).google_redirect_uri == uri
