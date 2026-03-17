import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user_id, get_db
from app.domain.settings.schemas import (
    CHAT_MODELS,
    EMBEDDING_MODELS,
    ModelCatalogResponse,
    ModelSettingsResponse,
    UpdateModelSettingsRequest,
)
from app.domain.settings.service import SettingsService

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
