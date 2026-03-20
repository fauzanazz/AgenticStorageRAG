"""Tests for the health check endpoint."""

from fastapi.testclient import TestClient

from app.main import app


class TestHealthEndpoint:
    """Test suite for the /health endpoint."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = TestClient(app)

    def test_health_returns_200(self) -> None:
        """Health endpoint should return 200 with status info."""
        response = self.client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_returns_expected_fields(self) -> None:
        """Health response should contain status, version, and environment."""
        response = self.client.get("/api/v1/health")
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "version" in data
        assert "environment" in data

    def test_health_version_matches_settings(self) -> None:
        """Health version should match app settings."""
        response = self.client.get("/api/v1/health")
        data = response.json()
        assert data["version"] == "0.1.0"
