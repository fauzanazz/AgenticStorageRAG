from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Model catalog — curated lists shown in frontend dropdowns
# ---------------------------------------------------------------------------

CHAT_MODELS: list[dict[str, str | bool]] = [
    {"provider": "Anthropic", "model_id": "anthropic/claude-opus-4-6", "label": "Claude Opus 4.6", "supports_thinking": True},
    {"provider": "Anthropic", "model_id": "anthropic/claude-sonnet-4-6", "label": "Claude Sonnet 4.6", "supports_thinking": True},
    {"provider": "Anthropic", "model_id": "anthropic/claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5", "supports_thinking": True},
    {"provider": "OpenAI", "model_id": "openai/gpt-4o", "label": "GPT-4o", "supports_thinking": False},
    {"provider": "OpenAI", "model_id": "openai/gpt-5-mini", "label": "GPT-5 mini", "supports_thinking": False},
    {"provider": "OpenAI", "model_id": "openai/o3", "label": "o3", "supports_thinking": True},
    {"provider": "OpenAI", "model_id": "openai/o4-mini", "label": "o4-mini", "supports_thinking": True},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-max", "label": "Qwen3 Max", "supports_thinking": False},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-plus", "label": "Qwen3 Plus", "supports_thinking": False},
    {"provider": "DashScope", "model_id": "dashscope/qwen3-turbo", "label": "Qwen3 Turbo", "supports_thinking": False},
    {"provider": "OpenRouter", "model_id": "openrouter/anthropic/claude-sonnet-4-6", "label": "Claude Sonnet 4.6 (OR)", "supports_thinking": True},
    {"provider": "OpenRouter", "model_id": "openrouter/google/gemini-2.5-pro-preview-06-05", "label": "Gemini 2.5 Pro (OR)", "supports_thinking": False},
    {"provider": "OpenRouter", "model_id": "openrouter/deepseek/deepseek-r1", "label": "DeepSeek R1 (OR)", "supports_thinking": True},
    {"provider": "OpenRouter", "model_id": "openrouter/meta-llama/llama-4-maverick", "label": "Llama 4 Maverick (OR)", "supports_thinking": False},
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
    "OpenRouter": "openrouter",
}

# ---------------------------------------------------------------------------
# API response/request schemas
# ---------------------------------------------------------------------------


class ApiKeyStatus(BaseModel):
    has_key: bool


class ClaudeSetupTokenStatus(BaseModel):
    has_token: bool


class ModelSettingsResponse(BaseModel):
    chat_model: str
    ingestion_model: str
    embedding_model: str
    anthropic_api_key: ApiKeyStatus
    openai_api_key: ApiKeyStatus
    dashscope_api_key: ApiKeyStatus
    openrouter_api_key: ApiKeyStatus
    claude_setup_token: ClaudeSetupTokenStatus

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
    openrouter_api_key: str | None = Field(
        default="", description="Empty string = unchanged, null = clear"
    )
    claude_setup_token: str | None = Field(
        default="", description="Empty string = unchanged, null = clear"
    )


class ModelCatalogResponse(BaseModel):
    chat_models: list[dict[str, Any]]
    embedding_models: list[dict[str, Any]]


class AvailableModelsResponse(BaseModel):
    models: list[dict[str, Any]]
