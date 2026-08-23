"""Per-API-key rate limiting: a token bucket in Redis, atomic via Lua.

Buckets are keyed ``rl:{key_prefix}:{class}`` — limits are per key, per endpoint class
(query / upload / default). Refill is continuous (limit/60 tokens per second), capacity
equals the per-minute limit.

Deliberate trade-off: when Redis is unavailable the limiter FAILS OPEN with an error
log — availability of search beats enforcement of quotas. Flip this only when quota
abuse costs more than downtime.

On top of the bucket, the query class can carry a **daily quota** (fixed UTC-day
window, ``RATE_LIMIT_QUERY_PER_DAY``) scoped per (api key, client address) — a cost
cap for the public demo where every visitor shares one key. The client address comes
from X-Forwarded-For only when ``RATE_LIMIT_TRUST_FORWARDED_FOR`` says a trusted
proxy overwrites it. Same fail-open policy. Denied requests are not charged; a request
that passes the gate is charged even if it later refuses for $0 — the quota bounds
worst-case spend, not exact spend.
"""

import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import structlog
from fastapi import Request, Response

from app.api.deps import CurrentTenant
from app.config import get_settings
from app.core.errors import DailyQuotaExceededError, RateLimitedError
from app.core.redis import get_redis

log = structlog.get_logger("docqa.rate_limit")

LimitClass = Literal["query", "upload", "default"]

# KEYS[1] bucket; ARGV: capacity, refill_per_sec, now_ms, cost
_TOKEN_BUCKET_LUA = """
local tokens = tonumber(redis.call('HGET', KEYS[1], 't') or ARGV[1])
local ts     = tonumber(redis.call('HGET', KEYS[1], 'ts') or ARGV[3])
tokens = math.min(tonumber(ARGV[1]), tokens + (ARGV[3] - ts) / 1000 * tonumber(ARGV[2]))
if tokens < tonumber(ARGV[4]) then
  redis.call('HSET', KEYS[1], 't', tokens, 'ts', ARGV[3])
  redis.call('PEXPIRE', KEYS[1], 60000)
  return {0, tostring(tokens)}
end
redis.call('HSET', KEYS[1], 't', tokens - ARGV[4], 'ts', ARGV[3])
redis.call('PEXPIRE', KEYS[1], 60000)
return {1, tostring(tokens - ARGV[4])}
"""


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_s: int


def _limit_for(limit_class: LimitClass) -> int:
    settings = get_settings()
    return {
        "query": settings.rate_limit_query_per_minute,
        "upload": settings.rate_limit_upload_per_minute,
        "default": settings.rate_limit_default_per_minute,
    }[limit_class]


async def consume(key_id: str, limit_class: LimitClass, cost: int = 1) -> RateDecision:
    limit = _limit_for(limit_class)
    refill_per_sec = limit / 60.0
    now_ms = int(time.time() * 1000)
    try:
        raw = await get_redis().eval(
            _TOKEN_BUCKET_LUA,
            1,
            f"rl:{key_id}:{limit_class}",
            limit,
            refill_per_sec,
            now_ms,
            cost,
        )
    except Exception:
        log.error("rate_limiter_unavailable_failing_open", limit_class=limit_class)
        return RateDecision(allowed=True, limit=limit, remaining=limit, retry_after_s=0)

    allowed = int(raw[0]) == 1
    tokens = float(raw[1])
    retry_after = 0 if allowed else max(1, math.ceil((cost - tokens) / refill_per_sec))
    return RateDecision(
        allowed=allowed,
        limit=limit,
        remaining=max(0, math.floor(tokens)),
        retry_after_s=retry_after,
    )


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_s: int


def _client_address(request: Request) -> str:
    """The per-visitor half of the daily-quota scope."""
    if get_settings().rate_limit_trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "local"


async def consume_daily(scope: str, limit: int) -> QuotaDecision:
    """Fixed-window daily counter, resets at UTC midnight; INCR + first-hit EXPIRE."""
    now = int(time.time())
    day_key = f"dq:{scope}:{time.strftime('%Y%m%d', time.gmtime(now))}"
    retry_after = 86400 - now % 86400
    try:
        redis = get_redis()
        used = int(await redis.incr(day_key))
        if used == 1:
            await redis.expire(day_key, 90000)  # 25h: outlives its window, then self-cleans
    except Exception:
        log.error("daily_quota_unavailable_failing_open")
        return QuotaDecision(allowed=True, limit=limit, remaining=limit, retry_after_s=0)
    return QuotaDecision(
        allowed=used <= limit,
        limit=limit,
        remaining=max(0, limit - used),
        retry_after_s=retry_after,
    )


def rate_limit(limit_class: LimitClass) -> Callable[..., Awaitable[None]]:
    """Dependency factory: attach per-class limits point-wise to routes."""

    async def guard(request: Request, response: Response, tenant: CurrentTenant) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        key_id = getattr(request.state, "api_key_prefix", None) or str(tenant.id)
        decision = await consume(key_id, limit_class)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        if not decision.allowed:
            # denied before the daily counter on purpose: a 429 costs nothing
            raise RateLimitedError(
                f"Rate limit exceeded for '{limit_class}' requests. "
                f"Retry in {decision.retry_after_s}s.",
                headers={
                    "Retry-After": str(decision.retry_after_s),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": str(decision.remaining),
                },
            )

        if limit_class == "query" and settings.rate_limit_query_per_day > 0:
            scope = f"{key_id}:{_client_address(request)}"
            quota = await consume_daily(scope, settings.rate_limit_query_per_day)
            response.headers["X-Quota-Daily-Limit"] = str(quota.limit)
            response.headers["X-Quota-Daily-Remaining"] = str(quota.remaining)
            if not quota.allowed:
                raise DailyQuotaExceededError(
                    f"Daily query quota exceeded. Resets in {quota.retry_after_s}s.",
                    headers={
                        "Retry-After": str(quota.retry_after_s),
                        "X-Quota-Daily-Limit": str(quota.limit),
                        "X-Quota-Daily-Remaining": "0",
                    },
                )

    return guard
