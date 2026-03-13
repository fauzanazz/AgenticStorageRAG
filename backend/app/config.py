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
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/dingdong_rag"

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "dingdongrag"  # Separate from other projects (no underscores in Neo4j DB names)

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM (LiteLLM) ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_model: str = "anthropic/claude-sonnet-4-20250514"
    fallback_model: str = "openai/gpt-4o"

    # --- Google Drive (read-only, owner only) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # --- File Upload ---
    max_upload_size_mb: int = 50
    upload_ttl_days: int = 7


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
