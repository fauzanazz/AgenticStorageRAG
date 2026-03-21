import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.settings.interfaces import AbstractSettingsService
from app.domain.settings.models import UserModelSettings
from app.domain.settings.schemas import (
    ApiKeyStatus,
    ModelSettingsResponse,
    UpdateModelSettingsRequest,
)
from app.infra.encryption import encrypt_value


class SettingsService(AbstractSettingsService):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_model_settings(self, user_id: uuid.UUID) -> ModelSettingsResponse:
        row = await self._get_or_create(user_id)
        return self._to_response(row)

    async def upsert_model_settings(
        self,
        user_id: uuid.UUID,
        request: UpdateModelSettingsRequest,
    ) -> ModelSettingsResponse:
        row = await self._get_or_create(user_id)

        if request.chat_model is not None:
            row.chat_model = request.chat_model
        if request.ingestion_model is not None:
            row.ingestion_model = request.ingestion_model
        if request.embedding_model is not None:
            row.embedding_model = request.embedding_model

        row.anthropic_api_key_enc = self._apply_key(
            request.anthropic_api_key, row.anthropic_api_key_enc
        )
        row.openai_api_key_enc = self._apply_key(request.openai_api_key, row.openai_api_key_enc)
        row.dashscope_api_key_enc = self._apply_key(
            request.dashscope_api_key, row.dashscope_api_key_enc
        )
        row.openrouter_api_key_enc = self._apply_key(
            request.openrouter_api_key, row.openrouter_api_key_enc
        )
        if request.use_claude_code is not None:
            row.use_claude_code = request.use_claude_code

        await self._db.commit()
        await self._db.refresh(row)
        return self._to_response(row)

    async def get_raw_settings(self, user_id: uuid.UUID) -> UserModelSettings | None:
        """Return raw row with encrypted key fields — callers must decrypt."""
        result = await self._db.execute(
            select(UserModelSettings).where(UserModelSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_create(self, user_id: uuid.UUID) -> UserModelSettings:
        result = await self._db.execute(
            select(UserModelSettings).where(UserModelSettings.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = UserModelSettings(user_id=user_id)
            self._db.add(row)
            await self._db.flush()
        return row

    @staticmethod
    def _apply_key(new_value: str | None, existing_enc: str | None) -> str | None:
        """
        Determine the new encrypted value for an API key field.

        - "" (empty string) → leave unchanged (return existing_enc)
        - None             → clear the key (return None)
        - "sk-..."         → encrypt and store
        """
        if new_value == "":
            return existing_enc
        if new_value is None:
            return None
        return encrypt_value(new_value)

    @staticmethod
    def _to_response(row: UserModelSettings) -> ModelSettingsResponse:
        return ModelSettingsResponse(
            chat_model=row.chat_model,
            ingestion_model=row.ingestion_model,
            embedding_model=row.embedding_model,
            anthropic_api_key=ApiKeyStatus(has_key=row.anthropic_api_key_enc is not None),
            openai_api_key=ApiKeyStatus(has_key=row.openai_api_key_enc is not None),
            dashscope_api_key=ApiKeyStatus(has_key=row.dashscope_api_key_enc is not None),
            openrouter_api_key=ApiKeyStatus(has_key=row.openrouter_api_key_enc is not None),
            use_claude_code=row.use_claude_code,
        )
