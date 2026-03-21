"""Tests for JWT token service."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.domain.auth.exceptions import InvalidTokenError
from app.domain.auth.token import TokenService


class TestTokenServiceCreate:
    """Tests for token creation."""

    @patch("app.domain.auth.token.get_settings")
    def test_create_access_token(self, mock_get_settings: MagicMock) -> None:
        """create_access_token should return a JWT string."""
        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30
        mock_settings.jwt_refresh_token_expire_days = 7
        mock_get_settings.return_value = mock_settings

        service = TokenService()
        user_id = uuid.uuid4()
        token = service.create_access_token(user_id)

        assert isinstance(token, str)
        assert len(token) > 0

    @patch("app.domain.auth.token.get_settings")
    def test_create_refresh_token(self, mock_get_settings: MagicMock) -> None:
        """create_refresh_token should return a JWT string."""
        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30
        mock_settings.jwt_refresh_token_expire_days = 7
        mock_get_settings.return_value = mock_settings

        service = TokenService()
        user_id = uuid.uuid4()
        token = service.create_refresh_token(user_id)

        assert isinstance(token, str)
        assert len(token) > 0

    @patch("app.domain.auth.token.get_settings")
    def test_access_and_refresh_tokens_are_different(self, mock_get_settings: MagicMock) -> None:
        """Access and refresh tokens should have different content."""
        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30
        mock_settings.jwt_refresh_token_expire_days = 7
        mock_get_settings.return_value = mock_settings

        service = TokenService()
        user_id = uuid.uuid4()
        access = service.create_access_token(user_id)
        refresh = service.create_refresh_token(user_id)

        assert access != refresh


class TestTokenServiceVerify:
    """Tests for token verification."""

    @patch("app.domain.auth.token.get_settings")
    def test_verify_valid_access_token(self, mock_get_settings: MagicMock) -> None:
        """verify_token should decode a valid access token."""
        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30
        mock_settings.jwt_refresh_token_expire_days = 7
        mock_get_settings.return_value = mock_settings

        service = TokenService()
        user_id = uuid.uuid4()
        token = service.create_access_token(user_id)

        payload = service.verify_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"

    @patch("app.domain.auth.token.get_settings")
    def test_verify_valid_refresh_token(self, mock_get_settings: MagicMock) -> None:
        """verify_token should decode a valid refresh token."""
        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30
        mock_settings.jwt_refresh_token_expire_days = 7
        mock_get_settings.return_value = mock_settings

        service = TokenService()
        user_id = uuid.uuid4()
        token = service.create_refresh_token(user_id)

        payload = service.verify_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"

    @patch("app.domain.auth.token.get_settings")
    def test_verify_invalid_token_raises(self, mock_get_settings: MagicMock) -> None:
        """verify_token should raise InvalidTokenError for garbage input."""
        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30
        mock_settings.jwt_refresh_token_expire_days = 7
        mock_get_settings.return_value = mock_settings

        service = TokenService()

        with pytest.raises(InvalidTokenError):
            service.verify_token("not.a.valid.token")

    @patch("app.domain.auth.token.get_settings")
    def test_verify_wrong_secret_raises(self, mock_get_settings: MagicMock) -> None:
        """verify_token should raise for tokens signed with different secret."""
        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "secret-1"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30
        mock_settings.jwt_refresh_token_expire_days = 7
        mock_get_settings.return_value = mock_settings

        service1 = TokenService()
        user_id = uuid.uuid4()
        token = service1.create_access_token(user_id)

        # Create a service with different secret
        mock_settings.jwt_secret_key = "secret-2"
        service2 = TokenService()

        with pytest.raises(InvalidTokenError):
            service2.verify_token(token)


class TestTokenServiceExpiry:
    """Tests for token expiry metadata."""

    @patch("app.domain.auth.token.get_settings")
    def test_access_expire_seconds(self, mock_get_settings: MagicMock) -> None:
        """access_expire_seconds should return minutes * 60."""
        mock_settings = MagicMock()
        mock_settings.jwt_secret_key = "test-secret"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30
        mock_settings.jwt_refresh_token_expire_days = 7
        mock_get_settings.return_value = mock_settings

        service = TokenService()

        assert service.access_expire_seconds == 1800
