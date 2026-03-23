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
                extra_headers: list[tuple[bytes, bytes]] = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"x-xss-protection", b"0"),
                ]

                if settings.environment == "production":
                    extra_headers.append(
                        (
                            b"strict-transport-security",
                            b"max-age=31536000; includeSubDomains",
                        )
                    )
                    extra_headers.append(
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'",
                        )
                    )

                existing = list(message.get("headers", []))
                existing.extend(extra_headers)
                message = {**message, "headers": existing}

            await send(message)

        await self.app(scope, receive, _send_wrapper)
