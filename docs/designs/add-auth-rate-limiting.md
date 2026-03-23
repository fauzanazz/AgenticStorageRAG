# Add Rate Limiting on Auth Endpoints and Registration Toggle

## Context

Security audit found that auth endpoints (`/auth/login`, `/auth/register`, `/auth/refresh`) have zero rate limiting. An attacker can brute-force passwords, create unlimited accounts, or abuse the refresh endpoint. Additionally, registration is wide open — anyone can create an account and consume LLM API credits.

## Requirements

- Add per-IP rate limiting to `/auth/login` (5 requests/minute)
- Add per-IP rate limiting to `/auth/register` (3 requests/hour)
- Add per-IP rate limiting to `/auth/refresh` (10 requests/minute)
- Add a `REGISTRATION_ENABLED` config setting (defaults to `true` for dev, must be explicitly set)
- When registration is disabled, `POST /auth/register` returns 403
- Rate limit state stored in Redis (already available as a dependency)
- Return standard `429 Too Many Requests` with `Retry-After` header
- All existing tests must continue to pass

## Implementation

### 1. Add config setting

**File:** `backend/app/config.py`

Add to the `Settings` class, in the `# --- Auth ---` section:

```python
# --- Auth ---
registration_enabled: bool = True  # Set to false to disable open registration
```

### 2. Create rate limiting middleware

**File:** `backend/app/infra/rate_limiter.py` (NEW)

```python
"""Redis-backed rate limiter for API endpoints.

Uses a sliding window counter pattern stored in Redis.
Each rate limit is defined as (max_requests, window_seconds).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

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
    """Extract client IP, respecting X-Forwarded-For behind reverse proxy."""
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
```

### 3. Apply rate limits to auth router

**File:** `backend/app/domain/auth/router.py`

Add imports at top:
```python
from fastapi import Request
from app.config import get_settings
from app.infra.rate_limiter import (
    LOGIN_LIMIT,
    REGISTER_LIMIT,
    REFRESH_LIMIT,
    check_rate_limit,
)
```

Update the three endpoint functions to call `check_rate_limit` as the first line:

**`register` function:**
```python
@router.post("/register", ...)
async def register(
    data: RegisterRequest,
    request: Request,  # ← ADD
    auth_service: AuthServiceDep,
) -> AuthResponse:
    settings = get_settings()
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled",
        )
    await check_rate_limit(request, REGISTER_LIMIT, "rl:register")
    try:
        return await auth_service.register(data)
    # ... rest unchanged
```

**`login` function:**
```python
@router.post("/login", ...)
async def login(
    data: LoginRequest,
    request: Request,  # ← ADD
    auth_service: AuthServiceDep,
) -> AuthResponse:
    await check_rate_limit(request, LOGIN_LIMIT, "rl:login")
    try:
        return await auth_service.login(data)
    # ... rest unchanged
```

**`refresh_token` function:**
```python
@router.post("/refresh", ...)
async def refresh_token(
    data: RefreshRequest,
    request: Request,  # ← ADD
    auth_service: AuthServiceDep,
) -> TokenResponse:
    await check_rate_limit(request, REFRESH_LIMIT, "rl:refresh")
    try:
        return await auth_service.refresh_tokens(data.refresh_token)
    # ... rest unchanged
```

### 4. Add env var to `.env.example`

**File:** `.env.example`

Add under the `# --- Auth ---` section:
```env
# Set to false to disable open user registration (invite-only mode)
REGISTRATION_ENABLED=true
```

## Testing Strategy

**Run:** `cd backend && uv run pytest` — all existing tests must pass.

**New test file:** `backend/app/infra/tests/test_rate_limiter.py`

```
- test_allows_requests_under_limit — make 4 requests with LOGIN_LIMIT(5/60s), all pass
- test_blocks_after_limit_exceeded — make 6 requests with LOGIN_LIMIT(5/60s), 6th gets 429
- test_returns_retry_after_header — verify 429 response has Retry-After header
- test_fails_open_when_redis_unavailable — mock Redis error, request passes through
- test_different_ips_have_separate_limits — two IPs each get their own window
```

**New test in:** `backend/app/domain/auth/tests/test_router.py`
```
- test_register_disabled_returns_403 — set registration_enabled=False, POST /register returns 403
```

## Out of Scope

- Account lockout after N failed attempts (future enhancement)
- CAPTCHA integration
- IP allowlisting / blocklisting
- Per-user rate limiting (only per-IP for now)
