"""Application configuration using Pydantic Settings.

All configuration is driven by environment variables with sensible defaults
for local development. See .env.example for the full list.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "DingDong RAG"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"  # development | staging | production

    # --- API ---
    api_prefix: str = "/api/v1"
    allowed_origins: list[str] = ["http://localhost:3000"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    cors_allow_headers: list[str] = ["Authorization", "Content-Type"]

    # --- Auth ---
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # --- Supabase (Database + Storage) ---
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/dingdong_rag"

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:17687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "dingdongrag"  # Separate from other projects (no underscores in Neo4j DB names)

    # --- Redis ---
    redis_url: str = "redis://localhost:16379/0"

    # --- LLM (LiteLLM) ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    dashscope_api_key: str = ""  # Alibaba Cloud DashScope (Qwen models)
    gemini_api_key: str = ""  # Google Gemini (via LiteLLM gemini/ prefix)
    default_model: str = "dashscope/qwen3-max"
    fallback_model: str = "anthropic/claude-sonnet-4-20250514"
    # Dedicated model for ingestion/KG-extraction tasks.
    # These are pure JSON-structured-output tasks that do NOT need frontier
    # reasoning — a fast, cheap model with high throughput limits is optimal.
    # gpt-4o-mini: $0.15/1M input — 16× cheaper than gpt-4o, very high rate limits.
    ingestion_model: str = "openai/gpt-4o-mini"

    # --- Embeddings ---
    # LiteLLM model string for embedding generation.
    # Examples:
    #   "text-embedding-3-small"           (OpenAI)
    #   "gemini/text-embedding-004"        (Google Gemini)
    #   "text-embedding-v3"                (DashScope / Alibaba)
    embedding_model: str = "text-embedding-3-small"

    # --- Google Drive (read-only) ---
    # Option 1: Service Account (preferred for production)
    google_service_account_file: str = ""  # Path to SA JSON key file
    google_service_account_json: str = ""  # Inline SA JSON (alternative to file)
    # Option 2: OAuth2 with your personal Google account
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""  # Run: uv run python -m app.scripts.google_auth
    # Shared
    google_drive_folder_id: str = ""  # Default Drive folder ID to scan

    # --- File Upload ---
    max_upload_size_mb: int = 50
    upload_ttl_days: int = 7

    # --- Worker / Ingestion concurrency ---
    # Number of worker replicas is controlled via docker-compose deploy.replicas
    # (default: 2 -- each handles one ingestion job at a time)
    file_concurrency: int = 3  # Max parallel files within a single orchestrator run


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
