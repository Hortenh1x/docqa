"""Password policy and mail boundaries; no external password checker is used."""

import httpx
import pytest

from app.accounts.errors import WeakPasswordError
from app.accounts.passwords import validate_password


@pytest.mark.parametrize(
    "password", ["aaaaaaa1", "password1", "Qwerty12", "пароль12", "letters١", " " * 1000 + "a1"]
)
async def test_password_accepts_exact_owner_rules_without_network(monkeypatch, password):
    def no_network(*args, **kwargs):
        raise AssertionError("Password validation must not contact an external service")

    monkeypatch.setattr(httpx, "AsyncClient", no_network)
    await validate_password(password)


@pytest.mark.parametrize(
    "password", ["", "short1", "abcdef1", "abcdefgh", "12345678", "$$$$$$$1", "aaaaaaa²"]
)
async def test_password_rejects_missing_length_letter_or_decimal_digit(password):
    with pytest.raises(WeakPasswordError):
        await validate_password(password)


async def test_smtp_uses_tls_and_captures_message_locally(monkeypatch):
    from app.accounts.mail import SMTPMailer
    from app.config import Settings

    calls = []

    class LocalCaptureSMTP:
        def __init__(self, host, port, timeout):
            calls.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self, context):
            calls.append("tls")

        def login(self, username, password):
            calls.append("login")

        def send_message(self, message):
            calls.append(message)
            return {}

    monkeypatch.setattr("app.accounts.mail.smtplib.SMTP", LocalCaptureSMTP)
    settings = Settings(
        _env_file=None,
        smtp_host="localhost",
        smtp_from="accounts@example.com",
        smtp_username="test-user",
        smtp_password="test-password",
    )
    await SMTPMailer(settings).send("alice@example.com", "Verify", "local token body")
    assert calls[1:3] == ["tls", "login"]
    assert calls[3]["To"] == "alice@example.com"
    assert calls[3].get_content() == "local token body\n"


def test_cookie_accounts_reject_wildcard_cors():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="exact"):
        Settings(_env_file=None, accounts_enabled=True, cors_origins="*")
