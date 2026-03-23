"""Tests for application configuration validation."""

import pytest

from app.config import Settings


class TestConfigValidation:
    """Tests for Settings model validators."""

    def test_rejects_same_encryption_and_jwt_key(self) -> None:
        with pytest.raises(ValueError, match="ENCRYPTION_KEY must be different from JWT_SECRET_KEY"):
            Settings(
                environment="production",
                jwt_secret_key="my-secret-key",
                encryption_key="my-secret-key",
            )

    def test_accepts_different_encryption_and_jwt_key(self) -> None:
        settings = Settings(
            environment="production",
            jwt_secret_key="my-jwt-secret",
            encryption_key="my-encryption-key",
        )
        assert settings.encryption_key != settings.jwt_secret_key

    def test_rejects_missing_encryption_key_in_production(self) -> None:
        with pytest.raises(ValueError, match="ENCRYPTION_KEY is required"):
            Settings(
                environment="production",
                jwt_secret_key="my-jwt-secret",
                encryption_key="",
            )

    def test_rejects_default_jwt_secret_in_production(self) -> None:
        with pytest.raises(ValueError, match="JWT_SECRET_KEY must be changed"):
            Settings(
                environment="production",
                jwt_secret_key="change-me-in-production",
                encryption_key="some-key",
            )

    def test_allows_defaults_in_development(self) -> None:
        settings = Settings(
            environment="development",
            jwt_secret_key="change-me-in-production",
        )
        assert settings.jwt_secret_key == "change-me-in-production"
