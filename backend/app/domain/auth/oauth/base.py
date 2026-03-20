"""Abstract OAuth provider interface.

Defines the contract that all OAuth providers must implement.
Adding a new provider (e.g., GitHub) = one new file implementing AbstractOAuthProvider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OAuthUserInfo:
    """User profile information from an OAuth provider."""

    email: str
    full_name: str
    provider_user_id: str
    picture_url: str | None = None


@dataclass(frozen=True)
class OAuthTokens:
    """OAuth tokens received from provider after code exchange."""

    access_token: str
    refresh_token: str | None = None
    token_expiry: datetime | None = None
    scopes: list[str] | None = None


class AbstractOAuthProvider(ABC):
    """Contract for OAuth provider implementations.

    Each provider (Google, GitHub, etc.) implements this interface.
    The OAuth service uses it without knowing provider-specific details.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for this provider (e.g., 'google', 'github')."""
        ...

    @abstractmethod
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Build the OAuth authorization URL for the consent screen.

        Args:
            state: CSRF protection token (stored in Redis, verified on callback).
            redirect_uri: The callback URL Google will redirect to after consent.

        Returns:
            Full authorization URL to redirect the user to.
        """
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        """Exchange an authorization code for OAuth tokens.

        Args:
            code: The authorization code from the callback.
            redirect_uri: Must match the redirect_uri used in get_authorization_url.

        Returns:
            OAuthTokens with access token and optionally refresh token.
        """
        ...

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch the user's profile from the OAuth provider.

        Args:
            access_token: A valid OAuth access token.

        Returns:
            OAuthUserInfo with email, name, and provider-specific user ID.
        """
        ...
