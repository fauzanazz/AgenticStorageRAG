"""Tests for middleware."""

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from app.infra.middleware import RequestLoggingMiddleware


class TestRequestLoggingMiddleware:
    """Tests for request logging middleware."""

    @pytest.mark.asyncio
    async def test_middleware_logs_and_passes_through(self) -> None:
        """Middleware should not alter the response, just log timing."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/test")
        async def test_endpoint() -> dict:
            return {"ok": True}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_streaming_response_not_blocked(self) -> None:
        """SSE streaming responses must pass through without buffering.

        BaseHTTPMiddleware would buffer or deadlock here; the pure ASGI
        middleware must let chunks flow through immediately.
        """
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        async def _sse_generator():
            for i in range(3):
                yield f"event: token\ndata: chunk-{i}\n\n"

        @app.get("/stream")
        async def stream_endpoint() -> StreamingResponse:
            return StreamingResponse(
                _sse_generator(),
                media_type="text/event-stream",
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/stream")

        assert response.status_code == 200
        assert "chunk-0" in response.text
        assert "chunk-2" in response.text
