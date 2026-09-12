"""SMTP delivery behind a Protocol; no production capture or success stub exists."""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

import anyio

from app.accounts.errors import AccountUnavailableError
from app.config import Settings, get_settings


class Mailer(Protocol):
    async def send(self, recipient: str, subject: str, body: str) -> None: ...


class SMTPMailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _send(self, recipient: str, subject: str, body: str) -> None:
        settings = self.settings
        if not settings.smtp_host or not settings.smtp_from:
            raise AccountUnavailableError("Email delivery is not configured.")
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_s
            ) as client:
                if settings.smtp_starttls:
                    client.starttls(context=ssl.create_default_context())
                if settings.smtp_username and settings.smtp_password:
                    client.login(settings.smtp_username, settings.smtp_password)
                refused = client.send_message(message)
                if refused:
                    raise AccountUnavailableError("Email delivery is temporarily unavailable.")
        except (OSError, smtplib.SMTPException):
            raise AccountUnavailableError("Email delivery is temporarily unavailable.") from None

    async def send(self, recipient: str, subject: str, body: str) -> None:
        await anyio.to_thread.run_sync(self._send, recipient, subject, body)


def get_mailer() -> Mailer:
    if not get_settings().registration_available:
        raise AccountUnavailableError("Email delivery is not configured.")
    return SMTPMailer(get_settings())
