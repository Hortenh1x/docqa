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
) -> IdempotentResult:
    """``fingerprint`` binds the key to the request that first used it: a replay attempt
    with a different fingerprint (same key, other question or other access role) is
    rejected instead of handing out the stored response."""
    redis = get_redis()
    key = f"idem:{tenant_id}:{idempotency_key}"
    ttl = get_settings().idempotency_ttl_s

    try:
        won = await redis.set(key, _IN_FLIGHT, nx=True, ex=ttl)
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
                await redis.delete(key)
            except Exception:
                log.error("idempotency_release_failed", key=key)
            raise
        try:
            await redis.set(
                key, json.dumps({"status": status, "body": body, "fp": fingerprint}), ex=ttl
            )
        except Exception:
            log.error("idempotency_store_failed", key=key)
        return IdempotentResult(status=status, body=body, replayed=False)

    stored = await redis.get(key)
    if stored is None or stored == _IN_FLIGHT:
        raise RequestInFlightError(
            "A request with this Idempotency-Key is currently being processed."
        )
    data = json.loads(stored)
    stored_fp = data.get("fp")
    if fingerprint is not None and stored_fp is not None and stored_fp != fingerprint:
        raise IdempotencyKeyReusedError(
            "This Idempotency-Key was already used for a different request "
            "(other question, collection or role). Use a fresh key."
        )
    return IdempotentResult(status=data["status"], body=data["body"], replayed=True)


def replay_headers(result: IdempotentResult) -> dict[str, str] | None:
    return {"X-Idempotency-Replay": "true"} if result.replayed else None
