"""Google OIDC code exchange. Provider tokens never leave this module."""

import asyncio
import json
import re
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
import jwt
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.config import Settings

ISSUER = "https://accounts.google.com"
AUTHORIZATION_URL = f"{ISSUER}/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_EMAIL = TypeAdapter(EmailStr)


class GoogleProviderError(Exception):
    def __init__(self) -> None:
        super().__init__("Google sign-in could not be completed.")


@dataclass(frozen=True)
class GoogleIdentityClaims:
    issuer: str
    subject: str
    email: str


async def _json_response(
    client: httpx.AsyncClient, method: str, url: str, data: dict[str, str] | None = None
) -> tuple[dict[str, Any], httpx.Headers]:
    # Size as well as time is bounded, including chunked/malformed upstream bodies.
    async with client.stream(method, url, data=data) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > 65536:
                raise GoogleProviderError()
        decoded = json.loads(body)
        if not isinstance(decoded, dict):
            raise GoogleProviderError()
        return decoded, response.headers


class GoogleProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport
        self._keys: dict[str, jwt.PyJWK] = {}
        self._expires_at = 0.0
        self._fetched_at = float("-inf")
        self._lock = asyncio.Lock()

    async def _key(self, kid: str, client: httpx.AsyncClient) -> jwt.PyJWK:
        async with self._lock:
            now = time.monotonic()
            if kid in self._keys and now < self._expires_at:
                return self._keys[kid]
            # A new kid triggers rotation refresh, at most once per 30 seconds.
            # Failed refreshes are throttled too; stale keys are never used after TTL.
            if now - self._fetched_at < 30:
                raise GoogleProviderError()
            self._fetched_at = now
            payload, headers = await _json_response(client, "GET", JWKS_URL)
            keys = payload.get("keys")
            if not isinstance(keys, list) or not 1 <= len(keys) <= 16:
                raise GoogleProviderError()
            parsed: dict[str, jwt.PyJWK] = {}
            for key in keys:
                if (
                    not isinstance(key, dict)
                    or key.get("kty") != "RSA"
                    or key.get("alg") != "RS256"
                    or key.get("use") != "sig"
                    or not isinstance(key.get("kid"), str)
                    or not 1 <= len(key["kid"]) <= 256
                    or key["kid"] in parsed
                ):
                    raise GoogleProviderError()
                parsed[key["kid"]] = jwt.PyJWK.from_dict(key, algorithm="RS256")
            match = re.search(r"(?:^|[,\s])max-age=(\d+)", headers.get("cache-control", ""))
            lifetime = min(3600, max(30, int(match[1]))) if match else 300
            self._keys = parsed
            self._expires_at = now + lifetime
            if kid not in parsed:
                raise GoogleProviderError()
            return parsed[kid]

    async def exchange(
        self, code: str, verifier: str, nonce: str, settings: Settings
    ) -> GoogleIdentityClaims:
        try:
            async with (
                asyncio.timeout(20),
                httpx.AsyncClient(
                    timeout=httpx.Timeout(10, connect=5),
                    follow_redirects=False,
                    transport=self.transport,
                ) as client,
            ):
                payload, _ = await _json_response(
                    client,
                    "POST",
                    TOKEN_URL,
                    {
                        "code": code,
                        "client_id": settings.google_client_id or "",
                        "client_secret": settings.google_client_secret or "",
                        "redirect_uri": settings.google_redirect_uri,
                        "grant_type": "authorization_code",
                        "code_verifier": verifier,
                    },
                )
                token = payload.get("id_token")
                if not isinstance(token, str) or not 1 <= len(token) <= 16384:
                    raise GoogleProviderError()
                header = jwt.get_unverified_header(token)
                kid = header.get("kid")
                if (
                    header.get("alg") != "RS256"
                    or not isinstance(kid, str)
                    or not 1 <= len(kid) <= 256
                ):
                    raise GoogleProviderError()
                key = await self._key(kid, client)
                claims = jwt.decode(
                    token,
                    key.key,
                    algorithms=["RS256"],
                    audience=settings.google_client_id,
                    issuer=[ISSUER, "accounts.google.com"],
                    options={
                        "strict_aud": True,
                        "require": [
                            "iss",
                            "aud",
                            "sub",
                            "exp",
                            "iat",
                            "nonce",
                            "email",
                            "email_verified",
                        ],
                    },
                )
                subject, email, token_nonce = claims["sub"], claims["email"], claims["nonce"]
                if (
                    not isinstance(subject, str)
                    or not 1 <= len(subject) <= 255
                    or not isinstance(token_nonce, str)
                    or not secrets.compare_digest(token_nonce, nonce)
                    or claims["email_verified"] is not True
                    or not isinstance(email, str)
                    or len(email) > 254
                    or type(claims["iat"]) is not int
                    or type(claims["exp"]) is not int
                    or claims.get("azp", settings.google_client_id) != settings.google_client_id
                ):
                    raise GoogleProviderError()
                email = str(_EMAIL.validate_python(email)).casefold()
                return GoogleIdentityClaims(ISSUER, subject, email)
        except (
            httpx.HTTPError,
            TimeoutError,
            jwt.PyJWTError,
            ValueError,
            TypeError,
            ValidationError,
        ):
            raise GoogleProviderError() from None


@lru_cache
def get_google_provider() -> GoogleProvider:
    return GoogleProvider()
