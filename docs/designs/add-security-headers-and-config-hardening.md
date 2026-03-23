# Add Security Headers Middleware and Config Hardening

## Context

Security audit found the application serves no security headers (CSP, HSTS, X-Frame-Options, etc.) on either backend or frontend. Additionally, the encryption key falls back to the JWT secret in development (single point of failure), the global exception handler hides errors even in debug mode, and the backend Dockerfile has no `.dockerignore` (risks copying `.env` into images).

## Requirements

- Add security headers middleware to FastAPI backend
- Add security headers config to Next.js frontend
- Require `ENCRYPTION_KEY` to be different from `JWT_SECRET_KEY` when both are set
- Show exception details in error responses when `DEBUG=true`
- Add a backend `.dockerignore` that excludes `.env`, `.venv`, `.git`, etc.
- All existing tests must continue to pass

## Implementation

### 1. Create security headers middleware

**File:** `backend/app/infra/security_headers.py` (NEW)

```python
"""Security headers middleware.

Adds standard security headers to every HTTP response.
Implemented as pure ASGI middleware (not BaseHTTPMiddleware)
to avoid SSE/streaming issues — same pattern as RequestLoggingMiddleware.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings


class SecurityHeadersMiddleware:
    """Add security headers to all HTTP responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()

        async def _send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                extra_headers: list[tuple[bytes, bytes]] = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"x-xss-protection", b"0"),  # Disable legacy XSS filter (CSP is better)
                ]

                if settings.environment == "production":
                    extra_headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                    extra_headers.append(
                        (b"content-security-policy",
                         b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'")
                    )

                existing = list(message.get("headers", []))
                existing.extend(extra_headers)
                message = {**message, "headers": existing}

            await send(message)

        await self.app(scope, receive, _send_wrapper)
```

### 2. Register middleware in app factory

**File:** `backend/app/main.py`

Add import:
```python
from app.infra.security_headers import SecurityHeadersMiddleware
```

In `create_app()`, add SecurityHeadersMiddleware BEFORE CORS (last-added = first-executed, security headers should be outermost):

```python
# Middleware (order: last added = first executed)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)  # ← ADD before CORS
app.add_middleware(
    CORSMiddleware,
    ...
)
```

### 3. Improve global exception handler for debug mode

**File:** `backend/app/main.py`

Update the global exception handler (around line 249):

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    detail = "Internal server error"
    if settings.debug:
        detail = f"{type(exc).__name__}: {exc}"
    return JSONResponse(
        status_code=500,
        content={"detail": detail},
    )
```

### 4. Add encryption key validation

**File:** `backend/app/config.py`

Extend the `_reject_weak_defaults` validator:

```python
@model_validator(mode="after")
def _reject_weak_defaults(self) -> "Settings":
    if self.environment in ("staging", "production"):
        if self.jwt_secret_key == "change-me-in-production":
            raise ValueError(
                "JWT_SECRET_KEY must be changed from its default in "
                f"{self.environment} environments"
            )
        if not self.encryption_key:
            raise ValueError(f"ENCRYPTION_KEY is required in {self.environment} environments")
        if self.encryption_key == self.jwt_secret_key:
            raise ValueError(
                "ENCRYPTION_KEY must be different from JWT_SECRET_KEY "
                "(separate key for stored secrets vs session tokens)"
            )
    return self
```

### 5. Add security headers to Next.js frontend

**File:** `frontend/next.config.ts`

```typescript
import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "X-XSS-Protection", value: "0" },
];

const nextConfig: NextConfig = {
  devIndicators: false,
  serverExternalPackages: ["@anthropic-ai/claude-agent-sdk"],
  turbopack: {},
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  webpack: (config, { dev }) => {
    if (dev) {
      config.watchOptions = {
        poll: 1000,
        aggregateTimeout: 300,
      };
    }
    return config;
  },
};

export default nextConfig;
```

### 6. Add backend `.dockerignore`

**File:** `backend/.dockerignore` (NEW)

```
.env
.env.*
!.env.example
.venv/
venv/
.git/
.mypy_cache/
.ruff_cache/
.pytest_cache/
.coverage
htmlcov/
__pycache__/
*.pyc
*.pyo
.DS_Store
```

## Testing Strategy

**Run:** `cd backend && uv run pytest` — all existing tests must pass.

**New test file:** `backend/app/infra/tests/test_security_headers.py`

```
- test_response_includes_x_frame_options — send GET /api/v1/health, assert X-Frame-Options: DENY
- test_response_includes_x_content_type_options — assert nosniff header present
- test_response_includes_referrer_policy — assert strict-origin-when-cross-origin
- test_hsts_only_in_production — mock settings.environment="development", assert no HSTS header
```

**New test in:** `backend/app/tests/test_config.py` (add to existing or create)
```
- test_rejects_same_encryption_and_jwt_key — set both to same value in production, assert ValueError
```

**Manual check:** `docker build -t test ./backend && docker run test ls -la` — verify `.env` is not present.

## Out of Scope

- Content-Security-Policy nonce generation for inline scripts
- Subresource Integrity (SRI) for CDN assets
- CORS origin validation hardening (currently using the allow-list from config)
