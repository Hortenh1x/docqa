import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.core.errors import SourcesDisabledError
from app.sources.crypto import decrypt_secret, encrypt_secret, validate_key


def test_validate_key():
    assert validate_key(Fernet.generate_key().decode())
    assert not validate_key("nope")
    assert not validate_key("")


def test_roundtrip_and_disabled(monkeypatch):
    monkeypatch.setenv("SOURCE_CREDENTIALS_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        token = encrypt_secret("secret_abc")
        assert token != "secret_abc"
        assert decrypt_secret(token) == "secret_abc"
    finally:
        get_settings.cache_clear()

    monkeypatch.delenv("SOURCE_CREDENTIALS_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(SourcesDisabledError):
            encrypt_secret("x")
    finally:
        get_settings.cache_clear()


def test_invalid_key_fails_fast(monkeypatch):
    monkeypatch.setenv("SOURCE_CREDENTIALS_KEY", "not-a-key")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError):
            get_settings()
    finally:
        get_settings.cache_clear()
