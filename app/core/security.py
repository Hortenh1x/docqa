"""API key generation and verification.

Key format: ``dqa_live_<32 base62 chars>``. The DB stores only the sha256 of the full
key plus the first 8 characters of the secret (lookup + safe display). Keys are
high-entropy random strings, so a fast hash is sufficient — bcrypt would only add latency.
The plaintext is shown exactly once, at creation time.
"""

import hashlib
import secrets

KEY_ENV_PREFIX = "dqa_live_"
SECRET_LENGTH = 32
PREFIX_LENGTH = 8

_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(plaintext, prefix, sha256_hex)``."""
    secret = "".join(secrets.choice(_BASE62) for _ in range(SECRET_LENGTH))
    plaintext = KEY_ENV_PREFIX + secret
    return plaintext, secret[:PREFIX_LENGTH], hash_api_key(plaintext)


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def split_api_key(plaintext: str) -> str | None:
    """Return the lookup prefix for a presented key, or None if malformed."""
    if not plaintext.startswith(KEY_ENV_PREFIX):
        return None
    secret = plaintext[len(KEY_ENV_PREFIX) :]
    if len(secret) != SECRET_LENGTH or not all(c in _BASE62 for c in secret):
        return None
    return secret[:PREFIX_LENGTH]


def verify_api_key(plaintext: str, key_hash: str) -> bool:
    return secrets.compare_digest(hash_api_key(plaintext), key_hash)


def display_key(prefix: str) -> str:
    """Human-readable identifier for logs/CLI: never the secret itself."""
    return f"{KEY_ENV_PREFIX}{prefix}…"
