"""Auth domain interfaces (ABC contracts).

All auth operations are defined here as abstract interfaces.
The AuthService implements these. This enables testing with
mocks and swapping implementations.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.domain.auth.schemas import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    TokenResponse,
    UserResponse,
)


class AbstractAuthService(ABC):
    """Contract for authentication operations."""

    @abstractmethod
    async def register(self, data: RegisterRequest) -> AuthResponse:
        """Register a new user and return tokens + profile."""
        ...

    @abstractmethod
    async def login(self, data: LoginRequest) -> AuthResponse:
        """Authenticate user and return tokens + profile."""
        ...

    @abstractmethod
    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """Refresh an access token using a valid refresh token."""
        ...

    @abstractmethod
    async def get_current_user(self, user_id: uuid.UUID) -> UserResponse:
        """Get the current user profile by ID."""
        ...


class AbstractPasswordHasher(ABC):
    """Contract for password hashing operations."""

    @abstractmethod
    def hash(self, password: str) -> str:
        """Hash a plaintext password."""
        ...

    @abstractmethod
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against a hash."""
        ...


class AbstractTokenService(ABC):
    """Contract for JWT token operations."""

    @abstractmethod
    def create_access_token(self, user_id: uuid.UUID) -> str:
        """Create a short-lived access token."""
        ...

    @abstractmethod
    def create_refresh_token(self, user_id: uuid.UUID) -> str:
        """Create a long-lived refresh token."""
        ...

    @abstractmethod
    def verify_token(self, token: str) -> dict:
        """Verify and decode a JWT token. Raises on invalid/expired."""
        ...
