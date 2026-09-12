"""Idempotency-Key support (Redis).

    SET idem:{tenant}:{key} "in-flight" NX EX ttl
      ├─ won  → run the handler → store {status, body} under the same key
      └─ lost → GET:
           "in-flight"  → 409 request_in_flight (a concurrent duplicate)
           stored result → replay: same status/body + X-Idempotency-Replay: true

Failed handlers release the key — an error response must not lock the client out of
retrying for the TTL. A fingerprint of the request can be stored with the result: a
replay with a different fingerprint is refused (422) — the same key must not hand a
response produced under one access role to a caller asserting another. Applies to
non-streaming endpoints only: a replayed SSE stream has no meaningful semantics
(documented on the query route). Redis down → fail open with an error log: for uploads
the dedup unique constraint still guards side effects.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from app.config import get_settings
from app.core.errors import IdempotencyKeyReusedError, RequestInFlightError
from app.core.redis import get_redis

log = structlog.get_logger("docqa.idempotency")

_IN_FLIGHT = "in-flight"

_RELEASE_LUA = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"
)
_STORE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
end
return 0
"""


async def purge_tenant_cache(tenant_id: uuid.UUID) -> None:
    # Historic entries have no collection metadata. Clear this tenant's replay
    # cache conservatively; other collections' actual documents/queries stay intact.
    redis = get_redis()
    async for key in redis.scan_iter(match=f"idem:{tenant_id}:*", count=100):
        await redis.delete(key)


Handler = Callable[[], Awaitable[tuple[int, dict[str, Any]]]]


@dataclass(frozen=True)
class IdempotentResult:
    status: int
    body: dict[str, Any]
    replayed: bool


async def run_idempotent(
    tenant_id: uuid.UUID,
    idempotency_key: str,
    handler: Handler,
    fingerprint: str | None = None,
    cache_valid: Callable[[], Awaitable[bool]] | None = None,
    *,
    visitor_scope: str | None = None,
) -> IdempotentResult:
    """``fingerprint`` binds the key to the request that first used it: a replay attempt
    with a different fingerprint (same key, other question or other access role) is
    rejected instead of handing out the stored response."""
    redis = get_redis()
    namespace = f"{tenant_id}:{visitor_scope}" if visitor_scope else str(tenant_id)
    key = f"idem:{namespace}:{idempotency_key}"
    ttl = get_settings().idempotency_ttl_s
    token = f"in-flight:{uuid.uuid4()}"

    try:
        won = await redis.set(key, token, nx=True, ex=ttl)
    except Exception:
        log.error("idempotency_unavailable_failing_open")
        status, body = await handler()
        return IdempotentResult(status=status, body=body, replayed=False)

    if won:
        try:
            status, body = await handler()
        except BaseException:
            # an error must not lock the key for the whole TTL — let the client retry
            try:
                await redis.eval(_RELEASE_LUA, 1, key, token)
            except Exception:
                log.error("idempotency_release_failed", key=key)
            raise
        try:
            if cache_valid is None or await cache_valid():
                await redis.eval(
                    _STORE_LUA,
                    1,
                    key,
                    token,
                    json.dumps({"status": status, "body": body, "fp": fingerprint}),
                    ttl,
                )
            else:
                await redis.eval(_RELEASE_LUA, 1, key, token)
        except Exception:
            log.error("idempotency_store_failed", key=key)
        return IdempotentResult(status=status, body=body, replayed=False)

    stored = await redis.get(key)
    if isinstance(stored, bytes):
        stored = stored.decode("utf-8")
    if stored is None or stored.startswith(_IN_FLIGHT):
        raise RequestInFlightError(
            "A request with this Idempotency-Key is currently being processed."
        )
    if cache_valid is not None and not await cache_valid():
        raise IdempotencyKeyReusedError(
            "Collection data changed. Retry with a fresh Idempotency-Key."
        )
    data = json.loads(stored)
    stored_fp = data.get("fp")
    if fingerprint is not None and stored_fp != fingerprint:
        raise IdempotencyKeyReusedError(
            "This Idempotency-Key was already used for a different request "
            "(other question, collection or role). Use a fresh key."
        )
    return IdempotentResult(status=data["status"], body=data["body"], replayed=True)


def replay_headers(result: IdempotentResult) -> dict[str, str] | None:
    return {"X-Idempotency-Replay": "true"} if result.replayed else None
