"""Middleware configuration.

CORS, request logging, and authentication middleware.

IMPORTANT: Do NOT use Starlette's ``BaseHTTPMiddleware`` here.
``BaseHTTPMiddleware.call_next()`` pipes the response body through an
internal ``anyio.MemoryObjectStream``, which causes two problems:

1. **SSE deadlocks** – ``StreamingResponse`` generators (the ``/chat/stream``
   endpoint) can hang because the background task feeding the memory channel
   may stall or lose error context, freezing the response mid-stream.
2. **Reload freezes** – active SSE connections served through this middleware
   keep the old uvicorn worker alive during ``--reload``, blocking the new
   process from starting (the symptom: "backend freezes on file change").

The pure-ASGI approach below wraps only the ``send`` callable to capture the
HTTP status code for logging.  It never touches the response body, so
``StreamingResponse`` chunks flow directly to the client with zero overhead.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """Log all incoming HTTP requests with timing information.

    Implemented as a pure ASGI middleware (not ``BaseHTTPMiddleware``) so that
    streaming responses (SSE) pass through without buffering or deadlocks.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only instrument HTTP requests — let WebSocket / lifespan pass through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        status_code = 0

        async def _send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        await self.app(scope, receive, _send_wrapper)

        duration_ms = (time.perf_counter() - start_time) * 1000
        path = scope.get("path", "?")
        method = scope.get("method", "?")
        logger.info(
            "%s %s → %d (%.1fms)",
            method,
            path,
            status_code,
            duration_ms,
        )
