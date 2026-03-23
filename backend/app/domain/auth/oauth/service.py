"""OAuth authentication service.

Orchestrates the OAuth flow: state management, provider interaction,
user find-or-create, and token storage.
"""

from __future__ import annotations

import logging
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.auth.exceptions import OAuthError
from app.domain.auth.models import OAuthAccount, User
from app.domain.auth.oauth.base import AbstractOAuthProvider
from app.domain.auth.schemas import AuthResponse, TokenResponse, UserResponse
from app.domain.auth.token import TokenService
from app.infra.encryption import encrypt_value
from app.infra.redis_client import RedisClient

logger = logging.getLogger(__name__)

# Redis key prefix and TTL for OAuth state tokens
_STATE_PREFIX = "oauth_state:"
_STATE_TTL_SECONDS = 300  # 5 minutes


class OAuthService:
    """Handles OAuth login flow: state, code exchange, user upsert."""

    def __init__(
        self,
        db: AsyncSession,
        redis: RedisClient,
        provider: AbstractOAuthProvider,
        token_service: TokenService | None = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._provider = provider
        self._tokens = token_service or TokenService()

    async def get_authorization_url(self, redirect_uri: str) -> str:
        """Generate authorization URL with CSRF state stored in Redis."""
        state = secrets.token_urlsafe(32)
        await self._redis.client.set(
            f"{_STATE_PREFIX}{state}",
            self._provider.provider_name,
            ex=_STATE_TTL_SECONDS,
        )
        return self._provider.get_authorization_url(state=state, redirect_uri=redirect_uri)

    async def handle_callback(self, code: str, state: str, redirect_uri: str) -> AuthResponse:
        """Handle OAuth callback: verify state, exchange code, find-or-create user."""
        # 1. Verify state
        redis_key = f"{_STATE_PREFIX}{state}"
        stored = await self._redis.client.get(redis_key)
        if stored is None:
            raise OAuthError(self._provider.provider_name, "Invalid or expired OAuth state")
        await self._redis.client.delete(redis_key)  # one-time use

        # 2. Exchange code for tokens
        oauth_tokens = await self._provider.exchange_code(code, redirect_uri)

        # 3. Get user info from provider
        user_info = await self._provider.get_user_info(oauth_tokens.access_token)

        # 4. Find or create user
        user = await self._find_or_create_user(user_info)

        # 5. Upsert OAuth account with encrypted tokens
        await self._upsert_oauth_account(user.id, user_info, oauth_tokens)

        await self._db.commit()

        # 6. Generate JWT tokens
        jwt_tokens = self._create_token_response(user.id)

        logger.info(
            "OAuth login (%s): user=%s email=%s",
            self._provider.provider_name,
            user.id,
            user.email,
        )

        return AuthResponse(
            user=UserResponse.model_validate(user),
            tokens=jwt_tokens,
        )

    async def _find_or_create_user(self, user_info) -> User:
        """Find existing user by OAuth link or email, or create a new one."""
        # 1. Check for existing OAuth account first (authoritative identity match).
        # This must come before the email lookup so that a provider email change
        # does not accidentally match a different local account.
        oauth_stmt = (
            select(User)
            .join(OAuthAccount, OAuthAccount.user_id == User.id)
            .where(
                OAuthAccount.provider == self._provider.provider_name,
                OAuthAccount.provider_user_id == user_info.provider_user_id,
            )
        )
        oauth_result = await self._db.execute(oauth_stmt)
        existing_user = oauth_result.scalar_one_or_none()
        if existing_user is not None:
            # Update email to match provider's current email
            existing_user.email = user_info.email.lower()
            if not existing_user.full_name and user_info.full_name:
                existing_user.full_name = user_info.full_name
            return existing_user

        # 2. Case-insensitive email lookup (first-time OAuth for existing user)
        stmt = select(User).where(func.lower(User.email) == user_info.email.lower())
        result = await self._db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is not None:
            if not user.full_name and user_info.full_name:
                user.full_name = user_info.full_name
            return user

        # 3. Block new user creation when registration is disabled
        if not get_settings().registration_enabled:
            raise OAuthError(self._provider.provider_name, "Registration is currently disabled")

        # Create new user (no password — Google-only)
        user = User(
            email=user_info.email.lower(),
            hashed_password=None,
            full_name=user_info.full_name or user_info.email.split("@")[0],
        )
        self._db.add(user)
        await self._db.flush()

        logger.info("Created new user via OAuth: %s (%s)", user.id, user.email)
        return user

    async def _upsert_oauth_account(self, user_id, user_info, oauth_tokens) -> None:
        """Create or update the OAuth account link."""
        provider_name = self._provider.provider_name

        stmt = select(OAuthAccount).where(
            OAuthAccount.provider == provider_name,
            OAuthAccount.provider_user_id == user_info.provider_user_id,
        )
        result = await self._db.execute(stmt)
        account = result.scalar_one_or_none()

        # Encrypt tokens
        access_enc = encrypt_value(oauth_tokens.access_token) if oauth_tokens.access_token else None
        refresh_enc = (
            encrypt_value(oauth_tokens.refresh_token) if oauth_tokens.refresh_token else None
        )
        scopes_str = " ".join(oauth_tokens.scopes) if oauth_tokens.scopes else None

        if account is not None:
            # Update existing
            account.access_token_enc = access_enc
            account.refresh_token_enc = refresh_enc
            account.token_expiry = oauth_tokens.token_expiry
            account.scopes = scopes_str
        else:
            # Create new
            account = OAuthAccount(
                user_id=user_id,
                provider=provider_name,
                provider_user_id=user_info.provider_user_id,
                access_token_enc=access_enc,
                refresh_token_enc=refresh_enc,
                token_expiry=oauth_tokens.token_expiry,
                scopes=scopes_str,
            )
            self._db.add(account)

    def _create_token_response(self, user_id: uuid.UUID) -> TokenResponse:
        """Generate JWT token pair."""
        return TokenResponse(
            access_token=self._tokens.create_access_token(user_id),
            refresh_token=self._tokens.create_refresh_token(user_id),
            expires_in=self._tokens.access_expire_seconds,
        )
