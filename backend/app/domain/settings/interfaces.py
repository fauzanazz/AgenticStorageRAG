import uuid
from abc import ABC, abstractmethod

from app.domain.settings.models import UserModelSettings
from app.domain.settings.schemas import ModelSettingsResponse, UpdateModelSettingsRequest


class AbstractSettingsService(ABC):

    @abstractmethod
    async def get_model_settings(self, user_id: uuid.UUID) -> ModelSettingsResponse:
        """Return the user's current model settings (API keys as has_key bools)."""
        ...

    @abstractmethod
    async def upsert_model_settings(
        self,
        user_id: uuid.UUID,
        request: UpdateModelSettingsRequest,
    ) -> ModelSettingsResponse:
        """Create or update model settings for a user."""
        ...

    @abstractmethod
    async def get_raw_settings(self, user_id: uuid.UUID) -> UserModelSettings | None:
        """Return the raw ORM row with encrypted key fields (internal use only)."""
        ...
