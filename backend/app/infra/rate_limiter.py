"""Redis-backed rate limiter for API endpoints.

Uses a sliding window counter pattern stored in Redis.
Each rate limit is defined as (max_requests, window_seconds).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.infra.redis_client import redis_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimit:
    """Rate limit definition."""

    max_requests: int
    window_seconds: int

    @property
    def retry_after(self) -> int:
        return self.window_seconds


# Pre-defined limits
LOGIN_LIMIT = RateLimit(max_requests=5, window_seconds=60)
REGISTER_LIMIT = RateLimit(max_requests=3, window_seconds=3600)
REFRESH_LIMIT = RateLimit(max_requests=10, window_seconds=60)


def _get_client_ip(request: Request) -> str:
    """Extract client IP for rate limiting.

    Only trusts X-Forwarded-For when RATE_LIMIT_TRUST_PROXY_HEADERS is enabled,
    indicating the app runs behind a trusted reverse proxy.
    """
    settings = get_settings()
    if settings.rate_limit_trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_rate_limit(
    request: Request,
    limit: RateLimit,
    key_prefix: str,
) -> None:
    """Check and enforce a rate limit. Raises HTTPException 429 if exceeded.

    Args:
        request: The incoming FastAPI request (for IP extraction).
        limit: The RateLimit to enforce.
        key_prefix: Redis key namespace (e.g. "rl:login").

    Raises:
        HTTPException: 429 if rate limit exceeded.
    """
    client_ip = _get_client_ip(request)
    redis_key = f"{key_prefix}:{client_ip}"
    now = time.time()
    window_start = now - limit.window_seconds

    try:
        pipe = redis_client.client.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # Count current window
        pipe.zcard(redis_key)
        # Add current request
        pipe.zadd(redis_key, {str(now): now})
        # Set TTL on the key
        pipe.expire(redis_key, limit.window_seconds)
        results = await pipe.execute()

        current_count = results[1]  # zcard result
    except Exception:
        # If Redis is down, fail open (allow the request)
        logger.warning("Rate limiter Redis error — failing open")
        return

    if current_count >= limit.max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Try again in {limit.retry_after} seconds.",
            headers={"Retry-After": str(limit.retry_after)},
        )
