import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user_id, get_db
from app.config import get_settings
from app.domain.settings.schemas import (
    CHAT_MODELS,
    EMBEDDING_MODELS,
    PROVIDER_DEFAULT_CHAT_MODEL,
    PROVIDER_KEY_MAP,
    AvailableModelsResponse,
    ModelCatalogResponse,
    ModelSettingsResponse,
    UpdateModelSettingsRequest,
)
from app.domain.settings.service import SettingsService

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
            or getattr(user_settings, "use_claude_code", False)
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

    # Pick the best default based on provider priority
    default_model: str | None = None
    for provider, model_id in PROVIDER_DEFAULT_CHAT_MODEL:
        if provider in available_providers:
            default_model = model_id
            break

    return AvailableModelsResponse(models=filtered, default_model=default_model)


@router.get("/claude-code/test")
async def test_claude_code(
    _user_id: uuid.UUID = Depends(get_current_user_id),
) -> dict:
    """Smoke test: check if the local `claude` CLI binary is available and responsive."""
    from app.infra.claude_code import check_claude_binary

    available, version = check_claude_binary()
    if not available:
        return {"ok": False, "error": "claude CLI binary not found in PATH"}

    try:
        from claude_agent_sdk import ClaudeAgentOptions, AssistantMessage, TextBlock, query

        response_text = ""
        options = ClaudeAgentOptions(max_turns=1)
        async for msg in query(prompt="Say hello", options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
        return {"ok": True, "version": version, "response": response_text[:200]}
    except Exception as e:
        return {"ok": False, "version": version, "error": str(e)}


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
