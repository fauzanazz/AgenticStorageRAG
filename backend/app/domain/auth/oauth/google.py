"""Google OAuth provider implementation.

Uses Google's OAuth 2.0 web server flow to authenticate users and
request read-only Drive access for document ingestion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.domain.auth.exceptions import OAuthError
from app.domain.auth.oauth.base import (
    AbstractOAuthProvider,
    OAuthTokens,
    OAuthUserInfo,
)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.readonly",
]


class GoogleOAuthProvider(AbstractOAuthProvider):
    """Google OAuth 2.0 provider for web server flow."""

    @property
    def provider_name(self) -> str:
        return "google"

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Build Google OAuth consent screen URL."""
        settings = get_settings()
        if not settings.google_client_id:
            raise OAuthError("google", "GOOGLE_CLIENT_ID is not configured")

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(_SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        """Exchange authorization code for tokens via Google's token endpoint."""
        settings = get_settings()

        payload = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data=payload,
                headers={"Accept": "application/json"},
            )

        if resp.status_code != 200:
            detail = resp.json().get("error_description", resp.text)
            raise OAuthError("google", f"Token exchange failed: {detail}")

        data = resp.json()

        expires_in = data.get("expires_in")
        token_expiry = (
            datetime.now(UTC) + timedelta(seconds=int(expires_in))
            if expires_in
            else None
        )

        scope_str = data.get("scope", "")

        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_expiry=token_expiry,
            scopes=scope_str.split() if scope_str else None,
        )

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch the authenticated user's profile from Google."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code != 200:
            raise OAuthError("google", f"Failed to fetch user info (HTTP {resp.status_code})")

        data = resp.json()

        email = data.get("email")
        if not email:
            raise OAuthError("google", "Google account has no email address")

        return OAuthUserInfo(
            email=email,
            full_name=data.get("name", ""),
            provider_user_id=data["sub"],
            picture_url=data.get("picture"),
        )
