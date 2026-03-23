"""JWT token service.

Creates and verifies JWT access and refresh tokens.
Implements AbstractTokenService interface.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt  # PyJWT

from app.config import get_settings
from app.domain.auth.exceptions import InvalidTokenError
from app.domain.auth.interfaces import AbstractTokenService


class TokenService(AbstractTokenService):
    """JWT token service using PyJWT.

    Access tokens are short-lived (configurable, default 30 min).
    Refresh tokens are long-lived (configurable, default 7 days).
    Both use HS256 by default (configurable via settings).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._secret_key = settings.jwt_secret_key
        self._algorithm = settings.jwt_algorithm
        self._access_expire_minutes = settings.jwt_access_token_expire_minutes
        self._refresh_expire_days = settings.jwt_refresh_token_expire_days

    def create_access_token(self, user_id: uuid.UUID) -> str:
        """Create a short-lived access token.

        Args:
            user_id: The user's UUID to embed in the token.

        Returns:
            Encoded JWT string.
        """
        expire = datetime.now(UTC) + timedelta(minutes=self._access_expire_minutes)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(self, user_id: uuid.UUID) -> str:
        """Create a long-lived refresh token.

        Args:
            user_id: The user's UUID to embed in the token.

        Returns:
            Encoded JWT string.
        """
        expire = datetime.now(UTC) + timedelta(days=self._refresh_expire_days)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "exp": expire,
            "type": "refresh",
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify and decode a JWT token.

        Args:
            token: The encoded JWT string.

        Returns:
            Decoded payload dict with 'sub', 'exp', 'type' keys.

        Raises:
            InvalidTokenError: If the token is invalid, expired, or malformed.
        """
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
            if "sub" not in payload:
                raise InvalidTokenError("Token missing subject claim")
            return payload
        except jwt.ExpiredSignatureError as e:
            raise InvalidTokenError("Token has expired") from e
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Token verification failed: {e}") from e

    @property
    def access_expire_seconds(self) -> int:
        """Get access token expiry in seconds (for API response)."""
        return self._access_expire_minutes * 60
