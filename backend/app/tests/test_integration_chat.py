"""Integration tests for chat/agent flow.

Tests conversation management and chat endpoints using
the FastAPI TestClient with mocked dependencies.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.auth.token import TokenService
from app.main import create_app


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_token(user_id: uuid.UUID) -> str:
    token_service = TokenService()
    return token_service.create_access_token(user_id)


@pytest.fixture
def mock_db(user_id: uuid.UUID) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()

    # Default: return None for get() calls (no existing record)
    db.get.return_value = None

    return db


@pytest.fixture
def mock_user(user_id: uuid.UUID) -> MagicMock:
    """Create a mock User object for auth."""
    user = MagicMock()
    user.id = user_id
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.is_active = True
    user.is_admin = False
    return user


@pytest.fixture
def app(mock_db: AsyncMock, mock_user: MagicMock):
    application = create_app()

    from app.dependencies import get_current_user, get_db

    async def override_get_db():
        yield mock_db

    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_current_user] = lambda: mock_user
    return application


class TestChatIntegration:
    """Integration tests for chat endpoints."""

    @pytest.mark.asyncio
    async def test_list_conversations_empty(
        self, app, auth_token: str, mock_db: AsyncMock
    ) -> None:
        """Should return empty list for new user."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/chat/conversations",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 200
            assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_nonexistent_conversation(
        self, app, auth_token: str, mock_db: AsyncMock
    ) -> None:
        """Getting a nonexistent conversation should return 404."""
        mock_db.get.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/chat/conversations/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_conversation(
        self, app, auth_token: str, mock_db: AsyncMock
    ) -> None:
        """Deleting a nonexistent conversation should return 404."""
        mock_db.get.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.delete(
                f"/api/v1/chat/conversations/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stream_requires_message(
        self, app, auth_token: str
    ) -> None:
        """Stream endpoint should require message field."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/chat/stream",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={},
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_message_requires_content(
        self, app, auth_token: str
    ) -> None:
        """Message endpoint should require message field."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/chat/message",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={},
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_conversations_limit_validation(
        self, app, auth_token: str
    ) -> None:
        """Limit must be within valid range."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": f"Bearer {auth_token}"}

            # limit < 1
            resp = await client.get(
                "/api/v1/chat/conversations?limit=0", headers=headers
            )
            assert resp.status_code == 422

            # limit > 100
            resp = await client.get(
                "/api/v1/chat/conversations?limit=200", headers=headers
            )
            assert resp.status_code == 422
