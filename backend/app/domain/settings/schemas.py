from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Model catalog — curated lists shown in frontend dropdowns
# ---------------------------------------------------------------------------

CHAT_MODELS: list[dict[str, str]] = [
    {"provider": "Anthropic", "model_id": "anthropic/claude-opus-4-5", "label": "Claude Opus 4.5"},
    {"provider": "Anthropic", "model_id": "anthropic/claude-sonnet-4-20250514", "label": "Claude Sonnet 4"},
    {"provider": "Anthropic", "model_id": "anthropic/claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
    {"provider": "Anthropic", "model_id": "anthropic/claude-3-5-haiku-20241022", "label": "Claude 3.5 Haiku"},
    {"provider": "OpenAI", "model_id": "openai/gpt-4o", "label": "GPT-4o"},
    {"provider": "OpenAI", "model_id": "openai/gpt-4o-mini", "label": "GPT-4o mini"},
    {"provider": "OpenAI", "model_id": "openai/o3", "label": "o3"},
    {"provider": "OpenAI", "model_id": "openai/o4-mini", "label": "o4-mini"},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-max", "label": "Qwen3 Max"},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-plus", "label": "Qwen3 Plus"},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-turbo", "label": "Qwen3 Turbo"},
]

EMBEDDING_MODELS: list[dict[str, str]] = [
    {"provider": "OpenAI", "model_id": "openai/text-embedding-3-small", "label": "text-embedding-3-small"},
    {"provider": "OpenAI", "model_id": "openai/text-embedding-3-large", "label": "text-embedding-3-large"},
    {"provider": "DashScope", "model_id": "dashscope/text-embedding-v3", "label": "text-embedding-v3"},
]

# Maps provider name → required key field name
PROVIDER_KEY_MAP: dict[str, str] = {
    "Anthropic": "anthropic",
    "OpenAI": "openai",
    "DashScope": "dashscope",
}

# ---------------------------------------------------------------------------
# API response/request schemas
# ---------------------------------------------------------------------------


class ApiKeyStatus(BaseModel):
    has_key: bool


class ModelSettingsResponse(BaseModel):
    chat_model: str
    ingestion_model: str
    embedding_model: str
    anthropic_api_key: ApiKeyStatus
    openai_api_key: ApiKeyStatus
    dashscope_api_key: ApiKeyStatus

    model_config = {"from_attributes": True}


class UpdateModelSettingsRequest(BaseModel):
    chat_model: str | None = None
    ingestion_model: str | None = None
    embedding_model: str | None = None
    # "" = unchanged, None = clear, "sk-..." = set new value
    anthropic_api_key: str | None = Field(
        default="", description="Empty string = unchanged, null = clear"
    )
    openai_api_key: str | None = Field(
        default="", description="Empty string = unchanged, null = clear"
    )
    dashscope_api_key: str | None = Field(
        default="", description="Empty string = unchanged, null = clear"
    )


class ModelCatalogResponse(BaseModel):
    chat_models: list[dict[str, Any]]
    embedding_models: list[dict[str, Any]]
