"""Tests for Google OAuth provider."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, UTC

from app.domain.auth.oauth.google import GoogleOAuthProvider
from app.domain.auth.exceptions import OAuthError


class TestGoogleOAuthProvider:
    def setup_method(self):
        self.provider = GoogleOAuthProvider()

    def test_provider_name(self):
        assert self.provider.provider_name == "google"

    @patch("app.domain.auth.oauth.google.get_settings")
    def test_get_authorization_url(self, mock_settings):
        mock_settings.return_value = MagicMock(
            google_client_id="test-client-id",
            google_client_secret="test-secret",
        )
        url = self.provider.get_authorization_url(
            state="test-state",
            redirect_uri="http://localhost:8000/callback",
        )
        assert "accounts.google.com" in url
        assert "test-client-id" in url
        assert "test-state" in url
        assert "callback" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        assert "drive.readonly" in url

    @patch("app.domain.auth.oauth.google.get_settings")
    def test_get_authorization_url_missing_client_id(self, mock_settings):
        mock_settings.return_value = MagicMock(google_client_id="")
        with pytest.raises(OAuthError, match="GOOGLE_CLIENT_ID"):
            self.provider.get_authorization_url(
                state="test", redirect_uri="http://localhost/cb"
            )

    @pytest.mark.asyncio
    @patch("app.domain.auth.oauth.google.get_settings")
    @patch("app.domain.auth.oauth.google.httpx.AsyncClient")
    async def test_exchange_code_success(self, mock_client_cls, mock_settings):
        mock_settings.return_value = MagicMock(
            google_client_id="test-id",
            google_client_secret="test-secret",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "google-access-token",
            "refresh_token": "google-refresh-token",
            "expires_in": 3600,
            "scope": "openid email profile",
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        tokens = await self.provider.exchange_code("auth-code", "http://localhost/cb")

        assert tokens.access_token == "google-access-token"
        assert tokens.refresh_token == "google-refresh-token"
        assert tokens.token_expiry is not None
        assert tokens.scopes == ["openid", "email", "profile"]

    @pytest.mark.asyncio
    @patch("app.domain.auth.oauth.google.get_settings")
    @patch("app.domain.auth.oauth.google.httpx.AsyncClient")
    async def test_exchange_code_failure(self, mock_client_cls, mock_settings):
        mock_settings.return_value = MagicMock(
            google_client_id="test-id",
            google_client_secret="test-secret",
        )
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Code expired",
        }
        mock_response.text = "Code expired"
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(OAuthError, match="Token exchange failed"):
            await self.provider.exchange_code("bad-code", "http://localhost/cb")

    @pytest.mark.asyncio
    @patch("app.domain.auth.oauth.google.httpx.AsyncClient")
    async def test_get_user_info_success(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "google-user-123",
            "email": "test@gmail.com",
            "name": "Test User",
            "picture": "https://lh3.google.com/photo.jpg",
        }
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        info = await self.provider.get_user_info("valid-token")

        assert info.email == "test@gmail.com"
        assert info.full_name == "Test User"
        assert info.provider_user_id == "google-user-123"
        assert info.picture_url == "https://lh3.google.com/photo.jpg"

    @pytest.mark.asyncio
    @patch("app.domain.auth.oauth.google.httpx.AsyncClient")
    async def test_get_user_info_no_email(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "google-user-123",
            "name": "No Email User",
        }
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(OAuthError, match="no email"):
            await self.provider.get_user_info("valid-token")

    @pytest.mark.asyncio
    @patch("app.domain.auth.oauth.google.httpx.AsyncClient")
    async def test_get_user_info_http_error(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(OAuthError, match="Failed to fetch user info"):
            await self.provider.get_user_info("expired-token")
