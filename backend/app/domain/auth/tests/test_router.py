"""Tests for auth router (API endpoints)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_db
from app.domain.auth.exceptions import (
    EmailAlreadyExistsError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.domain.auth.router import _get_auth_service, router
from app.domain.auth.schemas import AuthResponse, TokenResponse, UserResponse
from app.infra.rate_limiter import LOGIN_LIMIT, REFRESH_LIMIT, REGISTER_LIMIT


@pytest.fixture(autouse=True)
def mock_rate_limiter():
    """Disable rate limiting for router tests; yields the mock for assertion."""
    with patch("app.domain.auth.router.check_rate_limit", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture(autouse=True)
def _enable_registration():
    """Enable registration by default (registration_enabled defaults to False)."""
    with patch("app.domain.auth.router.get_settings") as mock_settings:
        mock_settings.return_value.registration_enabled = True
        yield


def _create_test_app(mock_service: AsyncMock | None = None) -> FastAPI:
    """Create a minimal FastAPI app with the auth router and overridden deps."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override the DB dependency to avoid needing a real database
    async def mock_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = mock_db

    # Override the auth service if provided
    if mock_service is not None:
        app.dependency_overrides[_get_auth_service] = lambda: mock_service

    return app


def _make_auth_response(
    email: str = "test@example.com",
    full_name: str = "Test User",
) -> AuthResponse:
    """Create a mock AuthResponse for testing."""
    return AuthResponse(
        user=UserResponse(
            id=uuid.uuid4(),
            email=email,
            full_name=full_name,
            is_active=True,
            is_admin=False,
            created_at=datetime.now(UTC),
        ),
        tokens=TokenResponse(
            access_token="mock_access",
            refresh_token="mock_refresh",
            expires_in=1800,
        ),
    )


class TestRegisterEndpoint:
    """Tests for POST /auth/register."""

    @pytest.mark.asyncio
    async def test_register_success(self) -> None:
        """Should return 201 with auth response on success."""
        mock_service = AsyncMock()
        mock_service.register.return_value = _make_auth_response()

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "securepassword",
                    "full_name": "New User",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert "user" in data
        assert "tokens" in data
        assert data["tokens"]["access_token"] == "mock_access"
        assert data["tokens"]["refresh_token"] == "mock_refresh"
        assert data["tokens"]["expires_in"] == 1800
        assert data["user"]["email"] == "test@example.com"
        assert data["user"]["full_name"] == "Test User"
        assert data["user"]["is_active"] is True

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self) -> None:
        """Should return 409 for duplicate email."""
        mock_service = AsyncMock()
        mock_service.register.side_effect = EmailAlreadyExistsError("taken@example.com")

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "taken@example.com",
                    "password": "password123",
                    "full_name": "Dup User",
                },
            )

        assert response.status_code == 409
        data = response.json()
        assert "detail" in data
        assert "taken@example.com" in data["detail"]

    @pytest.mark.asyncio
    async def test_register_short_password_returns_422(self) -> None:
        """Should return 422 for password shorter than 8 chars."""
        app = _create_test_app(AsyncMock())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "short",
                    "full_name": "User",
                },
            )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data  # FastAPI validation error detail

    @pytest.mark.asyncio
    async def test_register_invalid_email_returns_422(self) -> None:
        """Should return 422 for invalid email format."""
        app = _create_test_app(AsyncMock())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "not-an-email",
                    "password": "password123",
                    "full_name": "User",
                },
            )

        assert response.status_code == 422


