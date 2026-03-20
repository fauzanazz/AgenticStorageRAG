"""Tests for OAuth login guard (Google-only users blocked from password login)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

import pytest

from app.domain.auth.exceptions import OAuthLoginRequiredError
from app.domain.auth.models import User
from app.domain.auth.schemas import LoginRequest
from app.domain.auth.service import AuthService


class TestLoginGuard:
    @pytest.mark.asyncio
    async def test_google_only_user_cannot_password_login(self):
        """A user with no password (Google OAuth only) should be blocked from password login."""
        google_user = MagicMock(spec=User)
        google_user.id = uuid.uuid4()
        google_user.email = "google@gmail.com"
        google_user.hashed_password = None  # Google-only user
        google_user.is_active = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = google_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AuthService(db=mock_db)

        with pytest.raises(OAuthLoginRequiredError, match="Google Sign-In"):
            await service.login(LoginRequest(email="google@gmail.com", password="anything"))

    @pytest.mark.asyncio
    async def test_password_user_can_still_login(self):
        """A user with a password should still be able to use password login."""
        normal_user = MagicMock(spec=User)
        normal_user.id = uuid.uuid4()
        normal_user.email = "user@example.com"
        normal_user.full_name = "Normal User"
        normal_user.hashed_password = "hashed-password"
        normal_user.is_active = True
        normal_user.is_admin = False
        normal_user.created_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = normal_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_hasher = MagicMock()
        mock_hasher.verify.return_value = True

        mock_tokens = MagicMock()
        mock_tokens.create_access_token.return_value = "access"
        mock_tokens.create_refresh_token.return_value = "refresh"
        mock_tokens.access_expire_seconds = 1800

        service = AuthService(db=mock_db, password_hasher=mock_hasher, token_service=mock_tokens)

        response = await service.login(LoginRequest(email="user@example.com", password="password"))
        assert response.tokens.access_token == "access"
