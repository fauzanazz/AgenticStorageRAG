"""OAuth authentication router.

Handles the OAuth authorization and callback flow for external providers.
Currently supports Google; extensible via the provider registry.
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_db, get_redis
from app.domain.auth.exceptions import OAuthError
from app.domain.auth.oauth.google import GoogleOAuthProvider
from app.domain.auth.oauth.service import OAuthService
from app.domain.auth.schemas import AuthResponse
from app.infra.redis_client import RedisClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oauth", tags=["auth-oauth"])

# Provider registry — add new providers here
_PROVIDERS = {
    "google": GoogleOAuthProvider,
}


def _get_provider(provider: str) -> GoogleOAuthProvider:
    """Look up an OAuth provider by name."""
    cls = _PROVIDERS.get(provider)
    if cls is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown OAuth provider: {provider}",
        )
    return cls()


def _get_callback_uri(request: Request, provider: str) -> str:
    """Build the OAuth callback URI for a provider."""
    settings = get_settings()
    return f"{settings.api_prefix}/auth/oauth/{provider}/callback"


@router.get(
    "/{provider}/authorize",
    summary="Get OAuth authorization URL",
)
async def authorize(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict[str, str]:
    """Generate the OAuth authorization URL for a provider.

    The frontend should redirect the user to the returned URL.
    """
    oauth_provider = _get_provider(provider)
    service = OAuthService(db=db, redis=redis, provider=oauth_provider)

    # Build the callback URL using the request's base URL
    callback_uri = str(request.base_url).rstrip("/") + _get_callback_uri(request, provider)

    try:
        url = await service.get_authorization_url(redirect_uri=callback_uri)
    except OAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        ) from e

    return {"authorization_url": url}


@router.get(
    "/{provider}/callback",
    summary="OAuth callback endpoint",
    response_class=RedirectResponse,
)
async def callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> RedirectResponse:
    """Handle the OAuth provider callback.

    Exchanges the authorization code for tokens, creates or links the user,
    and redirects to the frontend with JWT tokens in the URL fragment.
    """
    settings = get_settings()
    frontend_callback = f"{settings.frontend_url}/auth/callback"

    # Handle provider-side errors (user denied consent, etc.)
    if error:
        logger.warning("OAuth callback error from %s: %s", provider, error)
        params = urlencode({"error": error})
        return RedirectResponse(url=f"{frontend_callback}?{params}")

    if not code or not state:
        params = urlencode({"error": "missing_params"})
        return RedirectResponse(url=f"{frontend_callback}?{params}")

    oauth_provider = _get_provider(provider)
    service = OAuthService(db=db, redis=redis, provider=oauth_provider)

    # Reconstruct the callback URI (must match what was used in authorize)
    callback_uri = str(request.base_url).rstrip("/") + _get_callback_uri(request, provider)

    try:
        auth_response = await service.handle_callback(
            code=code, state=state, redirect_uri=callback_uri
        )
    except OAuthError as e:
        logger.error("OAuth callback failed for %s: %s", provider, e.message)
        params = urlencode({"error": e.message})
        return RedirectResponse(url=f"{frontend_callback}?{params}")

    # Store auth response behind a one-time exchange code and redirect
    exchange_code = secrets.token_urlsafe(32)
    await redis.set_json(
        f"oauth_code:{exchange_code}",
        auth_response.model_dump(mode="json"),
        ttl=60,
    )
    return RedirectResponse(url=f"{frontend_callback}?code={exchange_code}")


class OAuthTokenRequest(BaseModel):
    code: str


@router.post(
    "/token",
    summary="Exchange one-time OAuth code for tokens",
    response_model=AuthResponse,
)
async def exchange_oauth_code(
    body: OAuthTokenRequest,
    redis: RedisClient = Depends(get_redis),
) -> AuthResponse:
    """Exchange a one-time OAuth code for an AuthResponse (tokens + user)."""
    key = f"oauth_code:{body.code}"
    data = await redis.get_json(key)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth code",
        )
    # Delete immediately — one-time use
    await redis.delete(key)
    return AuthResponse.model_validate(data)
