import logging
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user_id, get_db, get_redis
from app.config import get_settings
from app.domain.settings.claude_oauth import ClaudeOAuthService
from app.domain.settings.schemas import (
    CHAT_MODELS,
    EMBEDDING_MODELS,
    PROVIDER_KEY_MAP,
    AvailableModelsResponse,
    ModelCatalogResponse,
    ModelSettingsResponse,
    UpdateModelSettingsRequest,
)
from app.domain.settings.service import SettingsService
from app.infra.redis_client import RedisClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_settings_service(db: AsyncSession = Depends(get_db)) -> SettingsService:
    return SettingsService(db=db)


@router.get("/models/catalog", response_model=ModelCatalogResponse)
async def get_model_catalog() -> ModelCatalogResponse:
    """Return the curated list of supported models per use-case. No auth required."""
    return ModelCatalogResponse(
        chat_models=CHAT_MODELS,
        embedding_models=EMBEDDING_MODELS,
    )


@router.get("/models/available", response_model=AvailableModelsResponse)
async def get_available_models(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SettingsService = Depends(_get_settings_service),
) -> AvailableModelsResponse:
    """Return chat models filtered by which providers have API keys.

    Combines server-level env vars with user-level keys to determine
    which providers are available, then filters the catalog accordingly.
    """
    settings = get_settings()

    # Server-level keys (from env / .env)
    server_keys = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
        "dashscope": bool(settings.dashscope_api_key),
        "openrouter": bool(settings.openrouter_api_key),
    }

    # User-level keys
    user_settings = await service.get_raw_settings(user_id)
    user_keys = {
        "anthropic": bool(
            getattr(user_settings, "anthropic_api_key_enc", None)
            or getattr(user_settings, "claude_oauth_token_enc", None)
        ) if user_settings else False,
        "openai": bool(getattr(user_settings, "openai_api_key_enc", None)) if user_settings else False,
        "dashscope": bool(getattr(user_settings, "dashscope_api_key_enc", None)) if user_settings else False,
        "openrouter": bool(getattr(user_settings, "openrouter_api_key_enc", None)) if user_settings else False,
    }

    # A provider is available if either source has a key
    available_providers = {
        provider
        for provider, key_prefix in PROVIDER_KEY_MAP.items()
        if server_keys.get(key_prefix) or user_keys.get(key_prefix)
    }

    filtered = [m for m in CHAT_MODELS if m["provider"] in available_providers]
    return AvailableModelsResponse(models=filtered)


@router.get("/models", response_model=ModelSettingsResponse)
async def get_model_settings(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SettingsService = Depends(_get_settings_service),
) -> ModelSettingsResponse:
    """Get the current user's model settings."""
    return await service.get_model_settings(user_id)


@router.put("/models", response_model=ModelSettingsResponse)
async def update_model_settings(
    request: UpdateModelSettingsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SettingsService = Depends(_get_settings_service),
) -> ModelSettingsResponse:
    """Upsert model settings for the current user."""
    return await service.upsert_model_settings(user_id, request)


# ---------------------------------------------------------------------------
# Claude OAuth endpoints
# ---------------------------------------------------------------------------


@router.get("/claude-oauth/authorize")
async def claude_oauth_authorize(
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict[str, str]:
    """Generate the Claude OAuth authorization URL."""
    settings = get_settings()
    callback_uri = (
        str(request.base_url).rstrip("/")
        + settings.api_prefix
        + "/settings/claude-oauth/callback"
    )
    service = ClaudeOAuthService(db=db, redis=redis)
    url = await service.build_authorization_url(user_id, redirect_uri=callback_uri)
    return {"authorization_url": url}


@router.get("/claude-oauth/callback", response_class=RedirectResponse)
async def claude_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> RedirectResponse:
    """Handle the Claude OAuth callback (browser redirect — no auth required)."""
    settings = get_settings()
    frontend_settings = f"{settings.frontend_url}/settings"

    if error:
        logger.warning("Claude OAuth callback error: %s", error)
        return RedirectResponse(url=f"{frontend_settings}?claude_oauth=error")

    if not code or not state:
        return RedirectResponse(url=f"{frontend_settings}?claude_oauth=error")

    callback_uri = (
        str(request.base_url).rstrip("/")
        + settings.api_prefix
        + "/settings/claude-oauth/callback"
    )

    try:
        service = ClaudeOAuthService(db=db, redis=redis)
        await service.handle_callback(code=code, state=state, redirect_uri=callback_uri)
    except Exception as e:
        logger.error("Claude OAuth callback failed: %s", e)
        return RedirectResponse(url=f"{frontend_settings}?claude_oauth=error")

    return RedirectResponse(url=f"{frontend_settings}?claude_oauth=success")


@router.delete("/claude-oauth")
async def claude_oauth_disconnect(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict[str, str]:
    """Disconnect Claude OAuth — clears stored tokens."""
    service = ClaudeOAuthService(db=db, redis=redis)
    await service.disconnect(user_id)
    return {"status": "disconnected"}
