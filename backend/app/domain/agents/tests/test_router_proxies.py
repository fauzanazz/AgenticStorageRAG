"""Tests for tool proxy endpoint body validation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db, get_user_model_settings
from app.domain.auth.models import User
from app.main import app


@pytest.fixture
def mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.is_admin = False
    return user


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(mock_user: User, mock_db: AsyncMock) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_user_model_settings] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestFetchDocumentProxy:
    """Tests for POST /chat/tools/fetch-document."""

    def test_rejects_invalid_body(self, client: TestClient) -> None:
        response = client.post("/api/v1/chat/tools/fetch-document", json={"bad_field": "x"})
        assert response.status_code == 422

    def test_rejects_empty_body(self, client: TestClient) -> None:
        response = client.post("/api/v1/chat/tools/fetch-document", json={})
        assert response.status_code == 422


class TestGenerateDocumentProxy:
    """Tests for POST /chat/tools/generate-document."""

    def test_rejects_missing_title(self, client: TestClient) -> None:
        response = client.post("/api/v1/chat/tools/generate-document", json={})
        assert response.status_code == 422

    def test_rejects_invalid_format(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/chat/tools/generate-document",
            json={"title": "Test", "instructions": "Do stuff", "format": "evil"},
        )
        assert response.status_code == 422


class TestEnrichCitationsProxy:
    """Tests for POST /chat/tools/enrich-citations."""

    def test_accepts_empty_citations(self, client: TestClient) -> None:
        response = client.post("/api/v1/chat/tools/enrich-citations", json={"citations": []})
        assert response.status_code == 200
        assert response.json() == {"citations": []}

    def test_rejects_invalid_body(self, client: TestClient) -> None:
        response = client.post("/api/v1/chat/tools/enrich-citations", json="not-a-dict")
        assert response.status_code == 422
