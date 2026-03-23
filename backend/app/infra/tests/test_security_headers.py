"""Tests for security headers middleware."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.infra.security_headers import SecurityHeadersMiddleware

_DEV_SETTINGS = Settings(environment="development")
_PROD_SETTINGS = Settings(
    environment="production",
    jwt_secret_key="prod-secret-key-not-default",
    encryption_key="different-encryption-key",
)


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with SecurityHeadersMiddleware."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint() -> dict:
        return {"ok": True}

    return app


class TestSecurityHeadersMiddleware:
    """Tests for security headers middleware."""

    @pytest.mark.asyncio
    async def test_response_includes_x_frame_options(self) -> None:
        app = _make_app()
        transport = ASGITransport(app=app)
        with patch("app.infra.security_headers.get_settings", return_value=_DEV_SETTINGS):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test")
        assert response.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_response_includes_x_content_type_options(self) -> None:
        app = _make_app()
        transport = ASGITransport(app=app)
        with patch("app.infra.security_headers.get_settings", return_value=_DEV_SETTINGS):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test")
        assert response.headers["x-content-type-options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_response_includes_referrer_policy(self) -> None:
        app = _make_app()
        transport = ASGITransport(app=app)
        with patch("app.infra.security_headers.get_settings", return_value=_DEV_SETTINGS):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test")
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_response_includes_permissions_policy(self) -> None:
        app = _make_app()
        transport = ASGITransport(app=app)
        with patch("app.infra.security_headers.get_settings", return_value=_DEV_SETTINGS):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test")
        assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"

    @pytest.mark.asyncio
    async def test_response_includes_x_xss_protection(self) -> None:
        app = _make_app()
        transport = ASGITransport(app=app)
        with patch("app.infra.security_headers.get_settings", return_value=_DEV_SETTINGS):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test")
        assert response.headers["x-xss-protection"] == "0"

    @pytest.mark.asyncio
    async def test_hsts_only_in_production(self) -> None:
        app = _make_app()
        transport = ASGITransport(app=app)
        with patch("app.infra.security_headers.get_settings", return_value=_DEV_SETTINGS):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test")
        assert "strict-transport-security" not in response.headers

    @pytest.mark.asyncio
    async def test_hsts_present_in_production(self) -> None:
        app = _make_app()
        transport = ASGITransport(app=app)
        with patch("app.infra.security_headers.get_settings", return_value=_PROD_SETTINGS):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test")
        assert (
            response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
        )
        assert "content-security-policy" in response.headers

    @pytest.mark.asyncio
    async def test_csp_not_in_development(self) -> None:
        app = _make_app()
        transport = ASGITransport(app=app)
        with patch("app.infra.security_headers.get_settings", return_value=_DEV_SETTINGS):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/test")
        assert "content-security-policy" not in response.headers
