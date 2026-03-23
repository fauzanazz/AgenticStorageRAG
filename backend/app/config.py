"""Application configuration using Pydantic Settings.

All configuration is driven by environment variables with sensible defaults
for local development. See .env.example for the full list.
"""

from functools import lru_cache

from pydantic import model_validator
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
    app_name: str = "DriveRAG"
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
    frontend_url: str = "http://localhost:3000"  # For OAuth callback redirects
    jwt_secret_key: str = "change-me-in-production"
    encryption_key: str = ""  # Separate key for encrypting stored secrets; required in production
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
    neo4j_database: str = (
        "dingdongrag"  # Separate from other projects (no underscores in Neo4j DB names)
    )

    # --- Redis ---
    redis_url: str = "redis://localhost:16379/0"

    # --- LLM (LiteLLM) ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    dashscope_api_key: str = ""  # Alibaba Cloud DashScope (Qwen models)
    gemini_api_key: str = ""  # Google Gemini (via LiteLLM gemini/ prefix)
    openrouter_api_key: str = ""  # OpenRouter (via LiteLLM openrouter/ prefix)
    default_model: str = "anthropic/claude-sonnet-4-6"
    fallback_model: str = "anthropic/claude-sonnet-4-6"
    # Dedicated model for ingestion/KG-extraction tasks.
    # These are pure JSON-structured-output tasks that do NOT need frontier
    # reasoning — a fast, cheap model with high throughput limits is optimal.
    # gpt-5-mini: cheaper than gpt-4o-mini, high rate limits.
    ingestion_model: str = "openai/gpt-5-mini"
    # Cheap, fast model for auto-generating chat session titles.
    title_model: str = "openrouter/openai/gpt-oss-120b"

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
    file_concurrency: int = 1  # Sequential file processing to prevent OOM on large PDFs
    max_ingest_file_size_mb: int = 50  # Drive files larger than this are skipped

    # --- Pipeline stage concurrency ---
    pipeline_download_workers: int = 5
    pipeline_extract_workers: int = 3
    pipeline_embed_workers: int = 2
    pipeline_embed_batch_size: int = 100  # Max chunks per embedding API call
    pipeline_embed_max_retries: int = 2
    pipeline_download_extract_max_retries: int = 2
    pipeline_queue_multiplier: int = 2  # Queue maxsize = workers * multiplier

    @model_validator(mode="after")
    def _reject_weak_defaults(self) -> "Settings":
        if self.environment in ("staging", "production"):
            if self.jwt_secret_key == "change-me-in-production":
                raise ValueError(
                    "JWT_SECRET_KEY must be changed from its default in "
                    f"{self.environment} environments"
                )
            if not self.encryption_key:
                raise ValueError(f"ENCRYPTION_KEY is required in {self.environment} environments")
            if self.encryption_key == self.jwt_secret_key:
                raise ValueError(
                    "ENCRYPTION_KEY must be different from JWT_SECRET_KEY "
                    "(separate key for stored secrets vs session tokens)"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
