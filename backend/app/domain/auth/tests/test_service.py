"""Tests for auth service."""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.auth.exceptions import (
    EmailAlreadyExistsError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
)
from app.domain.auth.models import User
from app.domain.auth.schemas import LoginRequest, RegisterRequest
from app.domain.auth.service import AuthService


def _make_mock_user(
    email: str = "test@example.com",
    full_name: str = "Test User",
    is_active: bool = True,
    is_admin: bool = False,
) -> User:
    """Create a mock User object for testing."""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = email
    user.full_name = full_name
    user.hashed_password = "$2b$12$mock_hash"
    user.is_active = is_active
    user.is_admin = is_admin
    user.org_id = None
    user.created_at = MagicMock()
    user.updated_at = MagicMock()
    return user


class TestAuthServiceRegister:
    """Tests for user registration."""

    @pytest.mark.asyncio
    async def test_register_success(self) -> None:
        """register() should create user and return auth response."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing user
        mock_db.execute.return_value = mock_result

        # db.add() is NOT a coroutine on AsyncSession -- make it a regular MagicMock
        # When called, simulate DB setting default fields on the User object
        def _set_defaults(user: Any) -> None:
            user.id = uuid.uuid4()
            user.is_active = True
            user.is_admin = False
            user.created_at = datetime.now(timezone.utc)
            user.updated_at = datetime.now(timezone.utc)

        mock_db.add = MagicMock(side_effect=_set_defaults)

        mock_hasher = MagicMock()
        mock_hasher.hash.return_value = "$2b$12$hashed"

        mock_tokens = MagicMock()
        mock_tokens.create_access_token.return_value = "access_token"
        mock_tokens.create_refresh_token.return_value = "refresh_token"
        mock_tokens.access_expire_seconds = 1800

        service = AuthService(
            db=mock_db,
            password_hasher=mock_hasher,
            token_service=mock_tokens,
        )

        data = RegisterRequest(
            email="new@example.com",
            password="securepassword",
            full_name="New User",
        )

        result = await service.register(data)

        assert result.tokens.access_token == "access_token"
        assert result.tokens.refresh_token == "refresh_token"
        assert result.user.email == "new@example.com"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_hasher.hash.assert_called_once_with("securepassword")

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises(self) -> None:
        """register() should raise EmailAlreadyExistsError for duplicates."""
        existing_user = _make_mock_user(email="taken@example.com")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_db.execute.return_value = mock_result

        service = AuthService(db=mock_db)

        data = RegisterRequest(
            email="taken@example.com",
            password="password123",
            full_name="Duplicate",
        )

        with pytest.raises(EmailAlreadyExistsError):
            await service.register(data)


class TestAuthServiceLogin:
    """Tests for user login."""

    @pytest.mark.asyncio
    async def test_login_success(self) -> None:
        """login() should return tokens for valid credentials."""
        user = _make_mock_user()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        mock_hasher = MagicMock()
        mock_hasher.verify.return_value = True

        mock_tokens = MagicMock()
        mock_tokens.create_access_token.return_value = "access_token"
        mock_tokens.create_refresh_token.return_value = "refresh_token"
        mock_tokens.access_expire_seconds = 1800

        service = AuthService(
            db=mock_db,
            password_hasher=mock_hasher,
            token_service=mock_tokens,
        )

        data = LoginRequest(email="test@example.com", password="correct")

        result = await service.login(data)

        assert result.tokens.access_token == "access_token"
        mock_hasher.verify.assert_called_once_with("correct", user.hashed_password)

    @pytest.mark.asyncio
    async def test_login_wrong_email_raises(self) -> None:
        """login() should raise InvalidCredentialsError for unknown email."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = AuthService(db=mock_db)

        data = LoginRequest(email="unknown@example.com", password="whatever")

        with pytest.raises(InvalidCredentialsError):
            await service.login(data)

    @pytest.mark.asyncio
    async def test_login_wrong_password_raises(self) -> None:
        """login() should raise InvalidCredentialsError for wrong password."""
        user = _make_mock_user()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        mock_hasher = MagicMock()
        mock_hasher.verify.return_value = False

        service = AuthService(db=mock_db, password_hasher=mock_hasher)

        data = LoginRequest(email="test@example.com", password="wrong")

        with pytest.raises(InvalidCredentialsError):
            await service.login(data)

    @pytest.mark.asyncio
    async def test_login_inactive_user_raises(self) -> None:
        """login() should raise InactiveUserError for deactivated users."""
        user = _make_mock_user(is_active=False)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        mock_hasher = MagicMock()
        mock_hasher.verify.return_value = True

        service = AuthService(db=mock_db, password_hasher=mock_hasher)

        data = LoginRequest(email="test@example.com", password="correct")

        with pytest.raises(InactiveUserError):
            await service.login(data)


class TestAuthServiceRefresh:
    """Tests for token refresh."""

    @pytest.mark.asyncio
    async def test_refresh_success(self) -> None:
        """refresh_tokens() should return new tokens for valid refresh token."""
        user = _make_mock_user()
        user_id = user.id

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        mock_tokens = MagicMock()
        mock_tokens.verify_token.return_value = {
            "sub": str(user_id),
            "type": "refresh",
        }
        mock_tokens.create_access_token.return_value = "new_access"
        mock_tokens.create_refresh_token.return_value = "new_refresh"
        mock_tokens.access_expire_seconds = 1800

        service = AuthService(db=mock_db, token_service=mock_tokens)

        result = await service.refresh_tokens("valid_refresh_token")

        assert result.access_token == "new_access"
        assert result.refresh_token == "new_refresh"

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_raises(self) -> None:
        """refresh_tokens() should reject access tokens."""
        mock_db = AsyncMock()
        mock_tokens = MagicMock()
        mock_tokens.verify_token.return_value = {
            "sub": str(uuid.uuid4()),
            "type": "access",  # Wrong type
        }

        service = AuthService(db=mock_db, token_service=mock_tokens)

        with pytest.raises(InvalidTokenError, match="Not a refresh token"):
            await service.refresh_tokens("access_token_used_as_refresh")

    @pytest.mark.asyncio
    async def test_refresh_deleted_user_raises(self) -> None:
        """refresh_tokens() should raise when user no longer exists."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # User deleted
        mock_db.execute.return_value = mock_result

        mock_tokens = MagicMock()
        mock_tokens.verify_token.return_value = {
            "sub": str(uuid.uuid4()),
            "type": "refresh",
        }

        service = AuthService(db=mock_db, token_service=mock_tokens)

        with pytest.raises(UserNotFoundError):
            await service.refresh_tokens("valid_refresh_token")


class TestAuthServiceGetCurrentUser:
    """Tests for get_current_user."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self) -> None:
        """get_current_user() should return user profile."""
        user = _make_mock_user()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        service = AuthService(db=mock_db)

        result = await service.get_current_user(user.id)

        assert result.email == user.email
        assert result.full_name == user.full_name

    @pytest.mark.asyncio
    async def test_get_current_user_not_found_raises(self) -> None:
        """get_current_user() should raise for missing user."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = AuthService(db=mock_db)

        with pytest.raises(UserNotFoundError):
            await service.get_current_user(uuid.uuid4())
