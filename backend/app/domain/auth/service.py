"""Auth service implementation.

Orchestrates registration, login, token refresh, and user lookups.
Implements AbstractAuthService. All database access goes through
the injected SQLAlchemy session.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth.exceptions import (
    EmailAlreadyExistsError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    OAuthLoginRequiredError,
    UserNotFoundError,
)
from app.domain.auth.interfaces import AbstractAuthService
from app.domain.auth.models import User
from app.domain.auth.password import PasswordHasher
from app.domain.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.domain.auth.token import TokenService
from app.infra.logging_utils import redact_email

logger = logging.getLogger(__name__)


class AuthService(AbstractAuthService):
    """Production auth service backed by PostgreSQL.

    Receives a database session via dependency injection.
    Password hashing and JWT tokens are handled by dedicated services.
    """

    def __init__(
        self,
        db: AsyncSession,
        password_hasher: PasswordHasher | None = None,
        token_service: TokenService | None = None,
    ) -> None:
        self._db = db
        self._hasher = password_hasher or PasswordHasher()
        self._tokens = token_service or TokenService()

    async def register(self, data: RegisterRequest) -> AuthResponse:
        """Register a new user.

        Args:
            data: Registration request with email, password, full_name.

        Returns:
            AuthResponse with user profile and JWT tokens.

        Raises:
            EmailAlreadyExistsError: If email is already registered.
        """
        # Check for duplicate email
        existing = await self._get_user_by_email(data.email)
        if existing is not None:
            raise EmailAlreadyExistsError(data.email)

        # Create user
        user = User(
            email=data.email,
            hashed_password=self._hasher.hash(data.password),
            full_name=data.full_name,
        )
        self._db.add(user)
        await self._db.flush()  # Get the user ID without committing

        # Generate tokens
        tokens = self._create_token_response(user.id)

        logger.info("User registered: %s (%s)", user.id, redact_email(data.email))

        return AuthResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        )

    async def login(self, data: LoginRequest) -> AuthResponse:
        """Authenticate user with email and password.

        Args:
            data: Login request with email and password.

        Returns:
            AuthResponse with user profile and JWT tokens.

        Raises:
            InvalidCredentialsError: If email/password is wrong.
            InactiveUserError: If the user account is deactivated.
        """
        user = await self._get_user_by_email(data.email)
        if user is None:
            raise InvalidCredentialsError()

        if user.hashed_password is None:
            raise OAuthLoginRequiredError(provider="google")

        if not self._hasher.verify(data.password, user.hashed_password):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        tokens = self._create_token_response(user.id)

        logger.info("User logged in: %s (%s)", user.id, redact_email(data.email))

        return AuthResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """Refresh tokens using a valid refresh token.

        Args:
            refresh_token: The refresh JWT string.

        Returns:
            New TokenResponse with fresh access and refresh tokens.

        Raises:
            InvalidTokenError: If refresh token is invalid or expired.
            UserNotFoundError: If the user in the token no longer exists.
            InactiveUserError: If the user is deactivated.
        """
        payload = self._tokens.verify_token(refresh_token)

        if payload.get("type") != "refresh":
            raise InvalidTokenError("Not a refresh token")

        user_id = uuid.UUID(payload["sub"])
        user = await self._get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))

        if not user.is_active:
            raise InactiveUserError()

        return self._create_token_response(user.id)

    async def get_current_user(self, user_id: uuid.UUID) -> UserResponse:
        """Get user profile by ID.

        Args:
            user_id: The user's UUID.

        Returns:
            UserResponse with public profile fields.

        Raises:
            UserNotFoundError: If no user with that ID exists.
        """
        user = await self._get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))

        return UserResponse.model_validate(user)

    async def update_profile(self, user_id: uuid.UUID, data: UpdateProfileRequest) -> UserResponse:
        """Update user profile fields.

        Args:
            user_id: The user's UUID.
            data: Fields to update (only non-None fields are applied).

        Returns:
            Updated UserResponse.

        Raises:
            UserNotFoundError: If no user with that ID exists.
            EmailAlreadyExistsError: If the new email is taken by another user.
        """
        user = await self._get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))

        if data.full_name is not None:
            user.full_name = data.full_name

        if data.email is not None and data.email != user.email:
            existing = await self._get_user_by_email(data.email)
            if existing is not None:
                raise EmailAlreadyExistsError(data.email)
            user.email = data.email

        await self._db.flush()
        logger.info("User profile updated: %s", user_id)
        return UserResponse.model_validate(user)

    # --- Private helpers ---

    async def _get_user_by_email(self, email: str) -> User | None:
        """Look up a user by email address."""
        stmt = select(User).where(User.email == email)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Look up a user by UUID."""
        stmt = select(User).where(User.id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def _create_token_response(self, user_id: uuid.UUID) -> TokenResponse:
        """Generate a token pair for the given user."""
        return TokenResponse(
            access_token=self._tokens.create_access_token(user_id),
            refresh_token=self._tokens.create_refresh_token(user_id),
            expires_in=self._tokens.access_expire_seconds,
        )
