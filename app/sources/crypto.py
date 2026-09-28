"""Encryption at rest for source credentials (Fernet, key from SOURCE_CREDENTIALS_KEY).

Run ``python -m app.sources.crypto`` to print a fresh key.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.core.errors import SourcesDisabledError


def validate_key(key: str) -> bool:
    try:
        Fernet(key.encode("ascii"))
    except (ValueError, TypeError):
        return False
    return True


def _fernet() -> Fernet:
    key = get_settings().source_credentials_key
    if key is None:
        raise SourcesDisabledError(
            "External sources are disabled on this server (SOURCE_CREDENTIALS_KEY is not set)."
        )
    return Fernet(key.encode("ascii"))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # the key was rotated or the row was tampered with; either way the source is dead
        raise SourcesDisabledError(
            "Stored source credentials cannot be decrypted with the configured key."
        ) from None


if __name__ == "__main__":
    print(Fernet.generate_key().decode("ascii"))
