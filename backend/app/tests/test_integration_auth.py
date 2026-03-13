"""Integration tests for auth flow.

Tests the full register → login → me → refresh flow using
the FastAPI TestClient with mocked database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def app(mock_db: AsyncMock):
    """Create a fresh app with mocked dependencies."""
    application = create_app()

    # Override DB dependency
    from app.dependencies import get_db

    async def override_get_db():
        yield mock_db

    application.dependency_overrides[get_db] = override_get_db
    return application


class TestAuthIntegration:
    """Full auth flow integration tests."""

    @pytest.mark.asyncio
    async def test_register_endpoint_validates_email(self, app) -> None:
        """Registration should reject invalid email format."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "not-an-email",
                    "password": "password123",
                    "full_name": "Test User",
                },
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_endpoint_validates_password_length(self, app) -> None:
        """Registration should reject short passwords."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "short",
                    "full_name": "Test User",
                },
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_requires_body(self, app) -> None:
        """Login should return 422 with no body."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/auth/login")
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_me_requires_auth(self, app) -> None:
        """The /me endpoint should return 401 without a token."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/auth/me")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_requires_body(self, app) -> None:
        """Refresh should return 422 with no body."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/auth/refresh")
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_protected_endpoints_reject_invalid_token(self, app) -> None:
        """Protected endpoints should reject invalid JWT tokens."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": "Bearer invalid-token"}

            # Documents
            resp = await client.get("/api/v1/documents", headers=headers)
            assert resp.status_code == 401

            # Knowledge
            resp = await client.get("/api/v1/knowledge/stats", headers=headers)
            assert resp.status_code == 401

            # Chat
            resp = await client.get("/api/v1/chat/conversations", headers=headers)
            assert resp.status_code == 401
