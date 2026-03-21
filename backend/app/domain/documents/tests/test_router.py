"""Tests for document router."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user_id, get_db, get_redis, get_storage
from app.main import app


@pytest.fixture
def mock_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_redis() -> AsyncMock:
    mock = AsyncMock()
    mock.enqueue = AsyncMock()
    return mock


@pytest.fixture
def mock_storage() -> AsyncMock:
    mock = AsyncMock()
    mock.upload_file = AsyncMock(return_value={"path": "test"})
    return mock


@pytest.fixture
def client(
    mock_user_id: uuid.UUID, mock_db: AsyncMock, mock_redis: AsyncMock, mock_storage: AsyncMock
) -> TestClient:
    app.dependency_overrides[get_current_user_id] = lambda: mock_user_id
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_storage] = lambda: mock_storage
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestDocumentUploadEndpoint:
    """Tests for POST /documents."""

    def test_upload_no_file(self, client: TestClient) -> None:
        response = client.post("/api/v1/documents")
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_upload_unsupported_type(self, client: TestClient) -> None:
        import io

        response = client.post(
            "/api/v1/documents",
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert response.status_code == 415
        data = response.json()
        assert "detail" in data


class TestDocumentListEndpoint:
    """Tests for GET /documents."""

    def test_list_documents(self, client: TestClient, mock_db: AsyncMock) -> None:
        # Mock empty list result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        response = client.get("/api/v1/documents")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestDocumentGetEndpoint:
    """Tests for GET /documents/{id}."""

    def test_get_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get(f"/api/v1/documents/{uuid.uuid4()}")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestDocumentDeleteEndpoint:
    """Tests for DELETE /documents/{id}."""

    def test_delete_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.delete(f"/api/v1/documents/{uuid.uuid4()}")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