class TestLoginEndpoint:
    """Tests for POST /auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self) -> None:
        """Should return 200 with auth response on success."""
        mock_service = AsyncMock()
        mock_service.login.return_value = _make_auth_response()

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@example.com", "password": "password123"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["tokens"]["access_token"] == "mock_access"
        assert data["tokens"]["refresh_token"] == "mock_refresh"
        assert "user" in data
        assert data["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials_returns_401(self) -> None:
        """Should return 401 for wrong email/password."""
        mock_service = AsyncMock()
        mock_service.login.side_effect = InvalidCredentialsError()

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "wrong@example.com", "password": "wrong"},
            )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_login_inactive_user_returns_403(self) -> None:
        """Should return 403 for inactive user."""
        mock_service = AsyncMock()
        mock_service.login.side_effect = InactiveUserError()

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "inactive@example.com", "password": "pass"},
            )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data


class TestRefreshEndpoint:
    """Tests for POST /auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_success(self) -> None:
        """Should return 200 with new tokens."""
        mock_service = AsyncMock()
        mock_service.refresh_tokens.return_value = TokenResponse(
            access_token="new_access",
            refresh_token="new_refresh",
            expires_in=1800,
        )

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "valid_refresh"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new_access"
        assert data["refresh_token"] == "new_refresh"
        assert data["expires_in"] == 1800

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_returns_401(self) -> None:
        """Should return 401 for invalid refresh token."""
        mock_service = AsyncMock()
        mock_service.refresh_tokens.side_effect = InvalidTokenError()

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "invalid_token"},
            )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data


class TestMeEndpoint:
    """Tests for GET /auth/me."""

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self) -> None:
        """Should return 401 when no Authorization header is provided."""
        app = _create_test_app(AsyncMock())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401


class TestRegistrationToggle:
    """Tests for registration enabled/disabled toggle."""

    @pytest.mark.asyncio
    async def test_register_disabled_returns_403(self) -> None:
        """Should return 403 when registration_enabled is False."""
        mock_service = AsyncMock()
        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)

        with patch("app.domain.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.registration_enabled = False
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": "new@example.com",
                        "password": "securepassword",
                        "full_name": "New User",
                    },
                )

        assert response.status_code == 403
        data = response.json()
        assert "disabled" in data["detail"].lower()
        mock_service.register.assert_not_called()


class TestRateLimiting:
    """Tests that rate limiting is wired correctly into each endpoint."""

    @pytest.mark.asyncio
    async def test_login_calls_rate_limiter(self, mock_rate_limiter: AsyncMock) -> None:
        """Login endpoint must invoke check_rate_limit with LOGIN_LIMIT."""
        mock_service = AsyncMock()
        mock_service.login.return_value = _make_auth_response()

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/auth/login",
                json={"email": "test@example.com", "password": "password123"},
            )

        mock_rate_limiter.assert_called_once()
        _, limit, key_prefix = mock_rate_limiter.call_args[0]
        assert limit == LOGIN_LIMIT
        assert key_prefix == "rl:login"

    @pytest.mark.asyncio
    async def test_register_calls_rate_limiter(self, mock_rate_limiter: AsyncMock) -> None:
        """Register endpoint must invoke check_rate_limit with REGISTER_LIMIT."""
        mock_service = AsyncMock()
        mock_service.register.return_value = _make_auth_response()

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "securepassword",
                    "full_name": "New User",
                },
            )

        mock_rate_limiter.assert_called_once()
        _, limit, key_prefix = mock_rate_limiter.call_args[0]
        assert limit == REGISTER_LIMIT
        assert key_prefix == "rl:register"

    @pytest.mark.asyncio
    async def test_refresh_calls_rate_limiter(self, mock_rate_limiter: AsyncMock) -> None:
        """Refresh endpoint must invoke check_rate_limit with REFRESH_LIMIT."""
        mock_service = AsyncMock()
        mock_service.refresh_tokens.return_value = TokenResponse(
            access_token="new_access",
            refresh_token="new_refresh",
            expires_in=1800,
        )

        app = _create_test_app(mock_service)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "valid_refresh"},
            )

        mock_rate_limiter.assert_called_once()
        _, limit, key_prefix = mock_rate_limiter.call_args[0]
        assert limit == REFRESH_LIMIT
        assert key_prefix == "rl:refresh"
