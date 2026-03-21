"""Tests for OAuth service (find-or-create, token storage)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.auth.exceptions import OAuthError
from app.domain.auth.models import OAuthAccount, User
from app.domain.auth.oauth.base import OAuthTokens, OAuthUserInfo
from app.domain.auth.oauth.service import OAuthService


def _make_user_info(
    email: str = "test@gmail.com",
    full_name: str = "Test User",
    provider_user_id: str = "google-123",
) -> OAuthUserInfo:
    return OAuthUserInfo(
        email=email,
        full_name=full_name,
        provider_user_id=provider_user_id,
    )


def _make_oauth_tokens() -> OAuthTokens:
    return OAuthTokens(
        access_token="access-tok",
        refresh_token="refresh-tok",
        token_expiry=datetime.now(UTC) + timedelta(hours=1),
        scopes=["openid", "email", "profile", "https://www.googleapis.com/auth/drive.readonly"],
    )


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.client = AsyncMock()
    redis.client.set = AsyncMock()
    redis.client.get = AsyncMock(return_value="google")
    redis.client.delete = AsyncMock()
    return redis


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.provider_name = "google"
    provider.get_authorization_url = MagicMock(return_value="https://accounts.google.com/auth?...")
    provider.exchange_code = AsyncMock(return_value=_make_oauth_tokens())
    provider.get_user_info = AsyncMock(return_value=_make_user_info())
    return provider


@pytest.fixture
def mock_token_service():
    svc = MagicMock()
    svc.create_access_token.return_value = "jwt-access"
    svc.create_refresh_token.return_value = "jwt-refresh"
    svc.access_expire_seconds = 1800
    return svc


class TestOAuthServiceAuthorize:
    @pytest.mark.asyncio
    async def test_get_authorization_url_stores_state(
        self, mock_db, mock_redis, mock_provider, mock_token_service
    ):
        service = OAuthService(
            db=mock_db,
            redis=mock_redis,
            provider=mock_provider,
            token_service=mock_token_service,
        )
        url = await service.get_authorization_url("http://localhost/cb")

        assert url == "https://accounts.google.com/auth?..."
        mock_redis.client.set.assert_called_once()
        call_args = mock_redis.client.set.call_args
        assert call_args.kwargs.get("ex") == 300 or call_args[1].get("ex") == 300


class TestOAuthServiceCallback:
    @pytest.mark.asyncio
    @patch("app.domain.auth.oauth.service.encrypt_value", return_value="encrypted")
    async def test_callback_new_user(
        self, mock_encrypt, mock_db, mock_redis, mock_provider, mock_token_service
    ):
        # Create a mock user that Pydantic can validate
        new_user = MagicMock()
        new_user.id = uuid.uuid4()
        new_user.email = "test@gmail.com"
        new_user.full_name = "Test User"
        new_user.is_active = True
        new_user.is_admin = False
        new_user.created_at = datetime.now(UTC)

        service = OAuthService(
            db=mock_db,
            redis=mock_redis,
            provider=mock_provider,
            token_service=mock_token_service,
        )
        # Patch internal methods to avoid SQLAlchemy column expressions
        service._find_or_create_user = AsyncMock(return_value=new_user)

        # OAuth account lookup returns None (new account)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = await service.handle_callback(
            code="auth-code", state="valid-state", redirect_uri="http://localhost/cb"
        )

        assert response.tokens.access_token == "jwt-access"
        assert response.tokens.refresh_token == "jwt-refresh"
        # Should have called db.add once (oauth account only, user was handled by mock)
        assert mock_db.add.call_count == 1
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_invalid_state(
        self, mock_db, mock_redis, mock_provider, mock_token_service
    ):
        mock_redis.client.get = AsyncMock(return_value=None)

        service = OAuthService(
            db=mock_db,
            redis=mock_redis,
            provider=mock_provider,
            token_service=mock_token_service,
        )
        with pytest.raises(OAuthError, match="Invalid or expired"):
            await service.handle_callback(
                code="auth-code", state="bad-state", redirect_uri="http://localhost/cb"
            )

    @pytest.mark.asyncio
    @patch("app.domain.auth.oauth.service.encrypt_value", return_value="encrypted")
    async def test_callback_existing_user_merge(
        self, mock_encrypt, mock_db, mock_redis, mock_provider, mock_token_service
    ):
        existing_user = MagicMock(spec=User)
        existing_user.id = uuid.uuid4()
        existing_user.email = "test@gmail.com"
        existing_user.full_name = "Existing User"
        existing_user.is_active = True
        existing_user.is_admin = False
        existing_user.created_at = datetime.now(UTC)

        # First execute: user lookup → found
        # Second execute: OAuth account lookup → not found
        mock_result_user = MagicMock()
        mock_result_user.scalar_one_or_none.return_value = existing_user
        mock_result_oauth = MagicMock()
        mock_result_oauth.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[mock_result_user, mock_result_oauth])

        service = OAuthService(
            db=mock_db,
            redis=mock_redis,
            provider=mock_provider,
            token_service=mock_token_service,
        )
        await service.handle_callback(
            code="auth-code", state="valid-state", redirect_uri="http://localhost/cb"
        )

        # Should NOT create a new user (only add OAuth account)
        assert mock_db.add.call_count == 1  # Only OAuthAccount added
        mock_token_service.create_access_token.assert_called_once_with(existing_user.id)

    @pytest.mark.asyncio
    @patch("app.domain.auth.oauth.service.encrypt_value", return_value="encrypted")
    async def test_callback_existing_oauth_account_updates_tokens(
        self, mock_encrypt, mock_db, mock_redis, mock_provider, mock_token_service
    ):
        existing_user = MagicMock(spec=User)
        existing_user.id = uuid.uuid4()
        existing_user.email = "test@gmail.com"
        existing_user.full_name = "Test User"
        existing_user.is_active = True
        existing_user.is_admin = False
        existing_user.created_at = datetime.now(UTC)

        existing_account = MagicMock(spec=OAuthAccount)
        existing_account.access_token_enc = "old-enc"
        existing_account.refresh_token_enc = "old-enc"

        mock_result_user = MagicMock()
        mock_result_user.scalar_one_or_none.return_value = existing_user
        mock_result_oauth = MagicMock()
        mock_result_oauth.scalar_one_or_none.return_value = existing_account
        mock_db.execute = AsyncMock(side_effect=[mock_result_user, mock_result_oauth])

        service = OAuthService(
            db=mock_db,
            redis=mock_redis,
            provider=mock_provider,
            token_service=mock_token_service,
        )
        await service.handle_callback(
            code="auth-code", state="valid-state", redirect_uri="http://localhost/cb"
        )

        # Should update existing account, not add new one
        assert mock_db.add.call_count == 0
        assert existing_account.access_token_enc == "encrypted"
        assert existing_account.refresh_token_enc == "encrypted"
