"""Integration tests for auth flow.

Tests the full register -> login -> me -> refresh flow using
the FastAPI TestClient with mocked database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.auth.models import User
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
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/login")
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_me_requires_auth(self, app) -> None:
        """The /me endpoint should return 401 without a token."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_requires_body(self, app) -> None:
        """Refresh should return 422 with no body."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/refresh")
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_protected_endpoints_reject_invalid_token(self, app) -> None:
        """Protected endpoints should reject invalid JWT tokens."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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


class TestAuthFullFlow:
    """Tests that exercise the real register -> login -> access flow.

    These tests exist because the auth contract mismatch bug
    (frontend expecting flat TokenResponse, backend returning nested
    AuthResponse) was invisible when each layer was tested in isolation.
    """

    @pytest.mark.asyncio
    async def test_register_returns_auth_response_shape(self, app, mock_db) -> None:
        """Register should return {user: {...}, tokens: {...}} -- not flat tokens."""
        # Mock: no existing user (duplicate check)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Simulate DB setting defaults on add
        def set_user_defaults(user: Any) -> None:
            user.id = uuid.uuid4()
            user.is_active = True
            user.is_admin = False
            user.created_at = datetime.now(UTC)
            user.updated_at = datetime.now(UTC)

        mock_db.add.side_effect = set_user_defaults

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "securepassword123",
                    "full_name": "New User",
                },
            )

        assert response.status_code == 201
        data = response.json()

        # Validate the EXACT shape that the frontend expects
        assert "user" in data, "Response must have 'user' key"
        assert "tokens" in data, "Response must have 'tokens' key"

        # Validate user fields
        assert data["user"]["email"] == "new@example.com"
        assert data["user"]["full_name"] == "New User"
        assert data["user"]["is_active"] is True
        assert "id" in data["user"]
        assert "created_at" in data["user"]

        # Validate token fields
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]
        assert data["tokens"]["token_type"] == "bearer"
        assert isinstance(data["tokens"]["expires_in"], int)

    @pytest.mark.asyncio
    async def test_login_returns_auth_response_shape(self, app, mock_db) -> None:
        """Login should return {user: {...}, tokens: {...}} -- not flat tokens."""
        from app.domain.auth.password import PasswordHasher

        hasher = PasswordHasher()
        hashed = hasher.hash("correct_password")

        user = MagicMock(spec=User)
        user.id = uuid.uuid4()
        user.email = "existing@example.com"
        user.full_name = "Existing User"
        user.hashed_password = hashed
        user.is_active = True
        user.is_admin = False
        user.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        user.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": "existing@example.com",
                    "password": "correct_password",
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Contract: must be {user, tokens}, NOT flat {access_token, ...}
        assert "user" in data
        assert "tokens" in data
        assert data["user"]["email"] == "existing@example.com"
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]

    @pytest.mark.asyncio
    async def test_register_token_works_on_me_endpoint(self, app, mock_db) -> None:
        """Token from register should authenticate on /auth/me."""
        # Register: no existing user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        user_id = uuid.uuid4()

        def set_user_defaults(user: Any) -> None:
            user.id = user_id
            user.is_active = True
            user.is_admin = False
            user.created_at = datetime.now(UTC)
            user.updated_at = datetime.now(UTC)

        mock_db.add.side_effect = set_user_defaults

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Step 1: Register
            reg_response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "flow@example.com",
                    "password": "securepassword123",
                    "full_name": "Flow User",
                },
            )
            assert reg_response.status_code == 201
            tokens = reg_response.json()["tokens"]
            access_token = tokens["access_token"]

            # Step 2: Use the token to access /me
            # Now mock the DB to return the user for the /me lookup
            user_mock = MagicMock(spec=User)
            user_mock.id = user_id
            user_mock.email = "flow@example.com"
            user_mock.full_name = "Flow User"
            user_mock.is_active = True
            user_mock.is_admin = False
            user_mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
            user_mock.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

            me_result = MagicMock()
            me_result.scalar_one_or_none.return_value = user_mock
            mock_db.execute.return_value = me_result

            me_response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["email"] == "flow@example.com"
        assert me_data["full_name"] == "Flow User"
