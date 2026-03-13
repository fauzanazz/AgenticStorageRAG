"""Tests for middleware."""

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

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
