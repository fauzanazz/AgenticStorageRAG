"""Tests for ingestion router (admin-only endpoints)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db, get_storage
from app.main import create_app


@pytest.fixture
def admin_user() -> MagicMock:
    """Create a mock admin user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


@pytest.fixture
def regular_user() -> MagicMock:
    """Create a mock regular (non-admin) user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user@test.com"
    user.is_admin = False
    user.is_active = True
    return user


@pytest.fixture
def client(admin_user: MagicMock) -> TestClient:
    """Create test client with admin user dependency override."""
    app = create_app()

    mock_db = AsyncMock()
    mock_storage = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_storage] = lambda: mock_storage

    return TestClient(app)


class TestAdminAccess:
    """Test admin-only access control."""

    def test_non_admin_forbidden(self, regular_user: MagicMock) -> None:
        """Non-admin users should get 403."""
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: regular_user
        app.dependency_overrides[get_db] = lambda: AsyncMock()
        app.dependency_overrides[get_storage] = lambda: AsyncMock()

        client = TestClient(app)
        response = client.get("/api/v1/admin/ingestion/jobs")
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_admin_allowed(self, client: TestClient) -> None:
        """Admin users should be allowed to access ingestion endpoints."""
        with patch("app.domain.ingestion.service.IngestionService.list_jobs") as mock_list:
            mock_list.return_value = MagicMock(
                items=[],
                total=0,
                model_dump=lambda **kwargs: {"items": [], "total": 0},
            )
            response = client.get("/api/v1/admin/ingestion/jobs")
            assert response.status_code == 200


class TestListJobs:
    """Test GET /admin/ingestion/jobs."""

    def test_list_empty(self, client: TestClient) -> None:
        """Should return empty list."""
        with patch("app.domain.ingestion.service.IngestionService.list_jobs") as mock_list:
            mock_list.return_value = MagicMock(
                items=[],
                total=0,
                model_dump=lambda **kwargs: {"items": [], "total": 0},
            )
            response = client.get("/api/v1/admin/ingestion/jobs")
            assert response.status_code == 200


class TestGetJob:
    """Test GET /admin/ingestion/jobs/{job_id}."""

    def test_not_found(self, client: TestClient) -> None:
        """Should return 404 for non-existent job."""
        from app.domain.ingestion.exceptions import IngestionJobNotFoundError

        with patch("app.domain.ingestion.service.IngestionService.get_job") as mock_get:
            mock_get.side_effect = IngestionJobNotFoundError("abc")
            response = client.get(f"/api/v1/admin/ingestion/jobs/{uuid.uuid4()}")
            assert response.status_code == 404
            data = response.json()
            assert "detail" in data
