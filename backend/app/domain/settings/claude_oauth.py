"""Claude OAuth service for Claude Pro/Max subscribers.

Implements the OAuth 2.0 + PKCE flow against claude.ai, replicating
what Claude Code CLI does during `claude setup-token`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.settings.models import UserModelSettings
from app.infra.encryption import decrypt_value, encrypt_value
from app.infra.redis_client import RedisClient

logger = logging.getLogger(__name__)

CLAUDE_AUTH_URL = "https://claude.ai/oauth/authorize"
CLAUDE_TOKEN_URL = "https://claude.ai/oauth/token"
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_SCOPE = "user:inference"

_REDIS_PREFIX = "claude_settings_oauth:"
_STATE_TTL = 300  # 5 minutes


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class ClaudeOAuthService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self._db = db
        self._redis = redis

    async def build_authorization_url(
        self,
        user_id: uuid.UUID,
        redirect_uri: str,
    ) -> str:
        """Build the Claude OAuth authorization URL and store PKCE state in Redis."""
        verifier, challenge = _generate_pkce()
        state = secrets.token_urlsafe(32)

        # Store state → {user_id, code_verifier} in Redis
        payload = json.dumps({"user_id": str(user_id), "code_verifier": verifier})
        await self._redis.client.set(f"{_REDIS_PREFIX}{state}", payload, ex=_STATE_TTL)

        params = {
            "client_id": CLAUDE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": CLAUDE_SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        qs = "&".join(f"{k}={httpx.URL('', params={k: v}).params[k]}" for k, v in params.items())
        return f"{CLAUDE_AUTH_URL}?{qs}"

    async def handle_callback(
        self,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> uuid.UUID:
        """Exchange authorization code for tokens and store them.

        Returns the user_id associated with the state.
        """
        # Retrieve and delete state from Redis
        redis_key = f"{_REDIS_PREFIX}{state}"
        raw = await self._redis.client.get(redis_key)
        if not raw:
            raise ValueError("Invalid or expired OAuth state")
        await self._redis.client.delete(redis_key)

        data = json.loads(raw)
        user_id = uuid.UUID(data["user_id"])
        code_verifier = data["code_verifier"]

        # Exchange code for tokens
        tokens = await self._exchange_code(code, redirect_uri, code_verifier)
        await self._store_tokens(user_id, tokens)
        return user_id

    async def _exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict:
        """POST to Claude token endpoint to exchange code for tokens."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                CLAUDE_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": CLAUDE_CLIENT_ID,
                    "code_verifier": code_verifier,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def _store_tokens(self, user_id: uuid.UUID, tokens: dict) -> None:
        """Encrypt and persist OAuth tokens to UserModelSettings."""
        result = await self._db.execute(
            select(UserModelSettings).where(UserModelSettings.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = UserModelSettings(user_id=user_id)
            self._db.add(row)
            await self._db.flush()

        row.claude_oauth_token_enc = encrypt_value(tokens["access_token"])
        if tokens.get("refresh_token"):
            row.claude_oauth_refresh_token_enc = encrypt_value(tokens["refresh_token"])
        if tokens.get("expires_in"):
            row.claude_oauth_token_expiry = datetime.now(UTC) + timedelta(
                seconds=int(tokens["expires_in"])
            )

        await self._db.commit()

    async def refresh_token(self, refresh_token_enc: str) -> dict:
        """Use the refresh token to get a new access token."""
        refresh_token = decrypt_value(refresh_token_enc)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                CLAUDE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": CLAUDE_CLIENT_ID,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_and_store(self, user_id: uuid.UUID, refresh_token_enc: str) -> None:
        """Refresh the token and store the new one."""
        tokens = await self.refresh_token(refresh_token_enc)
        await self._store_tokens(user_id, tokens)

    async def disconnect(self, user_id: uuid.UUID) -> None:
        """Clear all Claude OAuth fields for the user."""
        result = await self._db.execute(
            select(UserModelSettings).where(UserModelSettings.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row:
            row.claude_oauth_token_enc = None
            row.claude_oauth_refresh_token_enc = None
            row.claude_oauth_token_expiry = None
            await self._db.commit()
