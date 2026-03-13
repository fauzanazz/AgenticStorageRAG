"""Integration tests for documents flow.

Tests document upload validation, listing, and error handling
using the FastAPI TestClient with mocked dependencies.
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
    """Generate a valid JWT for testing."""
    token_service = TokenService()
    return token_service.create_access_token(user_id)


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_storage() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_redis() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def app(mock_db: AsyncMock, mock_storage: AsyncMock, mock_redis: AsyncMock):
    """Create app with mocked dependencies."""
    application = create_app()

    from app.dependencies import get_db, get_redis, get_storage

    async def override_get_db():
        yield mock_db

    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_storage] = lambda: mock_storage
    application.dependency_overrides[get_redis] = lambda: mock_redis

    return application


class TestDocumentsIntegration:
    """Integration tests for document endpoints."""

    @pytest.mark.asyncio
    async def test_upload_rejects_no_file(self, app, auth_token: str) -> None:
        """Upload should return 422 with no file attached."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/documents",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_pagination_validation(self, app, auth_token: str) -> None:
        """Page must be >= 1, page_size must be >= 1 and <= 100."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": f"Bearer {auth_token}"}

            # page < 1
            resp = await client.get("/api/v1/documents?page=0", headers=headers)
            assert resp.status_code == 422

            # page_size > 100
            resp = await client.get(
                "/api/v1/documents?page_size=200", headers=headers
            )
            assert resp.status_code == 422

            # page_size < 1
            resp = await client.get(
                "/api/v1/documents?page_size=0", headers=headers
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_nonexistent_document(
        self, app, auth_token: str, mock_db: AsyncMock
    ) -> None:
        """Getting a nonexistent document should return 404."""
        # Make the query return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/documents/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document(
        self, app, auth_token: str, mock_db: AsyncMock
    ) -> None:
        """Deleting a nonexistent document should return 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.delete(
                f"/api/v1/documents/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 404
