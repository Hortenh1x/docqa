"""The owner's password rules and bounded Argon2id hashing."""

import secrets

import anyio
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.accounts.errors import PasswordMismatchError, WeakPasswordError

_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))
_hash_limiter = anyio.CapacityLimiter(4)


async def validate_password(password: str) -> None:
    if (
        len(password) < 8
        or not any(character.isalpha() for character in password)
        or not any(character.isdecimal() for character in password)
    ):
        raise WeakPasswordError()


def confirm_password(password: str, confirmation: str) -> None:
    if password != confirmation:
        raise PasswordMismatchError()


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hasher.hash, password, limiter=_hash_limiter)


def _verify(encoded: str | None, password: str) -> bool:
    try:
        valid = _hasher.verify(encoded or _dummy_hash, password)
        return encoded is not None and valid
    except (VerificationError, InvalidHashError):
        return False


async def verify_password(encoded: str | None, password: str) -> bool:
    return await anyio.to_thread.run_sync(_verify, encoded, password, limiter=_hash_limiter)
